# web/utils/image_compare.py
import os
import base64
import json
from openai import OpenAI

# El cliente leerá OPENAI_API_KEY de las variables de entorno si no se proporciona explícitamente.
client = OpenAI()

def _read_image_as_data_uri(path):
    """
    Devuelve 'data:image/<ext>;base64,<...>' o lanza FileNotFoundError.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"No existe el fichero de imagen: {path}")

    ext = os.path.splitext(path)[1].lower().lstrip(".")
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext or "jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/{mime};base64,{b64}"

def compare_images_with_gpt5(path1, path2, model="gpt-5"):
    """
    Compara dos imágenes usando GPT-5. Devuelve un diccionario con campos interpretables.
    """
    img1 = _read_image_as_data_uri(path1)
    img2 = _read_image_as_data_uri(path2)

    # Prompt: pedimos salida JSON con campos concretos para parsear fácilmente
    system_prompt = (
        "Eres un asistente que compara imágenes de mascotas. "
        "Devuelve SOLO JSON valido con las claves: "
        "same_animal (true/false), confidence (0..1), reason (texto breve), "
        "likely_breed1 (texto o null), likely_breed2 (texto o null)."
    )

    user_text = (
        "Compara estas dos fotografías. Indica si probablemente son del mismo animal, "
        "tu nivel de confianza entre 0 y 1, una razón breve y la raza más probable para cada foto."
    )

    # Construimos la petición multimodal: texto + dos imágenes (data URIs)
    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
            {"role": "user", "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": img1},
                {"type": "image_url", "image_url": img2}
            ]}
        ],
        # Opcional: limitar tokens/resumen o pedir formato conciso
        max_output_tokens=500,
        temperature=0.0
    )

    # El campo de salida puede variar según versión del cliente; este bloque intenta extraer texto
    out_text = None
    try:
        # algunas versiones devuelven response.output[0].content[0].text
        out_el = response.output[0].content[0]
        out_text = out_el.get("text") or out_el.get("markdown") or out_el.get("payload") or None
    except Exception:
        # fallback: stringify todo
        out_text = str(response)

    # Intentamos parsear JSON del texto devuelto (por si el modelo devolvió JSON)
    # Primero buscar la primera llave "{" para cortar cualquier prefacio.
    if isinstance(out_text, str):
        idx = out_text.find("{")
        if idx != -1:
            maybe_json = out_text[idx:]
        else:
            maybe_json = out_text

        try:
            parsed = json.loads(maybe_json)
            return {"ok": True, "result": parsed, "raw": out_text}
        except json.JSONDecodeError:
            # si no es JSON, devolvemos el texto crudo
            return {"ok": False, "raw": out_text, "note": "No se pudo parsear JSON de la respuesta."}
    else:
        return {"ok": False, "raw": repr(out_text), "note": "Respuesta inesperada del API."}
