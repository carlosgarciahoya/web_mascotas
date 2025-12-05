import os
from openai import OpenAI
import base64
from itertools import combinations

# Inicializa cliente con tu API key
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# ------------------ Funciones ------------------

def image_to_data_url(path):
    """
    Convierte una imagen local a Data URL (base64) para enviarla a GPT.
    """
    name = os.path.basename(path).lower()
    if name.endswith(".png"):
        mime = "image/png"
    elif name.endswith((".jpg", ".jpeg")):
        mime = "image/jpeg"
    elif name.endswith(".gif"):
        mime = "image/gif"
    elif name.endswith(".webp"):
        mime = "image/webp"
    else:
        mime = "image/jpeg"

    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def identificar_raza(imagen_path):
    """
    Identifica la raza del perro en la imagen.
    """
    try:
        data = image_to_data_url(imagen_path)
        mensajes = [
            {"type": "text", "text": "Identifica la raza del perro en esta imagen."},
            {"type": "image_url", "image_url": {"url": data}},
        ]
        respuesta = client.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": mensajes}]
        )
        return respuesta.choices[0].message.content
    except Exception as e:
        return f"Error: {e}"

def comparar_perros(imagen1_path, imagen2_path):
    """
    Compara dos imágenes de perros y pide un porcentaje de match y explicación.
    """
    try:
        data1 = image_to_data_url(imagen1_path)
        data2 = image_to_data_url(imagen2_path)

        mensajes = [
            {
                "type": "text",
                "text": "¿Son el mismo perro o distintos? Da además un porcentaje aproximado de parecido (0-100%) y explica brevemente por qué."
            },
            {"type": "image_url", "image_url": {"url": data1}},
            {"type": "image_url", "image_url": {"url": data2}},
        ]

        respuesta = client.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": mensajes}]
        )

        return respuesta.choices[0].message.content

    except Exception as e:
        return f"Error: {e}"

# ------------------ Ejecución ------------------

if __name__ == "__main__":
    # Lista de los 4 primeros perros
    perros = [f"fotos/perro{i}.jpg" for i in range(1, 5)]

    print("=== Identificación de razas ===")
    for p in perros:
        print(f"\n{os.path.basename(p)}:")
        raza = identificar_raza(p)
        print(raza)
        print("-" * 60)

    print("\n=== Comparaciones entre perros ===")
    # Todas las combinaciones de 2 perros
    pares = list(combinations(perros, 2))
    for idx, (p1, p2) in enumerate(pares, 1):
        print(f"\nComparación {idx}: {os.path.basename(p1)} vs {os.path.basename(p2)}")
        resultado = comparar_perros(p1, p2)
        print(resultado)
        print("-" * 60)
