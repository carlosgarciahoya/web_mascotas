import requests
import os

# Configura tus credenciales y tu phone number ID de WhatsApp

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")

def enviar_mensaje_texto(numero_destino, texto):
    """
    Envía un mensaje de texto a 'numero_destino' usando WhatsApp Cloud API.
    """
    url = f"https://graph.facebook.com/v22.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": numero_destino,
        "type": "text",
        "text": {"body": texto}
    }

    response = requests.post(url, headers=headers, json=data)
    return response.json()


def enviar_imagen(numero_destino, enlace_imagen):
    """
    Envía una imagen a 'numero_destino' usando un enlace público o un ID de media.
    Si tienes un ID de media subido a WhatsApp, puedes usar:
    "image": {"id": "<MEDIA_ID>"}
    En este ejemplo usamos 'link'.
    """
    url = f"https://graph.facebook.com/v22.0/{WHATSAPP_PHONE_NUMBER_ID 
}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": numero_destino,
        "type": "image",
        "image": {"link": enlace_imagen}
    }

    response = requests.post(url, headers=headers, json=data)
    return response.json()


def enviar_mensaje_y_foto(numero_destino, texto, enlace_imagen):
    """
    Envía primero un mensaje de texto y luego una imagen a 'numero_destino'.
    """
    print("Enviando mensaje de texto...")
    respuesta_texto = enviar_mensaje_texto(numero_destino, texto)
    print("Respuesta del envío de texto:", respuesta_texto)

    print("Enviando imagen...")
    respuesta_imagen = enviar_imagen(numero_destino, enlace_imagen)
    print("Respuesta del envío de imagen:", respuesta_imagen)


if __name__ == "__main__":
    # Cambia el número y el contenido a lo que necesites
    numero_destino = "34650776662"  # con código de país, sin espacios ni signos
    texto = "Hola, esto es un mensaje de prueba desde mi script en Python."
    # Usa una URL de imagen disponible públicamente (HTTPS)
    enlace_imagen = "https://fastly.picsum.photos/id/568/200/300.jpg?hmac=vQmkZRQt1uS-LMo2VtIQ7fn08mmx8Fz3Yy3lql5wkzM"

    enviar_mensaje_y_foto(numero_destino, texto, enlace_imagen)