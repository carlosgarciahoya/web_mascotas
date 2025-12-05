import os
import requests
from dotenv import load_dotenv

# Carga las variables definidas en el archivo .env
load_dotenv()

PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN")  # nombre de la variable que añadiste con setx
GRAPH_API_URL = "https://graph.facebook.com/v18.0/me/messages"


class MessengerClient:
    """
    Cliente sencillo para enviar mensajes de texto a través de la API de Facebook Messenger.
    """

    def __init__(self, page_access_token: str = PAGE_ACCESS_TOKEN):
        if not page_access_token:
            raise ValueError(
                "No se encontró FB_PAGE_ACCESS_TOKEN. "
                "Configura la variable de entorno o usa un .env."
            )
        self.page_access_token = page_access_token

    def send_text_message(self, recipient_psid: str, text: str) -> dict:
        """
        Envía un mensaje de texto a un usuario identificado por su PSID.
        Devuelve el JSON de respuesta que envía Facebook.
        """
        payload = {
            "recipient": {"id": recipient_psid},
            "message": {"text": text}
        }
        params = {"access_token": self.page_access_token}

        response = requests.post(
            GRAPH_API_URL,
            params=params,
            json=payload,
            timeout=10
        )
        response.raise_for_status()  # lanza error si la respuesta no es 200 OK
        return response.json()