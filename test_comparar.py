import os
from itertools import combinations
from openai import OpenAI

# Inicializa cliente con tu API key
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def _validar_url(recurso: str) -> str:
    """
    Devuelve la misma cadena si es una URL http/https o data:.
    Lanza ValueError en cualquier otro caso (no se admiten rutas locales).
    """
    if recurso.startswith(("http://", "https://", "data:")):
        return recurso
    raise ValueError(
        f"Solo se admiten URLs http/https o data:. Valor recibido: {recurso!r}"
    )

def identificar_raza(imagen_url: str) -> str:
    """
    Identifica la raza del perro en la imagen señalada por la URL.
    """
    try:
        url = _validar_url(imagen_url)
        mensajes = [
            {"type": "text", "text": "Identifica la raza del perro en esta imagen."},
            {"type": "image_url", "image_url": {"url": url}},
        ]
        respuesta = client.chat.completions.create(
            model="gpt-5.2",
            messages=[{"role": "user", "content": mensajes}]
        )
        return respuesta.choices[0].message.content
    except Exception as e:
        return f"Error: {e}"

def comparar_perros(imagen1_url: str, imagen2_url: str) -> str:
    """
    Compara dos imágenes (por URL) de perros y pide un porcentaje de match y explicación.
    """
    try:
        url1 = _validar_url(imagen1_url)
        url2 = _validar_url(imagen2_url)

        mensajes = [
            {
                "type": "text",
                "text": "¿Son el mismo perro o distintos? Da además un porcentaje aproximado de parecido (0-100%) y explica brevemente por qué."
            },
            {"type": "image_url", "image_url": {"url": url1}},
            {"type": "image_url", "image_url": {"url": url2}},
        ]

        respuesta = client.chat.completions.create(
            model="gpt-5.2",
            messages=[{"role": "user", "content": mensajes}]
        )
        return respuesta.choices[0].message.content

    except Exception as e:
        return f"Error: {e}"

# ------------------ Ejecución ------------------

if __name__ == "__main__":
    # Sustituye estos ejemplos por URLs reales (http/https o data:) de tus imágenes
    perros = [
        "https://tu-dominio.com/foto_perro1.jpg",
        "https://tu-dominio.com/foto_perro2.jpg",
        "https://tu-dominio.com/foto_perro3.jpg",
        "https://tu-dominio.com/foto_perro4.jpg",
    ]

    print("=== Identificación de razas ===")
    for p in perros:
        print(f"\n{p}:")
        raza = identificar_raza(p)
        print(raza)
        print("-" * 60)

    print("\n=== Comparaciones entre perros ===")
    pares = list(combinations(perros, 2))
    for idx, (p1, p2) in enumerate(pares, 1):
        print(f"\nComparación {idx}: {p1} vs {p2}")
        resultado = comparar_perros(p1, p2)
        print(resultado)
        print("-" * 60)