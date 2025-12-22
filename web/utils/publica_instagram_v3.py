import os
import time
import io
import requests
from PIL import Image  # pip install Pillow

API = "https://graph.facebook.com/v18.0"
IMAGE_URL = "https://buscarmascotas.com/foto/61"
CAPTION = "Publicación de prueba desde la web buscarmascotas.com 📸"

IG_USER_ID = os.environ.get("IG_USER_ID")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
if not IG_USER_ID or not ACCESS_TOKEN:
    raise SystemExit("Faltan IG_USER_ID o ACCESS_TOKEN en el entorno.")

def preparar_para_ig(url: str) -> bytes:
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content))
    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    if w > 1080:
        ratio = 1080 / float(w)
        img = img.resize((1080, int(h * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    return buf.getvalue()

def upload_tmpfiles(data: bytes) -> str:
    r = requests.post(
        "https://tmpfiles.org/api/v1/upload",
        files={"file": ("ig.jpg", data, "image/jpeg")},
        timeout=20,
    )
    r.raise_for_status()
    j = r.json()
    if j.get("status") not in ("ok", "success"):
        raise RuntimeError(f"Falló upload: {j}")
    url = j["data"]["url"]  # p.ej. http://tmpfiles.org/16572194/ig.jpg
    # Forzamos https porque IG no acepta http
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    # La URL directa de descarga en tmpfiles suele ser /dl/...
    url = url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
    return url

# Preparar la imagen optimizada
optimized = preparar_para_ig(IMAGE_URL)
print(f"Imagen optimizada: {len(optimized):,} bytes")

# Subir a hosting público
public_url = upload_tmpfiles(optimized)
print("URL pública:", public_url)

# Crear contenedor en IG
r1 = requests.post(
    f"{API}/{IG_USER_ID}/media",
    data={"image_url": public_url, "caption": CAPTION, "access_token": ACCESS_TOKEN},
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