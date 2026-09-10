#!/usr/bin/env python3
"""
Telegram Order Notifier for WooCommerce (HPOS)
==============================================
اسکریپت نوتیفیکیشن سفارش‌های ووکامرس به تلگرام

Polls a WooCommerce store over SSH and sends new orders + periodic
heartbeats to Telegram (private chat + group topic).

Designed to run from cron every 15 minutes; internally throttles itself
to a full check every ~3 hours via a timestamp gate. On failure the
gate stays open, so the next run retries automatically.

Features
--------
- HPOS-compatible (reads wp_wc_orders, NOT wp_posts)
- Per-order Persian message: order #, customer name/phone, items,
  total in Toman, payment method, address
- Heartbeat on every full check (proves the pipeline is alive)
- Fail-safe state: last-order-id + last-check-ts live on the server
  and only advance after confirmed Telegram delivery
- Duplicate-free by design (id > last_id, ascending)
- Read-only on store data except two tiny state files

Usage
-----
1. cp config.example.py config.py  ->  fill in your values
2. Run:  python3 notifier.py
   (cron: */15 * * * * cd /path/to/repo && python3 notifier.py)

Author: Alireza (bizhameh.ir)
License: MIT
"""

import subprocess
import sys
import time
import urllib.parse
import urllib.request
from typing import Optional

try:
    from config import (
        SSH_HOST, SSH_USER,
        BOT_TOKEN, CHAT_ID_OWNER, CHAT_ID_GROUP, GROUP_TOPIC_ID,
    )
except ImportError:
    sys.exit("config.py not found. Copy config.example.py -> config.py")

SSH_PORT = 22
GATE_SECONDS = 10500          # ~3 hours between full checks
STATE_ORDER_ID = ".notifier_last_order_id"
STATE_CHECK_TS = ".notifier_last_check_ts"
HTTP_TIMEOUT = 25


# ------------------------------------------------------------------
# SSH
# ------------------------------------------------------------------
def ssh_run(cmd: str) -> str:
    """Run a shell command on the store server, return stdout."""
    base = [
        "ssh", "-p", str(SSH_PORT),
        "-o", "ConnectTimeout=20",
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        f"{SSH_USER}@{SSH_HOST}",
        cmd,
    ]
    proc = subprocess.run(base, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"SSH failed: {proc.stderr.strip()[:200]}")
    return proc.stdout


