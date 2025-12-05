import requests, time

API = "https://graph.facebook.com/v18.0"
IG_USER_ID = "17841478301161922"                 # instagram_business_account.id
ACCESS_TOKEN = "EAAXWEbgy8BwBQEc2CdSda8ZBJPEZCZBI3vwJY43neK13oNZCAbSfxme2OOlImJGgkdMckk13v9wYGBrD6x80gxFZBbTnypZCiyaJnfHjmwfrd7oShLDFOHZA1ffvtvku59s56Wo454u3UFp1YOPkIfjCAJT7yRZA6TVHPwWDhp3MCbcRUsiH9a0TOC5CGeSKdLlfQQCB"               # Page access token
IMAGE_URL = "https://images.pexels.com/photos/1108099/pexels-photo-1108099.jpeg?auto=compress&cs=tinysrgb&w=1080"
CAPTION = "Publicación de prueba desde la API 📸"
# 1) Crear contenedor
r1 = requests.post(
    f"{API}/{IG_USER_ID}/media",
    data={
        "image_url": IMAGE_URL,
        "caption": CAPTION,
        "access_token": ACCESS_TOKEN,
    },
)

print("status:", r1.status_code)
print("body:", r1.text)

# Si la llamada tuvo éxito, extraer el ID del contenedor
if r1.ok:
    creation_id = r1.json()["id"]
    print("Contenedor creado:", creation_id)
else:
    raise SystemExit("No se pudo crear el contenedor. Revisa el mensaje anterior.")

# 2) Esperar un poco (opcional, depende de tu caso)
time.sleep(5)

# 3) Publicar
r2 = requests.post(
    f"{API}/{IG_USER_ID}/media_publish",
    data={
        "creation_id": creation_id,
        "access_token": ACCESS_TOKEN,
    },
)

print("status:", r2.status_code)
print("body:", r2.text)

if r2.ok:
    print("Publicación realizada:", r2.json())
else:
    raise SystemExit("No se pudo publicar la imagen. Revisa el mensaje anterior.")