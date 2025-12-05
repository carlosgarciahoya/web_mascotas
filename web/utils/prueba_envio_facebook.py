"""
Módulo para enviar información de mascotas vía Facebook Messenger.
Requiere las variables de entorno:
    - PAGE_ACCESS_TOKEN
    - PSID_DESTINO
"""

import json
import os
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence, Tuple, Union

import requests

# ------------------------------------------------------------------ #
# Configuración básica (variables obligatorias)
# ------------------------------------------------------------------ #
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
if not PAGE_ACCESS_TOKEN:
    raise RuntimeError("Falta la variable de entorno PAGE_ACCESS_TOKEN")

DEFAULT_PSID = os.getenv("PSID_DESTINO")
if not DEFAULT_PSID:
    raise RuntimeError("Falta la variable de entorno PSID_DESTINO")

GRAPH_API_VERSION = "v18.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
GRAPH_API_MESSAGES = f"{GRAPH_API_BASE}/me/messages"
GRAPH_API_ATTACHMENTS = f"{GRAPH_API_BASE}/me/message_attachments"

MAX_TEXT_LENGTH = 1900  # margen seguro para mensajes

DatosType = Union[Mapping[str, object], Sequence[Tuple[str, object]]]


def formatear_valor(valor) -> str:
    """
    Convierte un valor a cadena legible para el cuerpo del mensaje.
    - valor: cualquier tipo (datetime, date, None, etc.).
    - return: texto formateado con formato de fecha o "N/D" si es vacío.
    """
    from datetime import date, datetime

    if valor is None or valor == "":
        return "N/D"
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y %H:%M")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    return str(valor)


def extraer_ruta(objeto) -> Optional[str]:
    """
    Obtiene una ruta de archivo desde un objeto.
    - objeto: puede tener atributos ruta, path, filepath o file_path.
    - return: ruta en texto o None si no se encuentra.
    """
    return (
        getattr(objeto, "ruta", None)
        or getattr(objeto, "path", None)
        or getattr(objeto, "filepath", None)
        or getattr(objeto, "file_path", None)
    )


def dividir_texto(texto: str, max_len: int = MAX_TEXT_LENGTH) -> list[str]:
    """
    Divide un texto largo en fragmentos de longitud máxima.
    - texto: contenido completo a enviar.
    - max_len: tamaño máximo por fragmento.
    - return: lista de fragmentos respetando saltos de línea.
    """
    if len(texto) <= max_len:
        return [texto]

    partes: list[str] = []
    actual = ""

    for linea in texto.splitlines(keepends=True):
        if len(actual) + len(linea) > max_len and actual:
            partes.append(actual.rstrip("\n"))
            actual = ""
        actual += linea

    if actual:
        partes.append(actual.rstrip("\n"))

    return partes


def _post_to_graph(url: str, payload: dict | None = None, files: dict | None = None):
    """
    Envía una petición POST al Graph API.
    - url: endpoint completo.
    - payload: diccionario JSON para el cuerpo.
    - files: diccionario de archivos (multipart/form-data) o None.
    - return: respuesta decodificada como dict.
    """
    params = {"access_token": PAGE_ACCESS_TOKEN}
    response = requests.post(
        url,
        params=params,
        json=payload if files is None else None,
        data=payload if files is not None else None,
        files=files,
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def send_text(psid: str, text: str):
    """
    Envía un mensaje de texto (con saltos de línea).
    - psid: ID del destinatario.
    - text: contenido a enviar.
    - return: respuesta del Graph API.
    """
    payload = {"recipient": {"id": psid}, "message": {"text": text}}
    return _post_to_graph(GRAPH_API_MESSAGES, payload=payload)


def send_image_url(psid: str, image_url: str, reusable: bool = True):
    """
    Envía una imagen alojada en una URL pública.
    - psid: ID del destinatario.
    - image_url: URL accesible públicamente.
    - reusable: si se almacena como adjunto reutilizable.
    - return: respuesta del Graph API.
    """
    payload = {
        "recipient": {"id": psid},
        "message": {
            "attachment": {
                "type": "image",
                "payload": {"url": image_url, "is_reusable": reusable},
            }
        },
    }
    return _post_to_graph(GRAPH_API_MESSAGES, payload=payload)


def upload_attachment(file_path: str | Path, reusable: bool = True) -> str:
    """
    Sube un archivo local y devuelve el attachment_id.
    - file_path: ruta del archivo en disco.
    - reusable: si se marca como reutilizable.
    - return: attachment_id generado por Facebook.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {file_path}")

    with file_path.open("rb") as fb:
        files = {"filedata": (file_path.name, fb, "application/octet-stream")}
        payload = {
            "message": json.dumps(
                {
                    "attachment": {
                        "type": "image",
                        "payload": {"is_reusable": reusable},
                    }
                }
            )
        }
        data = _post_to_graph(GRAPH_API_ATTACHMENTS, payload=payload, files=files)
    return data["attachment_id"]


def send_image_local(psid: str, file_path: str | Path, reusable: bool = True):
    """
    Envía una imagen localizada en disco.
    - psid: ID del destinatario.
    - file_path: ruta absoluta del archivo.
    - reusable: si se marca como reutilizable.
    - return: respuesta del Graph API.
    """
    attachment_id = upload_attachment(file_path, reusable=reusable)
    payload = {
        "recipient": {"id": psid},
        "message": {
            "attachment": {
                "type": "image",
                "payload": {"attachment_id": attachment_id},
            }
        },
    }
    return _post_to_graph(GRAPH_API_MESSAGES, payload=payload)


def send_pet_fb_message(
    subject: str,
    datos: DatosType,
    fotos: Optional[Iterable[Union[str, object]]] = None,
    destinatarios_extra: Optional[Iterable[str]] = None,  # ignorado por ahora
) -> bool:
    """
    Envía a Facebook un mensaje equivalente al correo de mascotas.
    - subject: asunto o título del mensaje.
    - datos: dict o secuencia (campo, valor) para el cuerpo.
    - fotos: iterable de URLs o rutas/objetos con ruta de imagen.
    - destinatarios_extra: admitido por compatibilidad, ignorado.
    - return: True si se envió todo correctamente, False si hubo error.
    """
    try:
        # 1. Preparar el texto con el mismo formato que el correo
        if isinstance(datos, Mapping):
            items = list(datos.items())
        else:
            items = list(datos)

        cuerpo = [subject, "", "Datos de la mascota:", "--------------------"]
        for clave, valor in items:
            cuerpo.append(f"{clave}: {formatear_valor(valor)}")
        cuerpo.append("")
        cuerpo.append("Este mensaje se generó automáticamente desde Web Mascotas.")
        texto_total = "\n".join(cuerpo)

        # 2. Enviar texto (fragmentado si es necesario)
        for fragmento in dividir_texto(texto_total):
            send_text(DEFAULT_PSID, fragmento)

        # 3. Adjuntar fotos (URL o rutas locales)
        for foto in fotos or []:
            ruta = None
            if isinstance(foto, str):
                if foto.lower().startswith(("http://", "https://")):
                    send_image_url(DEFAULT_PSID, foto)
                    continue
                ruta = foto
            else:
                ruta = extraer_ruta(foto)

            if ruta and os.path.isfile(ruta):
                send_image_local(DEFAULT_PSID, ruta)
            elif ruta:
                print(f"⚠️ No se encontró la foto {ruta}; se omite.")

        return True

    except Exception as exc:  # pylint: disable=broad-except
        print(f"❌ Error enviando mensaje a Facebook: {exc}")
        return False