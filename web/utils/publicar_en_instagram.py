import os
import time
import requests

# este es el que conecta con routes.py con la funcion :  publicar_en_instagram

API = "https://graph.facebook.com/v18.0"
IG_USER_ID = os.environ["IG_USER_ID"]
ACCESS_TOKEN = os.environ["ACCESS_TOKEN"]

def _crear_contenedor_imagen(url, caption=None):
    resp = requests.post(
        f"{API}/{IG_USER_ID}/media",
        data={
            "image_url": url,
            "caption": caption or "",
            "access_token": ACCESS_TOKEN,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["id"]

def publicar_en_instagram(caption, fotos_urls):
    """
    Publica en IG. `fotos_urls` es una lista de URLs públicas.
    Si hay más de una, se publica como carrusel.
    """
    if not fotos_urls:
        raise ValueError("Debes proporcionar al menos una URL de foto.")

    if len(fotos_urls) == 1:
        creation_id = _crear_contenedor_imagen(fotos_urls[0], caption)
    else:
        # Crear contenedores hijo sin caption
        child_ids = [_crear_contenedor_imagen(url) for url in fotos_urls]

        # Crear contenedor CAROUSEL
        resp = requests.post(
            f"{API}/{IG_USER_ID}/media",
            data={
                "media_type": "CAROUSEL",
                "children": ",".join(child_ids),
                "caption": caption or "",
                "access_token": ACCESS_TOKEN,
            },
            timeout=10,
        )
        resp.raise_for_status()
        creation_id = resp.json()["id"]

    # Opcional: esperar un poco a que procese
    time.sleep(5)

    # Publicar
    resp_pub = requests.post(
        f"{API}/{IG_USER_ID}/media_publish",
        data={
            "creation_id": creation_id,
            "access_token": ACCESS_TOKEN,
        },
        timeout=10,
    )
    resp_pub.raise_for_status()
    return resp_pub.json()