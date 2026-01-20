import os
import re
import json
import urllib.parse
from typing import Optional, Tuple

import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# =========================
# CONFIG (ENV ONLY)
# =========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Missing env BOT_TOKEN")

BASE_URL = os.environ.get("BASE_URL", "https://getincash.com/currency-exchange")

UTM_SOURCE = os.environ.get("UTM_SOURCE", "telegram")
UTM_MEDIUM = os.environ.get("UTM_MEDIUM", "paid_social")

# Путь к локальному баннеру в проекте (рядом с main.py)
BANNER_PATH = os.environ.get("BANNER_PATH", "tg_banner_bot.jpg")

# (Опционально) секрет для вебхука: добавьте его в URL вебхука и проверяйте
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

# Ограничения deep linking параметра по документации:
# допустимы только A-Z a-z 0-9 _ - и длина до 64 :contentReference[oaicite:4]{index=4}
DEEP_LINK_ALLOWED_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


# =========================
# TELEGRAM API HELPERS
# =========================
def tg_api(method: str, data: dict, files: Optional[dict] = None) -> dict:
    """
    Telegram Bot API request.
    Docs: requests go to https://api.telegram.org/bot<token>/METHOD :contentReference[oaicite:5]{index=5}
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        if files:
            r = requests.post(url, data=data, files=files, timeout=20)
        else:
            r = requests.post(url, json=data, timeout=20)
        r.raise_for_status()
        payload = r.json()
        return payload
    except Exception as e:
        # Логируем в stdout (видно в логах хостинга)
        print(f"[tg_api] error method={method}: {e}")
        return {"ok": False, "description": str(e)}


def send_welcome(chat_id: int, site_url: str) -> None:
    """
    Отправляем баннер + подпись + кнопку.
    """
    caption = "Сервис быстрого и безопасного обмена валют"
    keyboard = {
        "inline_keyboard": [
            [{"text": "Начать пользоваться", "url": site_url}]
        ]
    }

    # Если файл баннера есть — шлём фото, иначе шлём текст
    if os.path.exists(BANNER_PATH):
        with open(BANNER_PATH, "rb") as f:
            tg_api(
                "sendPhoto",
                data={
                    "chat_id": chat_id,
                    "caption": caption,
                    "reply_markup": json.dumps(keyboard, ensure_ascii=False),
                },
                files={"photo": f},
            )
    else:
        tg_api(
            "sendMessage",
            data={
                "chat_id": chat_id,
                "text": f"[лого GetInCash]\n{caption}",
                "reply_markup": json.dumps(keyboard, ensure_ascii=False),
            },
        )


# =========================
# UTM / PAYLOAD PARSING
# =========================
def parse_start_payload(text: str) -> str:
    """
    Извлекаем payload из сообщений:
      "/start payload"
      "/start"
    По документации deep link даёт "/start <param>" :contentReference[oaicite:6]{index=6}
    """
    if not text:
        return ""
    # /start или /start@botname
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return ""
    cmd = parts[0]
    if not cmd.startswith("/start"):
        return ""
    return parts[1].strip() if len(parts) > 1 else ""


def split_payload(payload: str) -> Tuple[str, str, str]:
    """
    Поддерживаем форматы:
      chan_102__ad_17__ru     (рекомендовано: разделитель "__")
      chan_102-ad_17-ru       (альтернатива: "-")
    Важно: deep link параметр ограничен допустимыми символами :contentReference[oaicite:7]{index=7}
    """
    if not payload:
        return ("unknown", "unknown", "")

    # Валидация на допустимые символы/длину
    if not DEEP_LINK_ALLOWED_RE.match(payload):
        # если пришло что-то "грязное" — не используем
        return ("unknown", "unknown", "")

    if "__" in payload:
        parts = payload.split("__")
    elif "-" in payload:
        parts = payload.split("-")
    else:
        # без разделителей — считаем это campaign
        parts = [payload]

    campaign = parts[0] if len(parts) >= 1 and parts[0] else "unknown"
    content = parts[1] if len(parts) >= 2 and parts[1] else "unknown"
    term = parts[2] if len(parts) >= 3 and parts[2] else ""
    return (campaign, content, term)


def build_site_url(
    campaign: str,
    content: str,
    term: str,
) -> str:
    utm = {
        "utm_source": UTM_SOURCE,
        "utm_medium": UTM_MEDIUM,
        "utm_campaign": campaign,
        "utm_content": content,
    }
    if term:
        utm["utm_term"] = term

    return BASE_URL + "?" + urllib.parse.urlencode(utm)


# =========================
# WEBHOOK ROUTES
# =========================
@app.get("/")
def health():
    return "ok", 200


@app.post("/webhook")
def webhook():
    # (Опционально) проверка секрета в query string
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

    text = msg.get("text", "")
    payload = parse_start_payload(text)

    campaign, content, term = split_payload(payload)

    # Если term не пришёл — берём язык пользователя (language_code)
    # Telegram явно упоминает language_code как основу для локализации/адаптации :contentReference[oaicite:8]{index=8}
    if not term:
        user = msg.get("from") or {}
        term = user.get("language_code", "") or ""

    site_url = build_site_url(campaign, content, term)
    send_welcome(chat_id=chat_id, site_url=site_url)

    return jsonify({"ok": True})


if __name__ == "__main__":
    # Хостинги обычно дают PORT
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
