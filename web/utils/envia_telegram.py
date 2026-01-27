import requests
from flask import current_app

def send_pet_telegram(chat_id: str, texto: str, link_foto: str | None = None) -> bool:
    """
    Envía un mensaje de texto (y opcionalmente una foto por URL pública)
    al chat_id que le pases. Devuelve True si todo sale bien, False si hay error.
    Usa:
      TELEGRAM_TOKEN -> el token de tu bot (BotFather)
      chat_id        -> lo pasas tú en cada llamada
    """
    token = current_app.config.get("TELEGRAM_TOKEN")
    if not token or not chat_id:
        current_app.logger.error("Falta TELEGRAM_TOKEN o chat_id.")
        return False

    # 1) Enviar texto
    url_msg = f"https://api.telegram.org/bot{token}/sendMessage"
    data_msg = {"chat_id": chat_id, "text": texto}
    resp_msg = requests.post(url_msg, data=data_msg)
    if resp_msg.status_code >= 400:
        current_app.logger.error("Error enviando texto a Telegram: %s", resp_msg.text)
        return False

    # 2) Enviar foto (opcional)
    if link_foto:
        url_photo = f"https://api.telegram.org/bot{token}/sendPhoto"
        data_photo = {"chat_id": chat_id, "photo": link_foto}
        resp_photo = requests.post(url_photo, data=data_photo)
        if resp_photo.status_code >= 400:
            current_app.logger.error("Error enviando foto a Telegram: %s", resp_photo.text)
            return False

    return True