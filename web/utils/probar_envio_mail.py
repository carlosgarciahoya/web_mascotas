import os
import sys
from datetime import date

from flask import Flask, current_app

# ---------------------------------------------------------------------------
# Ajustamos sys.path para que Python encuentre el paquete 'web'
# (subimos dos niveles: utils -> web -> web_mascotas)
# ---------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from web.utils.envia_mail import send_pet_email  # noqa: E402

# ---------------------------------------------------------------------------
# Creamos una app Flask mínima y cargamos la configuración SMTP de entorno
# ---------------------------------------------------------------------------
def crear_app_de_pruebas() -> Flask:
    app = Flask(__name__)
    app.config["SMTP_SERVER"] = os.getenv("SMTP_SERVER", "")
    app.config["SMTP_PORT"] = int(os.getenv("SMTP_PORT", "587"))
    app.config["SMTP_USERNAME"] = os.getenv("SMTP_USERNAME", "")
    app.config["SMTP_PASSWORD"] = os.getenv("SMTP_PASSWORD", "")
    app.config["SMTP_TO_EMAIL"] = os.getenv("SMTP_TO_EMAIL", "")
    return app


# ---------------------------------------------------------------------------
# Datos de prueba (los mismos que me proporcionaste)
# ---------------------------------------------------------------------------
REGISTROS = [
    {
        "subject": "Mascota desaparecida",
        "datos": {
            "ID": 1,
            "Tipo de registro": "desaparecida",
            "Nombre": "Firulais",
            "Especie": "Perro",
            "Raza": "Labrador",
            "Edad": 3,
            "Zona": "Centro",
            "Email contacto": "juan@example.com",
            "Teléfono contacto": "600000001",
            "Color": "marrón",
            "Sexo": "macho",
            "Chip": "123456789012345",
            "Peso": 28.5,
            "Tamaño": "grande",
            "Descripción": "Labrador con collar rojo.",
            "Fecha registro": date(2025, 10, 1),
            "Fecha aparecida": None,
            "Estado aparecida": None,
        },
        "fotos": [
            r"c:\Users\CGH\Documents\web_mascotas\web\static\fotos\frontal4.jpg",
        ],
    },
    {
        "subject": "Mascota encontrada",
        "datos": {
            "ID": 2,
            "Tipo de registro": "encontrada",
            "Nombre": "Michi",
            "Especie": "Gato",
            "Raza": "Siamés",
            "Edad": 2,
            "Zona": "Norte",
            "Email contacto": "ana@example.com",
            "Teléfono contacto": "600000002",
            "Color": "crema",
            "Sexo": "hembra",
            "Chip": None,
            "Peso": 4.2,
            "Tamaño": "pequeño",
            "Descripción": "Con cascabel azul.",
            "Fecha registro": date(2025, 10, 2),
            "Fecha aparecida": None,
            "Estado aparecida": None,
        },
        "fotos": [],
    },
    {
        "subject": "Mascota desaparecida",
        "datos": {
            "ID": 3,
            "Tipo de registro": "desaparecida",
            "Nombre": "Rocky",
            "Especie": "Perro",
            "Raza": "Pastor Alemán",
            "Edad": 4,
            "Zona": "Este",
            "Email contacto": "luis@example.com",
            "Teléfono contacto": "600000003",
            "Color": "negro y fuego",
            "Sexo": "macho",
            "Chip": None,
            "Peso": 32.0,
            "Tamaño": "grande",
            "Descripción": "",
            "Fecha registro": date(2025, 10, 3),
            "Fecha aparecida": None,
            "Estado aparecida": None,
        },
        "fotos": [
            r"c:\Users\CGH\Documents\web_mascotas\web\static\fotos\frontal1.jpg",
        ],
    },
    {
        "subject": "Mascota encontrada",
        "datos": {
            "ID": 4,
            "Tipo de registro": "encontrada",
            "Nombre": "Luna",
            "Especie": "Gato",
            "Raza": "Común",
            "Edad": 1,
            "Zona": "Oeste",
            "Email contacto": "marta@example.com",
            "Teléfono contacto": "600000004",
            "Color": "atigrado",
            "Sexo": "hembra",
            "Chip": None,
            "Peso": 3.8,
            "Tamaño": "pequeño",
            "Descripción": "Muy cariñosa.",
            "Fecha registro": date(2025, 10, 4),
            "Fecha aparecida": None,
            "Estado aparecida": None,
        },
        "fotos": [],
    },
    {
        "subject": "Mascota desaparecida",
        "datos": {
            "ID": 5,
            "Tipo de registro": "desaparecida",
            "Nombre": "Toby",
            "Especie": "Perro",
            "Raza": "Beagle",
            "Edad": 5,
            "Zona": "Centro",
            "Email contacto": "pablo@example.com",
            "Teléfono contacto": "600000005",
            "Color": "tricolor",
            "Sexo": "macho",
            "Chip": None,
            "Peso": 12.5,
            "Tamaño": "mediano",
            "Descripción": "",
            "Fecha registro": date(2025, 10, 5),
            "Fecha aparecida": None,
            "Estado aparecida": None,
        },
        "fotos": [
            r"c:\Users\CGH\Documents\web_mascotas\web\static\fotos\lateral1.jpg",
        ],
    },
    {
        "subject": "Mascota encontrada",
        "datos": {
            "ID": 6,
            "Tipo de registro": "encontrada",
            "Nombre": "Nala",
            "Especie": "Perro",
            "Raza": "Mestizo",
            "Edad": 2,
            "Zona": "Sur",
            "Email contacto": "sofia@example.com",
            "Teléfono contacto": "600000006",
            "Color": "blanco",
            "Sexo": "hembra",
            "Chip": None,
            "Peso": 10.0,
            "Tamaño": "mediano",
            "Descripción": "",
            "Fecha registro": date(2025, 10, 6),
            "Fecha aparecida": None,
            "Estado aparecida": None,
        },
        "fotos": [],
    },
    {
        "subject": "Mascota desaparecida",
        "datos": {
            "ID": 7,
            "Tipo de registro": "desaparecida",
            "Nombre": "Coco",
            "Especie": "Gato",
            "Raza": "Maine Coon",
            "Edad": 3,
            "Zona": "Norte",
            "Email contacto": "raul@example.com",
            "Teléfono contacto": "600000007",
            "Color": "gris",
            "Sexo": "macho",
            "Chip": None,
            "Peso": 6.5,
            "Tamaño": "mediano",
            "Descripción": "",
            "Fecha registro": date(2025, 10, 7),
            "Fecha aparecida": None,
            "Estado aparecida": None,
        },
        "fotos": [
            r"c:\Users\CGH\Documents\web_mascotas\web\static\fotos\lateral2.jpg",
        ],
    },
    {
        "subject": "Mascota encontrada",
        "datos": {
            "ID": 8,
            "Tipo de registro": "encontrada",
            "Nombre": "Bella",
            "Especie": "Perro",
            "Raza": "Pomerania",
            "Edad": 1,
            "Zona": "Centro",
            "Email contacto": "laura@example.com",
            "Teléfono contacto": "600000008",
            "Color": "naranja",
            "Sexo": "hembra",
            "Chip": None,
            "Peso": 2.8,
            "Tamaño": "pequeño",
            "Descripción": "",
            "Fecha registro": date(2025, 10, 8),
            "Fecha aparecida": None,
            "Estado aparecida": None,
        },
        "fotos": [],
    },
]

