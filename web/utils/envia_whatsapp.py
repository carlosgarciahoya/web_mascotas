import requests
import requests
from flask import current_app

def send_pet_whatsapp(numero_destino: str, texto: str, link_foto: str | None = None) -> bool:
    """
    Envía un WhatsApp con 'texto' y, si se especifica, una foto (por enlace público).
    Devuelve True si la API responde OK, False si algo falla.
    """
    # Carga config desde variables de entorno (igual que con el correo)
    token = current_app.config.get("WHATSAPP_TOKEN")           # ej. System User Token
    phone_number_id = current_app.config.get("WHATSAPP_PHONE_NUMBER_ID")  # ID interno de Meta

    if not token or not phone_number_id:
        current_app.logger.error("Faltan WHATSAPP_TOKEN o WHATSAPP_PHONE_NUMBER_ID.")
        return False

    url = f"https://graph.facebook.com/v22.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # 1) Enviar texto
    data_texto = {
        "messaging_product": "whatsapp",
        "to": numero_destino,  # ej. "34650776662"
        "type": "text",
        "text": {"body": texto},
    }
    resp_texto = requests.post(url, headers=headers, json=data_texto)
    if resp_texto.status_code >= 400:
        current_app.logger.error("Error enviando texto WhatsApp: %s", resp_texto.text)
        return False

    # 2) Enviar foto (opcional)
    if link_foto:
        data_foto = {
            "messaging_product": "whatsapp",
            "to": numero_destino,
            "type": "image",
            "image": {"link": link_foto},
        }
        resp_foto = requests.post(url, headers=headers, json=data_foto)
        if resp_foto.status_code >= 400:
            current_app.logger.error("Error enviando foto WhatsApp: %s", resp_foto.text)
            return False

    return True


