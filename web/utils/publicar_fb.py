"""
Publicación de mensajes y fotos en el feed de la página de Facebook.

Requiere como mínimo las variables de entorno:
    - PAGE_ACCESS_TOKEN (token de la página con permisos pages_manage_posts,
      pages_show_list y pages_read_engagement).
    - FACEBOOK_PAGE_ID (ID numérico de la página).
"""

import json
import os
from io import BytesIO
from typing import Dict, Any, Iterable, Mapping, Optional, Sequence, Tuple, Union

import requests
from flask import current_app

PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
if not PAGE_ACCESS_TOKEN:
    raise RuntimeError("Falta la variable de entorno PAGE_ACCESS_TOKEN")

FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
if not FACEBOOK_PAGE_ID:
    raise RuntimeError("Falta la variable de entorno FACEBOOK_PAGE_ID")

GRAPH_API_VERSION = "v18.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
GRAPH_API_FEED = f"{GRAPH_API_BASE}/{FACEBOOK_PAGE_ID}/feed"
GRAPH_API_PHOTOS = f"{GRAPH_API_BASE}/{FACEBOOK_PAGE_ID}/photos"

MAX_TEXT_LENGTH = 63_000  # límite aproximado admitido por el feed

DatosType = Union[Mapping[str, object], Sequence[Tuple[str, object]]]


def formatear_valor(valor) -> str:
    """
    Convierte un valor al formato de texto que usamos en los correos/post.
    - valor: objeto de cualquier tipo (datetime, date, None, etc.).
    - return: cadena legible; fechas formateadas o "N/D" si está vacío.
    """
    from datetime import date, datetime

    if valor is None or valor == "":
        return "N/D"
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y %H:%M")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    return str(valor)


def construir_texto_post(subject: str, datos: DatosType) -> str:
    """
    Genera el cuerpo del post con el mismo formato del correo.
    - subject: título o asunto.
    - datos: dict o secuencia (campo, valor).
    - return: cadena con formato final.
    """
    if isinstance(datos, Mapping):
        items = list(datos.items())
    else:
        items = list(datos)

    cuerpo = [subject, "", "Datos de la mascota:", "--------------------"]
    for clave, valor in items:
        cuerpo.append(f"{clave}: {formatear_valor(valor)}")
    cuerpo.append("")
    cuerpo.append("Este mensaje se generó automáticamente desde Web Mascotas.")

    texto = "\n".join(cuerpo)
    if len(texto) > MAX_TEXT_LENGTH:
        raise ValueError(
            f"El texto resultante supera el límite permitido ({MAX_TEXT_LENGTH} caracteres)."
        )
    return texto


def _post_to_graph(
    url: str,
    payload: dict | None = None,
    files: dict | None = None,
    use_json: bool = False,
):
    params = {"access_token": PAGE_ACCESS_TOKEN}

    data = payload if payload and not use_json else None
    json_data = payload if payload and use_json else None
    files_data = files if files is not None else None

    response = requests.post(
        url,
        params=params,
        data=data,
        json=json_data,
        files=files_data,
        timeout=15,
    )

    print("[FB] POST", url, "status", response.status_code)

    if response.status_code >= 400:
        raise requests.HTTPError(
            f"{response.status_code} {response.reason}: {response.text}",
            response=response,
        )
    return response.json()


def _upload_photo_url(image_url: str, published: bool = False) -> str:
    """
    Sube una foto al álbum de la página usando una URL pública.
    - image_url: URL accesible de la imagen.
    - published: False para reutilizarla después en un post.
    - return: media_fbid asignado por Facebook.
    """
    payload = {
        "url": image_url,
        "published": "true" if published else "false",
        "temporary": "false" if published else "true",
    }
    data = _post_to_graph(GRAPH_API_PHOTOS, payload=payload)
    return data["id"]


