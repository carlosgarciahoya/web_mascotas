import os
import requests
import time

API = "https://graph.facebook.com/v18.0"
IMAGE_URL = "https://buscarmascotas-com.onrender.com/foto/63.jpg"
CAPTION = "Publicación de prueba desde la web buscarmascotas.com 📸"

IG_USER_ID = os.environ.get("IG_USER_ID")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
if not IG_USER_ID or not ACCESS_TOKEN:
    raise SystemExit("Faltan IG_USER_ID o ACCESS_TOKEN en el entorno.")

# opcional: comprobar que la URL devuelve 200 y es JPEG
head = requests.head(IMAGE_URL, timeout=10)
head.raise_for_status()
print("URL OK:", head.status_code, head.headers.get("Content-Type"))

# Crear contenedor en IG usando tu propia URL
r1 = requests.post(
    f"{API}/{IG_USER_ID}/media",
    data={
        "image_url": IMAGE_URL,
        "caption": CAPTION,
        "access_token": ACCESS_TOKEN,
    },
    timeout=20,
)
print("status:", r1.status_code, "body:", r1.text)
r1.raise_for_status()
creation_id = r1.json()["id"]

# Publicar
time.sleep(5)
r2 = requests.post(
    f"{API}/{IG_USER_ID}/media_publish",
    data={"creation_id": creation_id, "access_token": ACCESS_TOKEN},
    timeout=20,
)
print("status:", r2.status_code, "body:", r2.text)
r2.raise_for_status()
print("Publicación realizada:", r2.json())