"""
Utilidad para identificar (estimativamente) la raza de un animal en una o varias
fotos mediante el modelo visual de OpenAI.

Lo que espera:
    - Una ruta (str) o una colección (lista, tupla, etc.) de hasta 5 rutas de
      imágenes (absolutas o relativas) que existan en disco.

Lo que devuelve:
    - Un diccionario con las claves:
        * ok (bool): True si la consulta se completó sin excepciones.
        * mensaje (str): Respuesta textual completa del modelo.
        * raza (str | None): Raza detectada si se pudo extraer del texto.
        * raw (str | None): Copia del texto bruto (para futuras inspecciones).

Nota:
    El resto de funciones internas (_resolver_ruta, etc.) siguen funcionando
    igual que antes; solo se ha ampliado la función pública para manejar varias
    imágenes en la misma llamada, replicando la lógica que ya usamos en
    comparar_fotos.py.
"""

from __future__ import annotations

import base64
import os
import re
from typing import Dict, Optional, Sequence

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

def identificar_raza(paths_fotos: str | Sequence[str]) -> Dict[str, object]:
    """
    Intenta identificar la raza del animal presente en una o varias imágenes.

    Parameters
    ----------
    paths_fotos : str o Sequence[str]
        Ruta (absoluta o relativa) de la foto a evaluar, o colección de rutas.
        Se admiten hasta 5 imágenes por llamada.

    Returns
    -------
    dict
        Estructura con las claves:
            - ok (bool): indica si la operación se realizó sin excepciones.
            - mensaje (str): texto devuelto por el modelo (explicación completa).
            - raza (str | None): raza detectada (si fue posible parsearla).
            - raw (str | None): texto original por si se quiere analizar después.

    Raises
    ------
    ValueError
        Si no se recibe ninguna ruta o si se supera el máximo permitido (5).
    """
    # ------------------------------------------------------------------
    # Conversión y validación de entradas (antes solo admitíamos un str).
    # ------------------------------------------------------------------
    if isinstance(paths_fotos, str):
        rutas = [paths_fotos]
    else:
        rutas = list(paths_fotos or [])

    if not rutas:
        raise ValueError("Debes proporcionar al menos una imagen para analizar.")

    if len(rutas) > 5:
        raise ValueError("Solo se admiten hasta 5 imágenes por consulta.")

    # ------------------------------------------------------------------
    # Resolución y transformación a data URLs (nuevo soporte a múltiples fotos).
    # ------------------------------------------------------------------
    rutas_absolutas = [_resolver_ruta(ruta) for ruta in rutas]
    data_urls = [_image_to_data_url(ruta) for ruta in rutas_absolutas]

    # ------------------------------------------------------------------
    # Mensaje estilo comparar_fotos: texto inicial + cada imagen como image_url.
    # ------------------------------------------------------------------
    contenido = [
        {
            "type": "text",
            "text": (
                "Te enviaré hasta cinco imágenes de un animal (puede ser el mismo "
                "o más de uno). Identifica la raza o razas posibles presentes en "
                "estas imágenes. Si no es posible determinarla con certeza, da la "
                "mejor aproximación y explica brevemente tu razonamiento."
            ),
        }
    ]
    for data_url in data_urls:
        contenido.append({"type": "image_url", "image_url": {"url": data_url}})

    mensajes = [{"role": "user", "content": contenido}]

    try:
        cliente = _identificar_raza()
        respuesta = cliente.chat.completions.create(
            model="gpt-5",
            messages=mensajes,
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
            "Error al identificar la raza en %s: %s", rutas, exc
        )
        return {
            "ok": False,
            "mensaje": f"Error al identificar la raza: {exc}",
            "raza": None,
            "raw": None,
        }