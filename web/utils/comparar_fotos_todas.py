"""
Herramientas para comparar conjuntos de fotos (hasta 5 por mascota) utilizando
el modelo visual de OpenAI.

La función pública `comparar_fotos_todas(paths_a, paths_b)` recibe listas de
rutas (absolutas o relativas), data-URIs o bytes de las imágenes a comparar
y devuelve un diccionario con el resultado textual y, si es posible, un
porcentaje de similitud.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
from typing import Dict, Iterable, List, Optional, Union

from flask import current_app
from openai import OpenAI


# ---------------------------------------------------------------------------
# Utilidades internas comunes
# ---------------------------------------------------------------------------

def _get_client() -> OpenAI:
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
    Resuelve una ruta de fichero (absoluta o relativa) a una ruta absoluta existente.
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
    Convierte un fichero de imagen a data-URI.
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


def _a_data_url(item: Union[str, bytes, bytearray]) -> str:
    """
    Convierte la entrada a data-URI. Acepta:
      - cadenas que ya sean data:image/...
      - rutas de fichero existentes (absolutas o relativas)
      - bytes/bytearray con datos de imagen (mime por defecto image/jpeg)
    """
    if isinstance(item, str):
        s = item.strip()
        if s.startswith("data:image"):
            return s
        # Si no es data-URI, tratamos como ruta
        ruta_abs = _resolver_ruta(s)
        return _image_to_data_url(ruta_abs)

    if isinstance(item, (bytes, bytearray)):
        mime = "image/jpeg"
        b64 = base64.b64encode(item).decode("utf-8")
        return f"data:{mime};base64,{b64}"

    raise ValueError(f"No se pudo procesar la imagen recibida: {item!r}")


def _extraer_score(texto: str) -> Optional[float]:
    if not texto:
        return None

    coincidencia = re.search(r"(\d{1,3})\s?%", texto)
    if coincidencia:
        score = int(coincidencia.group(1))
        if 0 <= score <= 100:
            return float(score)
    return None


def _normalizar_listado(rutas: Iterable[Union[str, bytes, bytearray]], max_items: int = 5) -> List[Union[str, bytes, bytearray]]:
    """
    Limpia la lista de entradas, acepta str/bytes/bytearray y limita a max_items.
    """
    rutas_limpias: List[Union[str, bytes, bytearray]] = [
        ruta for ruta in rutas
        if ruta and isinstance(ruta, (str, bytes, bytearray))
    ]
    if not rutas_limpias:
        raise ValueError("No se proporcionaron imágenes válidas.")
    if len(rutas_limpias) > max_items:
        rutas_limpias = rutas_limpias[:max_items]
    return rutas_limpias


def _construir_contenido(
    data_urls_a: List[str],
    data_urls_b: List[str],
    etiqueta_a: str,
    etiqueta_b: str,
) -> List[Dict[str, object]]:
    contenido = [
        {
            "type": "text",
            "text": (
                "Te envío varias fotografías: unas llevan el identificador "
                f"«{etiqueta_a}» y pertenecen al mismo animal; las otras llevan el "
                f"identificador «{etiqueta_b}» y pertenecen a otro animal. "
                "Tu tarea es analizar si se trata del mismo animal o de animales "
                "distintos. Devuelve tu respuesta en JSON con la forma:\n"
                'Devuelve un porcentaje aproximado de parecido en funcion de tu analisis (0-100) y una breve explicación.'
                '{"conclusion": "...", "porcentaje": 0-100, "explicacion": "..."} '
                "IMPORTANTE :  asegúrate de que si concluyes que no es el mismo animal el porcentaje sea bajo "
                "(cercano a 0), si concluyes que sí sea alto (cercano a 100) y si dudas, esté alrededor de 50."
            ),
        },
    ]

    for indice, data_url in enumerate(data_urls_a, start=1):
        contenido.append({
            "type": "text",
            "text": f"Identificador: {etiqueta_a} (foto {indice})",
        })
        contenido.append({
            "type": "image_url",
            "image_url": {"url": data_url},
        })

    for indice, data_url in enumerate(data_urls_b, start=1):
        contenido.append({
            "type": "text",
            "text": f"Identificador: {etiqueta_b} (foto {indice})",
        })
        contenido.append({
            "type": "image_url",
            "image_url": {"url": data_url},
        })

    return contenido


def _sanitizar_contenido_para_log(contenido: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """Devuelve una copia del contenido sustituyendo las data-urls por un marcador."""
    copia = []
    for item in contenido:
        if item.get("type") == "image_url":
            url = item.get("image_url", {}).get("url", "")
            copia.append({
                "type": "image_url",
                "image_url": {
                    "url": f"<data-url length={len(url)}>"
                },
            })
        else:
            copia.append(item)
    return copia


def _parsear_respuesta(texto: str) -> Dict[str, object]:
    if not texto:
        return {
            "mensaje": "",
            "score": None,
            "raw": "",
        }

    texto_limpio = texto.strip()
    try:
        datos = json.loads(texto_limpio)
        porcentaje = datos.get("porcentaje")
        if porcentaje is None and "score" in datos:
            porcentaje = datos["score"]
        if isinstance(porcentaje, str):
            try:
                porcentaje = float(porcentaje.replace(",", "."))
            except ValueError:
                porcentaje = None
        return {
            "mensaje": datos.get("explicacion") or datos.get("mensaje") or texto_limpio,
            "score": float(porcentaje) if isinstance(porcentaje, (int, float)) else None,
            "raw": texto_limpio,
            "json": datos,
        }
    except json.JSONDecodeError:
        return {
            "mensaje": texto_limpio,
            "score": _extraer_score(texto_limpio),
            "raw": texto_limpio,
            "json": None,
        }


# ---------------------------------------------------------------------------
# Función pública
# ---------------------------------------------------------------------------

def comparar_fotos_todas(
    paths_a: Iterable[Union[str, bytes, bytearray]],
    paths_b: Iterable[Union[str, bytes, bytearray]],
    etiqueta_a: str = "mascota-desaparecida",
    etiqueta_b: str = "mascota-encontrada",
) -> Dict[str, object]:
    paths_a_list = list(paths_a)
    paths_b_list = list(paths_b)

    try:
        rutas_a = _normalizar_listado(paths_a_list, max_items=5)
        rutas_b = _normalizar_listado(paths_b_list, max_items=5)
    except ValueError as exc:
        return {
            "ok": False,
            "mensaje": str(exc),
            "score": None,
            "raw": None,
            "json": None,
            "num_fotos_a": 0,
            "num_fotos_b": 0,
        }

    try:
        data_urls_a = [_a_data_url(x) for x in rutas_a]
        data_urls_b = [_a_data_url(x) for x in rutas_b]
    except (ValueError, FileNotFoundError) as exc:
        return {
            "ok": False,
            "mensaje": str(exc),
            "score": None,
            "raw": None,
            "json": None,
            "num_fotos_a": 0,
            "num_fotos_b": 0,
        }

    contenido = _construir_contenido(data_urls_a, data_urls_b, etiqueta_a, etiqueta_b)
    # Para depurar:
    # current_app.logger.debug(
    #     "[comparar_fotos_todas] Contenido a enviar a OpenAI: %s",
    #     json.dumps(_sanitizar_contenido_para_log(contenido), ensure_ascii=False, indent=2),
    # )

    try:
        cliente = _get_client()
        respuesta = cliente.chat.completions.create(
            model="gpt-5.2",
            messages=[{"role": "user", "content": contenido}],
        )
        texto = respuesta.choices[0].message.content or ""

        datos = _parsear_respuesta(texto)

        resultado = {
            "ok": True,
            "mensaje": datos["mensaje"],
            "score": datos["score"],
            "raw": datos["raw"],
            "json": datos.get("json"),
            "num_fotos_a": len(data_urls_a),
            "num_fotos_b": len(data_urls_b),
        }
        return resultado

    except Exception as exc:  # pylint: disable=broad-except
        current_app.logger.exception(
            "Error al comparar conjuntos de imágenes %s vs %s: %s",
            rutas_a,
            rutas_b,
            exc,
        )
        return {
            "ok": False,
            "mensaje": f"Error al comparar las imágenes: {exc}",
            "score": None,
            "raw": None,
            "json": None,
            "num_fotos_a": len(data_urls_a),
            "num_fotos_b": len(data_urls_b),
        }