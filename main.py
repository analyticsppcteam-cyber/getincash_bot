import os
import requests
from flask import Flask, request

app = Flask(__name__)

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.environ.get("BOT_TOKEN")  # добавлен в Render → Environment
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

BANNER_PATH = "tg_banner_bot.jpg"  # файл лежит в репозитории
LANDING_URL_BASE = "https://getincash.com/currency-exchange"

# =========================
# HELPERS
# =========================

def send_photo(chat_id, caption, button_url):
    url = f"{TELEGRAM_API}/sendPhoto"

    with open(BANNER_PATH, "rb") as photo:
        payload = {
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": "HTML",
            "reply_markup": {
                "inline_keyboard": [[
                    {
                        "text": "Начать пользоваться",
                        "url": button_url
                    }
                ]]
            }
        }

        files = {"photo": photo}
        return requests.post(url, data=payload, files=files)


# =========================
# ROUTES
# =========================

@app.route("/", methods=["GET"])
def healthcheck():
    return "ok", 200


@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    data = request.get_json(force=True)

    if "message" not in data:
        return "ignored", 200

    message = data["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    # =========================
    # /start payload
    # =========================
    utm_campaign = "unknown"
    utm_content = "unknown"
    utm_term = "unknown"

    if text.startswith("/start"):
        parts = text.split(" ", 1)

        if len(parts) > 1:
            payload = parts[1]

            # ожидаем формат:
            # chan_102|ad_17|ru
            payload_parts = payload.split("|")

            if len(payload_parts) == 3:
                utm_campaign, utm_content, utm_term = payload_parts

        landing_url = (
            f"{LANDING_URL_BASE}"
            f"?utm_source=telegram"
            f"&utm_medium=paid_social"
            f"&utm_campaign={utm_campaign}"
            f"&utm_content={utm_content}"
            f"&utm_term={utm_term}"
        )

        caption = (
            "<b>Сервис быстрого и безопасного обмена валют</b>\n\n"
            "GetInCash — надежно, удобно и без лишних комиссий."
        )

        send_photo(chat_id, caption, landing_url)

    return "ok", 200


# =========================
# ENTRYPOINT
# =========================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
