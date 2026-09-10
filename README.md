# bizhameh — WooCommerce Store Projects 🛒

پروژه‌های توسعه فروشگاه اینترنتی [bizhameh.ir](https://bizhameh.ir) — فروشگاه ووکامرسی با تم کاملاً اختصاصی و زیرساخت اتوماسیون سفارش‌ها.

Two components:

| Folder | What it is | Tech |
|---|---|---|
| [`bizhameh-theme/`](bizhameh-theme/) | Custom WordPress theme stylesheet — ~5,300 lines of hand-tuned, de-duplicated CSS for a Persian (RTL) WooCommerce store: glassmorphism product cards, custom checkout & account pages, dark mode, OTP login forms, slider styling | CSS, RTL |
| [`telegram-order-notifier/`](telegram-order-notifier/) | Zero-dependency Python service that polls WooCommerce orders over SSH and pushes them to Telegram — with heartbeats, a 3-hour gate, and automatic retry on failure | Python 3, MySQL (HPOS), Telegram Bot API, SSH |

## Telegram Order Notifier — highlights

- **HPOS-compatible** — reads `wp_wc_orders` (WooCommerce High-Performance Order Storage), not the legacy `wp_posts` table
- **Fail-safe state machine** — last-order-id and last-check-timestamp live on the store server; they only advance after a *confirmed* Telegram delivery, so failed runs retry automatically and orders are never duplicated or lost
- **Heartbeat messages** — every full check sends a short status line, so silence itself becomes a signal
- **No dependencies** — stdlib only (`urllib`, `subprocess`), deployable on any box with SSH access

## Theme highlights

- Full Persian/RTL layout with Vazirmatn font
- Glassmorphism design system (backdrop-filter, layered gradients, custom shadows)
- Dark mode with CSS custom properties
- Custom styling for OTP (SMS) login forms, checkout, and account pages
- De-duplicated from ~5,500 to ~5,260 lines with zero visual change (braces verified balanced, staged in sessions with rollback backups)

## License

MIT
