import os
import requests
from flask import Flask, request, jsonify

# =========================
# CONFIG
# =========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # ОБЯЗАТЕЛЬНО задан в Render
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)


# =========================
# HEALTHCHECK
# =========================
@app.route("/", methods=["GET"])
def index():
    return "ok", 200


# =========================
# TELEGRAM WEBHOOK
# =========================
@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    data = request.get_json()

    if not data:
        return jsonify({"status": "no data"}), 400

    message = data.get("message")
    if not message:
        return jsonify({"status": "no message"}), 200

    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    if text == "/start":
        send_message(
            chat_id,
            "👋 Привет!\n\n"
            "Это бот GetinCash.\n"
            "Я успешно запущен и готов к работе 🚀"
        )

    return jsonify({"status": "ok"}), 200


# =========================
# SEND MESSAGE
# =========================
def send_message(chat_id: int, text: str):
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    requests.post(url, json=payload)


# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
