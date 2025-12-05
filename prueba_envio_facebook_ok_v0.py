import os
import requests

PAGE_ACCESS_TOKEN = "EAAXWEbgy8BwBPzqwUARiJoYiUTBJ89Jx9nzmIhRR3N3frr48aBZBCaOTgUZC4zFltA6wW9q0OPDywMqtZAkZCKDgsOX2A2vEfzDbdoRZB5V4sWjGGxpKZA0roLvlnXXUe9OfSndZCaHvlJjAiWZCVoWbwCqzpZB7llzEF8zFprE4rg5ZCNuSDaaZCtHkaL6AZCkq2aK4wDjY5OWS"

GRAPH_API_URL = "https://graph.facebook.com/v18.0/me/messages"

def send_text(psid: str, text: str):
    payload = {
        "recipient": {"id": psid},
        "message": {"text": text}
    }
    params = {"access_token": PAGE_ACCESS_TOKEN}

    response = requests.post(GRAPH_API_URL, params=params, json=payload, timeout=10)
    try:
        response.raise_for_status()
        print("✅ Mensaje enviado:", response.json())
    except requests.HTTPError:
        print("❌ Error al enviar mensaje")
        print(response.status_code, response.text)
        raise

if __name__ == "__main__":
    PSID_DESTINO = "25546787448240611"
    send_text(PSID_DESTINO, "esto es una prueba de envio desde la web_mascotas  👋")