# ------------------------------------------------------------------
# Telegram (send from the local machine — the store server often
# cannot reach api.telegram.org directly)
# ------------------------------------------------------------------
def tg_send(text: str, chat_id: str, topic_id: Optional[str] = None) -> bool:
    """Send a message via the Telegram Bot API. Returns success."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    if topic_id:
        data["message_thread_id"] = topic_id
    payload = urllib.parse.urlencode(data).encode()
    try:
        with urllib.request.urlopen(url, data=payload, timeout=HTTP_TIMEOUT) as r:
            return r.status == 200
    except Exception as exc:  # noqa: BLE001
        print(f"TG send to {chat_id} failed: {exc}")
        return False


def send_both(text: str) -> bool:
    """Send to owner chat (required) + group topic (best effort)."""
    ok_owner = tg_send(text, CHAT_ID_OWNER)
    ok_group = tg_send(text, CHAT_ID_GROUP, GROUP_TOPIC_ID)
    return ok_owner  # group failure alone must not advance the gate


# ------------------------------------------------------------------
# State gate — lives on the server so any host can resume the loop
# ------------------------------------------------------------------
def read_state():
    """Return (last_order_id, last_check_ts, now)."""
    out = ssh_run(
        f"cat ~/{STATE_ORDER_ID} ~/{STATE_CHECK_TS} 2>/dev/null; "
        f"echo '---'; date +%s"
    )
    parts = out.strip().split("---")
    lines = [ln.strip() for ln in parts[0].splitlines() if ln.strip()]
    last_id = int(lines[0]) if len(lines) > 0 and lines[0].isdigit() else 0
    last_ts = int(lines[1]) if len(lines) > 1 and lines[1].isdigit() else 0
    now = int(parts[1].strip())
    return last_id, last_ts, now


def write_state(last_id: int, now: int) -> None:
    ssh_run(
        f'echo "{last_id}" > ~/{STATE_ORDER_ID} && '
        f'date +%s > ~/{STATE_CHECK_TS}'
    )


# ------------------------------------------------------------------
# Store queries (HPOS tables — wp_wc_orders, NOT wp_posts)
# ------------------------------------------------------------------
def fetch_new_order_ids(last_id: int):
    out = ssh_run(
        "mysql -N -B -e "
        "\"SELECT id FROM wp_wc_orders "
        "WHERE status='wc-processing' AND id > %d ORDER BY id ASC\" %s"
        % (last_id, "shopdb")
    )
    return [int(x) for x in out.split() if x.strip().isdigit()]


def fetch_order_details(order_id: int) -> dict:
    """Fetch customer + items + total for one order (read-only)."""
    out = ssh_run(
        "mysql -N -B -e \""
        "SELECT first_name, last_name, phone, city, state "
        "FROM wp_wc_order_addresses WHERE order_id=%d AND address_type='shipping' LIMIT 1; "
        "SELECT total_amount FROM wp_wc_orders WHERE id=%d; "
        "SELECT payment_method_title FROM wp_wc_orders WHERE id=%d; "
        "SELECT i.order_item_name, m.meta_value "
        "FROM wp_woocommerce_order_items i "
        "JOIN wp_woocommerce_order_itemmeta m "
        "  ON m.order_item_id=i.order_item_id AND m.meta_key='_qty' "
        "WHERE i.order_id=%d AND i.order_item_type='line_item'\" %s"
        % (order_id, order_id, order_id, order_id, "shopdb")
    )
    blocks = out.strip().split("\n")
    name = phone = city = state = "?"
    total = "0"
    payment = "?"
    items = []
    if blocks:
        first = blocks[0].split("\t")
        if len(first) >= 5:
            name, phone, city, state = (
                first[0], first[2], first[3], first[4]
            )
    for line in blocks:
        cols = line.split("\t")
        if len(cols) == 2:
            items.append(f"{cols[0]} × {cols[1]}")
        elif len(cols) == 1 and cols[0].isdigit():
            if total == "0":
                total = cols[0]
            else:
                payment = cols[0]
    return {
        "name": name, "phone": phone, "city": city, "state": state,
        "total": total, "payment": payment, "items": items,
    }


def compose_order_message(order_id: int, d: dict) -> str:
    return (
        f"🛒 سفارش جدید #{order_id}\n"
        f"👤 {d['name']}\n"
        f"📱 {d['phone']}\n"
        f"📦 {'، '.join(d['items'])}\n"
        f"💰 {d['total']} تومان\n"
        f"💳 {d['payment']}\n"
        f"📍 {d['city']}، {d['state']}"
    )


def heartbeat_text() -> str:
    tehran = time.gmtime(time.time() + 3 * 3600 + 30 * 60)
    hhmm = time.strftime("%H:%M", tehran)
    return f"✅ بررسی انجام شد - ساعت {hhmm} به وقت ایران - سفارش جدیدی ثبت نشده"


# ------------------------------------------------------------------
# Main loop
# ------------------------------------------------------------------
def main() -> int:
    last_id, last_ts, now = read_state()

    # Gate: only run a full check every ~3h (fails keep the gate open)
    if last_ts and (now - last_ts) < GATE_SECONDS:
        print("[SILENT] gate closed — checked recently")
        return 0

    print(f"[FULL CHECK] last order id = {last_id}")

    new_ids = fetch_new_order_ids(last_id)
    if not new_ids:
        if send_both(heartbeat_text()):
            write_state(last_id, int(time.time()))
            print("heartbeat sent, no new orders")
        else:
            print("heartbeat FAILED — gate stays open for retry")
        return 0

    for oid in new_ids:
        details = fetch_order_details(oid)
        msg = compose_order_message(oid, details)
        if send_both(msg):
            write_state(oid, int(time.time()))
            print(f"order #{oid} sent")
        else:
            print(f"order #{oid} FAILED to send — will retry next run")
            break  # keep ordering; retry from this id next run

    return 0


if __name__ == "__main__":
    sys.exit(main())
