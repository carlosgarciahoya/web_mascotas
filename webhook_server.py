import os
import json
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from messenger_client import MessengerClient

load_dotenv()

VERIFY_TOKEN = os.getenv("FB_VERIFY_TOKEN", "mi_token_verificacion")
app = Flask(__name__)
messenger = MessengerClient()

@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Error de verificación", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    print(json.dumps(data, indent=2))

    if data["object"] == "page":
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                handle_message(event)
        return "EVENT_RECEIVED", 200

    return "NOT_FOUND", 404

def handle_message(event):
    sender_psid = event["sender"]["id"]
    if "message" in event:
        message_text = event["message"].get("text", "")
        reply = f"¡Hola! Recibí tu mensaje: {message_text}"
        messenger.send_text_message(sender_psid, reply)

if __name__ == "__main__":
    app.run(port=5000)