import json
import os
import urllib.parse
from pathlib import Path

import requests
from flask import Flask, request

app = Flask(__name__)

# =========================
# Настройки (меняй при необходимости)
# =========================

BASE_URL = "https://getincash.com/currency-exchange"
UTM_SOURCE = "telegram"
UTM_MEDIUM = "paid_social"

# Имя файла баннера в репозитории
BANNER_FILE_NAME = "tg_banner_bot.jpg"

# =========================
# Telegram API
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    # Чтобы деплой не "молчал": лучше явная ошибка в логах, чем странное поведение
    raise RuntimeError("ENV BOT_TOKEN is not set. Add it in Render -> Environment -> Environment Variables.")

API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

BANNER_PATH = (Path(__file__).resolve().parent / BANNER_FILE_NAME)


def build_site_url(payload: str) -> str:
    """
    Поддерживает несколько форматов payload:
    1) chan_102__ad_17__ru   (как у тебя было)
    2) chan_102_ad_17_ru     (если без двойных __)
    3) пустой payload

    Маппинг:
    utm_campaign = parts[0]
    utm_content  = parts[1]
    utm_term     = parts[2]
    """
    payload = (payload or "").strip()

    if not payload:
        campaign, content, term = "unknown", "unknown", "unknown"
    else:
        if "__" in payload:
            parts = [p for p in payload.split("__") if p != ""]
        else:
            parts = [p for p in payload.split("_") if p != ""]

        campaign = parts[0] if len(parts) > 0 else "unknown"
        content = parts[1] if len(parts) > 1 else "unknown"
        term = parts[2] if len(parts) > 2 else "unknown"

    params = {
        "utm_source": UTM_SOURCE,
        "utm_medium": UTM_MEDIUM,
        "utm_campaign": campaign,
        "utm_content": content,
        "utm_term": term,
    }
    return BASE_URL + "?" + urllib.parse.urlencode(params)


def tg_send_message(chat_id: int, text: str) -> None:
    r = requests.post(
        f"{API_BASE}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=20,
    )
    r.raise_for_status()


def tg_send_banner(chat_id: int, site_url: str) -> None:
    caption = (
        "Сервис быстрого и безопасного обмена валют\n"
        "<b>Нажми, чтобы начать</b>\n"
        "⬇️⬇️⬇️"
    )

    reply_markup = {
        "inline_keyboard": [
            [{"text": "Начать пользоваться", "url": site_url}],
        ]
    }

    # Если баннера нет — отправим хотя бы текст с кнопкой
    if not BANNER_PATH.exists():
        tg_send_message(chat_id, f"{caption}\n{site_url}")
        return

    with BANNER_PATH.open("rb") as photo:
        r = requests.post(
            f"{API_BASE}/sendPhoto",
            data={
                "chat_id": str(chat_id),
                "caption": caption,
                "reply_markup": json.dumps(reply_markup, ensure_ascii=False),
            },
            files={"photo": photo},
            timeout=30,
        )
    r.raise_for_status()


def extract_message(update: dict) -> dict | None:
    # Telegram может прислать message / edited_message / channel_post etc.
    return (
        update.get("message")
        or update.get("edited_message")
        or update.get("channel_post")
        or update.get("edited_channel_post")
    )


# =========================
# Routes
# =========================

@app.route("/", methods=["GET"])
def healthcheck():
    return "ok", 200


@app.route("/telegram", methods=["GET"])
def telegram_get():
    # Чтобы в браузере не видеть 405 — просто показываем ok
    return "ok", 200


@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    update = request.get_json(silent=True) or {}

    msg = extract_message(update)
    if not msg:
        return "ok", 200

    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    text = (msg.get("text") or "").strip()

    if not chat_id:
        return "ok", 200

    if text.startswith("/start"):
        payload = ""
        # /start <payload>
        if " " in text:
            payload = text.split(" ", 1)[1].strip()

        site_url = build_site_url(payload)
        tg_send_banner(chat_id, site_url)

    return "ok", 200


# =========================
# Entrypoint
# =========================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