def _upload_photo_bytes(
    data_bytes: bytes,
    nombre_archivo: str,
    mime_type: str | None = None,
    published: bool = False,
) -> str:
    """
    Sube una foto a partir de datos binarios (los que vienen de PostgreSQL).
    """
    payload = {
        "published": "true" if published else "false",
        "temporary": "false" if published else "true",
    }

    mime = mime_type or "application/octet-stream"
    buffer = BytesIO(data_bytes)
    files = {"source": (nombre_archivo, buffer, mime)}
    data = _post_to_graph(GRAPH_API_PHOTOS, payload=payload, files=files)
    return data["id"]


def _resolver_media_ids(fotos: Optional[Iterable[Dict[str, Any]]]) -> list[str]:
    """
    Procesa la colección de fotos (diccionarios provenientes de `_obtener_rutas_fotos`)
    y devuelve sus media IDs (tras subirlas sin publicarlas).
    """
    media_ids: list[str] = []

    for foto in fotos or []:
        data_bytes = foto.get("data")
        mime_type = foto.get("mime_type") or "application/octet-stream"
        nombre_archivo = foto.get("nombre_archivo") or f"foto_{foto.get('id', 'sin_id')}.jpg"
        url_publica = foto.get("url")

        if data_bytes:
            try:
                # Convertir memoryview a bytes si hace falta
                if isinstance(data_bytes, memoryview):
                    data_bytes = data_bytes.tobytes()
                media_id = _upload_photo_bytes(data_bytes, nombre_archivo, mime_type, published=False)
                print(f"[FB] Foto binaria (id={foto.get('id')}) -> media_id {media_id}")
                media_ids.append(media_id)
                continue
            except Exception as exc:  # pylint: disable=broad-except
                print(f"[FB] ⚠️ Error subiendo foto binaria (id={foto.get('id')}): {exc}")

        if url_publica:
            try:
                url_abs = _asegurar_url_absoluta(url_publica)
                media_id = _upload_photo_url(url_abs, published=False)
                print(f"[FB] Foto URL {url_abs} -> media_id {media_id}")
                media_ids.append(media_id)
                continue
            except Exception as exc:  # pylint: disable=broad-except
                print(f"[FB] ⚠️ Error subiendo foto desde URL {url_publica}: {exc}")

        print(f"[FB] ⚠️ Foto sin datos utilizables; se omite (id={foto.get('id')}).")

    return media_ids


def _asegurar_url_absoluta(url_relativa: str) -> str:
    """
    Convierte una URL relativa (p. ej. '/foto/5') en absoluta usando EXTERNAL_BASE_URL.
    Si ya es absoluta, la devuelve tal cual.
    """
    if url_relativa.startswith(("http://", "https://")):
        return url_relativa

    base = current_app.config.get("EXTERNAL_BASE_URL") or "http://127.0.0.1:5000"
    if not url_relativa.startswith("/"):
        url_relativa = "/" + url_relativa
    return base.rstrip("/") + url_relativa


def publish_pet_fb_post(
    subject: str,
    datos: DatosType,
    fotos: Optional[Iterable[Dict[str, Any]]] = None,
) -> bool:
    """
    Publica en el feed de la página un mensaje con el mismo formato del correo.
    - subject: título o encabezado del post.
    - datos: dict o lista de pares (campo, valor).
    - fotos: iterable de diccionarios retornados por `_obtener_rutas_fotos`.
             Se suben a Facebook en base a sus binarios (o URL pública si aplica).
    - return: True si la publicación se creó correctamente, False si hubo error.
    """
    try:
        mensaje = construir_texto_post(subject, datos)
        media_ids = _resolver_media_ids(fotos)

        payload = {"message": mensaje}
        for idx, media_id in enumerate(media_ids):
            payload[f"attached_media[{idx}]"] = json.dumps(
                {"media_fbid": media_id},
                separators=(",", ":"),
            )

        print("[FB] Payload a feed:", payload)

        respuesta = _post_to_graph(GRAPH_API_FEED, payload=payload)

        print("[FB] Respuesta feed:", respuesta)

        return True

    except Exception as exc:  # pylint: disable=broad-except
        print("[FB] ❌ Error publicando:", exc)
        if hasattr(exc, "response") and exc.response is not None:
            print("[FB] ❌ Respuesta completa:", exc.response.text)
        return False