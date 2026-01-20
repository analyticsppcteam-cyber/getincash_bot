import os
import re
import json
import urllib.parse
from typing import Optional, Tuple

import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# =========================================================
# CONFIG (только через переменные окружения на Render)
# =========================================================
# В Render -> Settings -> Environment -> Add Environment Variable
# BOT_TOKEN = 123:ABC...
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("Missing env var BOT_TOKEN")

# Куда ведём трафик
BASE_URL = os.environ.get("BASE_URL", "https://getincash.com/currency-exchange").strip()

# UTM фиксированная часть
UTM_SOURCE = os.environ.get("UTM_SOURCE", "telegram").strip()
UTM_MEDIUM = os.environ.get("UTM_MEDIUM", "paid_social").strip()

# Баннер лежит в репозитории рядом с main.py
BANNER_PATH = os.environ.get("BANNER_PATH", "tg_banner_bot.jpg").strip()

# (опционально) секрет для защиты вебхука:
# WEBHOOK_SECRET=someSecret
# и webhook URL будет: https://<domain>/webhook?secret=someSecret
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "").strip()

# Deep-link параметр /start (payload) в Telegram ограничен символами и длиной
DEEP_LINK_ALLOWED_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


# =========================================================
# Telegram Bot API helper
# =========================================================
def tg_api(method: str, *, data: dict, files: Optional[dict] = None) -> dict:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        # Для sendMessage/sendPhoto Telegram корректно принимает form-data
        if files:
            r = requests.post(url, data=data, files=files, timeout=30)
        else:
            r = requests.post(url, data=data, timeout=30)
        r.raise_for_status()
        payload = r.json()
        if not payload.get("ok"):
            print(f"[tg_api] Telegram returned ok=false: {payload}")
        return payload
    except Exception as e:
        print(f"[tg_api] error method={method}: {e}")
        return {"ok": False, "description": str(e)}


def send_welcome(chat_id: int, site_url: str) -> None:
    caption = "Сервис быстрого и безопасного обмена валют"

    keyboard = {
        "inline_keyboard": [
            [{"text": "Начать пользоваться", "url": site_url}],
        ]
    }
    reply_markup = json.dumps(keyboard, ensure_ascii=False)

    # Если баннер есть — отправляем фото + подпись + кнопку
    if os.path.exists(BANNER_PATH):
        try:
            with open(BANNER_PATH, "rb") as f:
                tg_api(
                    "sendPhoto",
                    data={
                        "chat_id": str(chat_id),
                        "caption": caption,
                        "reply_markup": reply_markup,
                    },
                    files={"photo": f},
                )
            return
        except Exception as e:
            print(f"[send_welcome] banner open/send error: {e}")

    # Фолбэк: если баннер не найден или не отправился — текст + кнопка
    tg_api(
        "sendMessage",
        data={
            "chat_id": str(chat_id),
            "text": f"[лого GetInCash]\n{caption}",
            "reply_markup": reply_markup,
        },
    )


# =========================================================
# Payload -> UTM
# =========================================================
def parse_start_payload(message_text: str) -> str:
    """
    Извлекаем payload из:
      /start
      /start payload
      /start@YourBot payload
    """
    if not message_text:
        return ""
    parts = message_text.strip().split(maxsplit=1)
    if not parts:
        return ""
    cmd = parts[0]
    if not cmd.startswith("/start"):
        return ""
    return parts[1].strip() if len(parts) > 1 else ""


def split_payload(payload: str) -> Tuple[str, str, str]:
    """
    Поддерживаем:
      chan_102__ad_17__ru
      chan_102-ad_17-ru

    Возвращаем:
      (utm_campaign, utm_content, utm_term)
    """
    if not payload:
        return ("unknown", "unknown", "")

    # Telegram deep link payload должен быть "чистым"
    if not DEEP_LINK_ALLOWED_RE.match(payload):
        return ("unknown", "unknown", "")

    if "__" in payload:
        parts = payload.split("__")
    elif "-" in payload:
        parts = payload.split("-")
    else:
        parts = [payload]

    campaign = parts[0] if len(parts) >= 1 and parts[0] else "unknown"
    content = parts[1] if len(parts) >= 2 and parts[1] else "unknown"
    term = parts[2] if len(parts) >= 3 and parts[2] else ""
    return (campaign, content, term)


def build_site_url(campaign: str, content: str, term: str) -> str:
    utm = {
        "utm_source": UTM_SOURCE,
        "utm_medium": UTM_MEDIUM,
        "utm_campaign": campaign,
        "utm_content": content,
    }
    if term:
        utm["utm_term"] = term

    return BASE_URL + "?" + urllib.parse.urlencode(utm, safe="")


# =========================================================
# Routes
# =========================================================
@app.get("/")
def health():
    # Чтобы в браузере по главному URL не было Not Found
    return "ok", 200


@app.post("/webhook")
def webhook():
    # (опционально) защита секретом
    if WEBHOOK_SECRET:
        if request.args.get("secret") != WEBHOOK_SECRET:
            return "forbidden", 403

    update = request.get_json(silent=True) or {}
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return jsonify({"ok": True})

    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if not chat_id:
        return jsonify({"ok": True})

    text = msg.get("text", "") or ""
    payload = parse_start_payload(text)

    campaign, content, term = split_payload(payload)

    # Если term не передали — попробуем взять язык пользователя (language_code)
    if not term:
        user = msg.get("from") or {}
        term = (user.get("language_code") or "").strip()

    site_url = build_site_url(campaign, content, term)
    send_welcome(chat_id=int(chat_id), site_url=site_url)

    return jsonify({"ok": True})


if __name__ == "__main__":
    # Render прокидывает PORT
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
