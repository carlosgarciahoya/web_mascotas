"""
Utilidad para identificar (estimativamente) la raza de un animal en una foto
mediante el modelo visual de OpenAI.

La función pública `identificar_raza(path_foto)` recibe una ruta (absoluta o
relativa) a la imagen y devuelve un diccionario con el texto de respuesta y,
si se encuentra, un posible nombre de raza.
"""

from __future__ import annotations

import base64
import os
import re
from typing import Dict, Optional

from flask import current_app
from openai import OpenAI


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

def _identificar_raza() -> OpenAI:
    """
    Devuelve un cliente OpenAI inicializado con la API key definida en la
    configuración de Flask (`current_app.config["OPENAI_API_KEY"]`) o en la
    variable de entorno del mismo nombre.

    Raises
    ------
    ValueError
        Si no se encuentra la API key.
    """
    api_key = (
        current_app.config.get("OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )
    if not api_key:
        raise ValueError(
            "Falta OPENAI_API_KEY en la configuración o en las variables de entorno."
        )
    return OpenAI(api_key=api_key)


def _resolver_ruta(ruta: str) -> str:
    """
    Intenta convertir `ruta` en una ruta absoluta existente.

    Se aceptan rutas absolutas o relativas. Para las relativas se prueban,
    en este orden:
        1. Directorio configurado en `current_app.config["FOTOS_BASE_PATH"]`
        2. `current_app.static_folder`
        3. `current_app.instance_path`
        4. Carpeta raíz de la aplicación (`current_app.root_path`)

    Raises
    ------
    ValueError
        Si `ruta` está vacía.
    FileNotFoundError
        Si no se encuentra ningún archivo válido.
    """
    if not ruta:
        raise ValueError("Se recibió una ruta vacía o None.")

    if os.path.isabs(ruta) and os.path.isfile(ruta):
        return ruta

    candidatos = []

    base_config = current_app.config.get("FOTOS_BASE_PATH")
    if base_config:
        candidatos.append(os.path.join(base_config, ruta.lstrip("/")))

    if current_app.static_folder:
        candidatos.append(os.path.join(current_app.static_folder, ruta.lstrip("/")))

    candidatos.append(os.path.join(current_app.instance_path, ruta.lstrip("/")))
    candidatos.append(os.path.join(current_app.root_path, ruta.lstrip("/")))

    for candidato in candidatos:
        if os.path.isfile(candidato):
            return candidato

    raise FileNotFoundError(f"No se encontró la imagen solicitada: {ruta!r}")


def _image_to_data_url(path: str) -> str:
    """
    Convierte una ruta local en un data URL (base64) listo para enviarlo a OpenAI.

    Raises
    ------
    FileNotFoundError
        Si el archivo no existe.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No existe la imagen: {path}")

    nombre = os.path.basename(path).lower()
    if nombre.endswith(".png"):
        mime = "image/png"
    elif nombre.endswith((".jpg", ".jpeg")):
        mime = "image/jpeg"
    elif nombre.endswith(".gif"):
        mime = "image/gif"
    elif nombre.endswith(".webp"):
        mime = "image/webp"
    else:
        mime = "image/jpeg"

    with open(path, "rb") as archivo:
        contenido = archivo.read()

    b64 = base64.b64encode(contenido).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def _extraer_raza(texto: str) -> Optional[str]:
    """
    Intenta detectar el nombre de una raza dentro del texto.

    Se basa en expresiones como 'raza', 'podría ser un ...', etc.
    Si no se encuentra nada, devuelve None.
    """
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


# ---------------------------------------------------------------------------
# Función pública
# ---------------------------------------------------------------------------

def identificar_raza(path_foto: str) -> Dict[str, object]:
    """
    Intenta identificar la raza del animal presente en la imagen.

    Parameters
    ----------
    path_foto : str
        Ruta (absoluta o relativa) de la foto a evaluar.

    Returns
    -------
    dict
        Estructura con las claves:
            - ok (bool): indica si la operación se realizó sin excepciones.
            - mensaje (str): texto devuelto por el modelo (explicación completa).
            - raza (str | None): raza detectada (si fue posible parsearla).
            - raw (str | None): texto original por si se quiere analizar después.

    Notes
    -----
    - La función registra cualquier excepción en el logger de Flask.
    - Si falta la API key, lanza ValueError (para que el llamador maneje la configuración).
    """
    ruta = _resolver_ruta(path_foto)
    data_url = _image_to_data_url(ruta)

    mensajes = [
        {
            "type": "text",
            "text": (
                "te voy a enviar algunas fotos de una animal "
                "Identifica la raza (o razas posibles) del animal en esta imagen. "
                "Si no es posible determinarla, da la mejor aproximación y explica brevemente."
            ),
        },
        {"type": "image_url", "image_url": {"url": data_url}},
    ]

    try:
        cliente = _identificar_raza()
        respuesta = cliente.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": mensajes}],
        )
        texto = respuesta.choices[0].message.content or ""
        raza = _extraer_raza(texto)

        return {
            "ok": True,
            "mensaje": texto.strip(),
            "raza": raza,
            "raw": texto,
        }

    except Exception as exc:  # pylint: disable=broad-except
        current_app.logger.exception(
            "Error al identificar la raza en '%s': %s", path_foto, exc
        )
        return {
            "ok": False,
            "mensaje": f"Error al identificar la raza: {exc}",
            "raza": None,
            "raw": None,
        }