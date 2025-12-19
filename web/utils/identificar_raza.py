"""
Utilidad para identificar (estimativamente) la raza de un animal en una o varias
fotos mediante el modelo visual de OpenAI.

Acepta:
    - URLs http/https públicas o data URLs (data:...),
      o una colección (lista, tupla, etc.) de hasta 5 de ellas.
      Si le pasas rutas locales o bytes, intentará convertirlas a data: URL.

Devuelve:
    - Un diccionario con las claves:
        * ok (bool): True si la consulta se completó sin excepciones.
        * mensaje (str): Respuesta textual completa del modelo.
        * raza (str | None): Raza detectada si se pudo extraer del texto.
        * raw (str | None): Copia del texto bruto.
"""
from __future__ import annotations

import base64
import mimetypes
import os
import re
from typing import Dict, Optional, Sequence, Union

from flask import current_app
from openai import OpenAI


def _get_client() -> OpenAI:
    api_key = current_app.config.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Falta OPENAI_API_KEY en la configuración o en las variables de entorno.")
    return OpenAI(api_key=api_key)


def _a_data_url(item: Union[str, bytes, bytearray]) -> str:
    """
    Convierte la entrada a data-URI. Acepta:
      - cadenas que ya sean data:image/...
      - URLs http/https públicas (se envían tal cual)
      - rutas de fichero existentes (absolutas o relativas)
      - bytes/bytearray con datos de imagen (mime por defecto image/jpeg)
    """
    if isinstance(item, str):
        s = item.strip()
        if s.startswith("data:image"):
            return s
        if s.startswith("http://") or s.startswith("https://"):
            return s
        # ruta local
        if os.path.isfile(s):
            mime = mimetypes.guess_type(s)[0] or "image/jpeg"
            with open(s, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode("utf-8")
            return f"data:{mime};base64,{b64}"
        raise ValueError(f"No se pudo procesar la imagen recibida: {item!r}")

    if isinstance(item, (bytes, bytearray)):
        mime = "image/jpeg"
        b64 = base64.b64encode(item).decode("utf-8")
        return f"data:{mime};base64,{b64}"

    raise ValueError(f"No se pudo procesar la imagen recibida: {item!r}")


def _extraer_raza(texto: str) -> Optional[str]:
    if not texto:
        return None
    patrones = [
        r"(?:raza|breed)\s*:?[\s\-]*(.+)",
        r"podría\s+ser\s+(?:un|una)\s+([a-záéíóúñ\s-]+)",
        r"parece\s+(?:un|una)\s+([a-záéíóúñ\s-]+)",
    ]
    for patron in patrones:
        coincidencia = re.search(patron, texto, flags=re.IGNORECASE)
        if coincidencia:
            raza = coincidencia.group(1).strip()
            raza = re.split(r"[.\n]", raza)[0].strip()
            if raza:
                return raza.title()
    return None


def identificar_raza(paths_fotos: str | Sequence[str]) -> Dict[str, object]:
    """
    Intenta identificar la raza del animal presente en una o varias imágenes.
    """
    if isinstance(paths_fotos, str):
        rutas = [paths_fotos]
    else:
        rutas = list(paths_fotos or [])

    if not rutas:
        raise ValueError("Debes proporcionar al menos una imagen para analizar.")
    if len(rutas) > 5:
        raise ValueError("Solo se admiten hasta 5 imágenes por consulta.")

    data_urls = [_a_data_url(ruta) for ruta in rutas]

    contenido = [{
        "type": "text",
        "text": (
            "Te enviaré hasta cinco imágenes de un animal (puede ser el mismo "
            "o más de uno). Identifica la raza o razas posibles presentes en "
            "estas imágenes. Si no es posible determinarla con certeza, da la "
            "mejor aproximación y explica brevemente tu razonamiento."
        ),
    }]
    for data_url in data_urls:
        contenido.append({"type": "image_url", "image_url": {"url": data_url}})

    try:
        cliente = _get_client()
        respuesta = cliente.chat.completions.create(
            model="gpt-5.2",
            messages=[{"role": "user", "content": contenido}],
        )
        texto = respuesta.choices[0].message.content or ""
        raza = _extraer_raza(texto)
        return {"ok": True, "mensaje": texto.strip(), "raza": raza, "raw": texto}
    except Exception as exc:  # pylint: disable=broad-except
        current_app.logger.exception("Error al identificar la raza en %s: %s", rutas, exc)
        return {"ok": False, "mensaje": f"Error al identificar la raza: {exc}", "raza": None, "raw": None}