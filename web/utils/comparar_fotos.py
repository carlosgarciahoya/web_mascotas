"""
Herramientas para comparar dos fotos utilizando el modelo visual de OpenAI.

La función pública `comparar_fotos(path_a, path_b)` recibe rutas (absolutas o
relativas) de las imágenes a comparar y devuelve un diccionario con el
resultado textual y, si es posible, un porcentaje de similitud.
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

def _get_client() -> OpenAI:
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


def _extraer_score(texto: str) -> Optional[float]:
    """
    Intenta localizar un porcentaje en el texto de respuesta (por ejemplo: '85%').
    Devuelve el valor numérico (0-100) si lo encuentra, o None en caso contrario.
    """
    if not texto:
        return None

    coincidencia = re.search(r"(\d{1,3})\s?%", texto)
    if coincidencia:
        score = int(coincidencia.group(1))
        # Filtra valores fuera de rango por si el modelo devolviera algo extraño
        if 0 <= score <= 100:
            return float(score)
    return None


# ---------------------------------------------------------------------------
# Función pública
# ---------------------------------------------------------------------------

def comparar_fotos(path_a: str, path_b: str) -> Dict[str, object]:
    """
    Compara dos imágenes y pide al modelo de OpenAI un porcentaje y explicación.

    Parameters
    ----------
    path_a : str
        Ruta (absoluta o relativa) de la primera foto.
    path_b : str
        Ruta (absoluta o relativa) de la segunda foto.

    Returns
    -------
    dict
        Estructura con las claves:
            - ok (bool): indica si la comparación se realizó sin excepciones.
            - mensaje (str): texto devuelto por el modelo o el error.
            - score (float | None): porcentaje de similitud extraído si se detecta.
            - raw (str | None): texto original por si se quiere analizar después.

    Notes
    -----
    - La función registra cualquier excepción en el logger de Flask.
    - Si falta la API key, lanza ValueError (para que la vista sepa que es problema de configuración).
    """
    # Normaliza rutas y prepara data URLs
    ruta_a = _resolver_ruta(path_a)
    ruta_b = _resolver_ruta(path_b)

    data_a = _image_to_data_url(ruta_a)
    data_b = _image_to_data_url(ruta_b)

    # Contenido enviado al modelo
    mensajes = [
        {
            "type": "text",
            "text": (
                "Tu tarea es analizar si se trata del mismo animal o de animales distintos  "
                "Devuelve tu respuesta en JSON con la forma:\n"
                "Devuelve un porcentaje aproximado de parecido en funcion de tu analisis (0-100) y una breve explicación."
                '{"conclusion": "...", "porcentaje": 0-100, "explicacion": "..."} '
                "IMPORTANTE :  asegúrate de que si concluyes que no es el mismo animal el porcentaje sea bajo "
                "(cercano a 0), si concluyes que sí sea alto (cercano a 100) y si dudas, esté alrededor de 50."
           
            ),
        },
        {"type": "image_url", "image_url": {"url": data_a}},
        {"type": "image_url", "image_url": {"url": data_b}},
    ]

    try:
        cliente = _get_client()
        respuesta = cliente.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": mensajes}],
        )
        texto = respuesta.choices[0].message.content or ""
        score = _extraer_score(texto)

        return {
            "ok": True,
            "mensaje": texto.strip(),
            "score": score,
            "raw": texto,
        }

    except Exception as exc:  # pylint: disable=broad-except
        current_app.logger.exception(
            "Error al comparar imágenes '%s' vs '%s': %s", path_a, path_b, exc
        )
        return {
            "ok": False,
            "mensaje": f"Error al comparar las imágenes: {exc}",
            "score": None,
            "raw": None,
        }