"""
Example configuration for the Telegram Order Notifier.
Copy this file to config.py and fill in your own values.
NEVER commit the real config.py to a public repository!
"""

# --- Store server (SSH) ---
SSH_HOST = "203.0.113.10"       # your VPS IP
SSH_USER = "ubuntu"

# --- Telegram bot (from @BotFather) ---
BOT_TOKEN = "123456:ABC-DEF..."  # your bot token
CHAT_ID_OWNER = "123456789"      # your private chat id (get from @userinfobot)
CHAT_ID_GROUP = "-1001234567890" # your group id
GROUP_TOPIC_ID = "3570"          # topic/thread id inside the group (or None)

# --- Store database (used only in read-only mysql queries) ---
DB_NAME = "shopdb"
