import os
import time
import requests

API = "https://graph.facebook.com/v18.0"
# IMAGE_URL = "https://images.pexels.com/photos/1108099/pexels-photo-1108099.jpeg?auto=compress&cs=tinysrgb&w=1080"
IMAGE_URL = "https://buscarmascotas.com/foto/61?auto=compress&cs=tinysrgb&w=1080"
CAPTION = "Publicación de prueba desde la web buscarmascotas.com 📸"

IG_USER_ID = os.environ.get("IG_USER_ID")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")

if not IG_USER_ID or not ACCESS_TOKEN:
    raise SystemExit("Faltan IG_USER_ID o ACCESS_TOKEN en el entorno.")

# 1) Crear el contenedor en Instagram con la URL pública
r1 = requests.post(
    f"{API}/{IG_USER_ID}/media",
    data={
        "image_url": IMAGE_URL,
        "caption": CAPTION,
        "access_token": ACCESS_TOKEN,
    },
    timeout=20,
)
print("status:", r1.status_code)
print("body:", r1.text)
r1.raise_for_status()

creation_id = r1.json()["id"]
print("Contenedor creado:", creation_id)

# 2) Publicar el contenedor
time.sleep(5)
r2 = requests.post(
    f"{API}/{IG_USER_ID}/media_publish",
    data={
        "creation_id": creation_id,
        "access_token": ACCESS_TOKEN,
    },
    timeout=20,
)
print("status:", r2.status_code)
print("body:", r2.text)
r2.raise_for_status()

print("Publicación realizada:", r2.json())