# ---------------------------------------------------------------------------
# Envío de los correos de prueba
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = crear_app_de_pruebas()

    with app.app_context():
        desaparecidos_previos = []

        cfg = current_app.config
        base_destinatarios = [
            correo.strip()
            for correo in str(cfg.get("SMTP_TO_EMAIL", "")).split(",")
            if correo.strip()
        ]
        correo_extra_fijo = "encontrar.mi.mascota@gmail.com"
        if correo_extra_fijo and correo_extra_fijo not in base_destinatarios:
            base_destinatarios.append(correo_extra_fijo)

        for idx, registro in enumerate(REGISTROS, start=1):
            datos = registro["datos"]
            tipo = str(datos.get("Tipo de registro", "")).strip().lower()
            nombre = datos.get("Nombre", "¿sin nombre?")
            email_contacto = datos.get("Email contacto")

            if tipo not in {"desaparecida", "encontrada"}:
                tipo = "desconocido"

            destinatarios_extra = []

            if tipo == "desaparecida":
                if email_contacto:
                    destinatarios_extra = [email_contacto]
                    if email_contacto not in desaparecidos_previos:
                        desaparecidos_previos.append(email_contacto)
                else:
                    current_app.logger.warning(
                        "Registro 'desaparecida' sin email de contacto: %s (ID %s)",
                        nombre,
                        datos.get("ID"),
                    )

            elif tipo == "encontrada":
                destinatarios_extra = list(desaparecidos_previos)
                if email_contacto:
                    if email_contacto not in destinatarios_extra:
                        destinatarios_extra.append(email_contacto)
                else:
                    current_app.logger.warning(
                        "Registro 'encontrada' sin email de contacto: %s (ID %s)",
                        nombre,
                        datos.get("ID"),
                    )

            # Calculamos el listado completo de destinatarios para mostrarlo
            destinatarios_finales = []
            for correo in base_destinatarios + destinatarios_extra:
                correo_norm = (correo or "").strip()
                if correo_norm and correo_norm not in destinatarios_finales:
                    destinatarios_finales.append(correo_norm)

            print(
                f"[{idx}] Mascota: {nombre} | Tipo: {tipo} | Destinatarios: {', '.join(destinatarios_finales) or 'N/D'}"
            )

            ok = send_pet_email(
                registro["subject"],
                datos,
                registro["fotos"],
                destinatarios_extra=destinatarios_extra,
            )
            print("   -> Resultado:", "OK" if ok else "ERROR")