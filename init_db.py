import os
import mimetypes
from datetime import date

from flask import current_app
from app import app
from web.models import db, Mascota, FotoMascotaDesaparecida as Foto
from sqlalchemy.exc import IntegrityError


def _static_root():
    """
    Devuelve la carpeta static configurada en Flask (cuando existe) o
    hace fallback al directorio web/static del proyecto.
    """
    try:
        return current_app.static_folder or os.path.join(os.path.dirname(__file__), "web", "static")
    except RuntimeError:
        return os.path.join(os.path.dirname(__file__), "web", "static")


def _cargar_foto(rel_path):
    """
    Carga una foto ubicada dentro de static/… devolviendo:
      - ruta_rel normalizada (sin prefijo “static/”)
      - bytes (o None si no existe el archivo físico)
      - mime_type, nombre_archivo y tamaño
    """
    if not rel_path:
        return None

    rel_path = rel_path.strip().lstrip("/")

    if rel_path.lower().startswith("static/"):
        rel_path = rel_path.split("/", 1)[1]

    ruta_abs = os.path.join(_static_root(), rel_path.replace("/", os.sep))

    if not os.path.isfile(ruta_abs):
        print(f"[init_db] ⚠️ Archivo no encontrado: {ruta_abs}")
        return {
            "ruta_rel": rel_path,
            "data": None,
            "mime_type": mimetypes.guess_type(rel_path)[0] or "application/octet-stream",
            "nombre_archivo": os.path.basename(rel_path),
            "tamano_bytes": None,
        }

    with open(ruta_abs, "rb") as f:
        data = f.read()

    return {
        "ruta_rel": rel_path,
        "data": data,
        "mime_type": mimetypes.guess_type(rel_path)[0] or "application/octet-stream",
        "nombre_archivo": os.path.basename(rel_path),
        "tamano_bytes": len(data),
    }


with app.app_context():
    db.drop_all()
    db.create_all()
    print("Creando tablas en:", app.config["SQLALCHEMY_DATABASE_URI"])
    mascotas = [
        Mascota(
            nombre="Firulais",
            especie="Perro",
            raza="Labrador",
            edad=3,
            propietario_email="juan@example.com",
            propietario_telefono="600000001",
            zona="Centro",
            codigo_postal="28013",
            tipo_registro="desaparecida",
            color="marrón",
            descripcion="Labrador con collar rojo.",
            chip="123456789012345",
            sexo="macho",
            peso=28.5,
            tamano="grande",
            fecha_registro=date(2025, 10, 1),
        ),
        Mascota(
            nombre="encontrada",
            especie="Gato",
            raza="Siamés",
            edad=2,
            propietario_email="ana@example.com",
            propietario_telefono="600000002",
            zona="Norte",
            codigo_postal="28029",
            tipo_registro="encontrada",
            color="crema",
            descripcion="Con cascabel azul.",
            chip=None,
            sexo="hembra",
            peso=4.2,
            tamano="pequeño",
            fecha_registro=date(2025, 10, 2),
        ),
        Mascota(
            nombre="Rocky",
            especie="Perro",
            raza="Pastor Alemán",
            edad=4,
            propietario_email="luis@example.com",
            propietario_telefono="600000003",
            zona="Este",
            codigo_postal="28032",
            tipo_registro="desaparecida",
            color="negro y fuego",
            descripcion=None,
            chip=None,
            sexo="macho",
            peso=32.0,
            tamano="grande",
            fecha_registro=date(2025, 10, 3),
        ),
        Mascota(
            nombre="encontrada",
            especie="Gato",
            raza="Común",
            edad=1,
            propietario_email="marta@example.com",
            propietario_telefono="600000004",
            zona="Oeste",
            codigo_postal="28039",
            tipo_registro="encontrada",
            color="atigrado",
            descripcion="Muy cariñosa.",
            chip=None,
            sexo="hembra",
            peso=3.8,
            tamano="pequeño",
            fecha_registro=date(2025, 10, 4),
        ),
        Mascota(
            nombre="Toby",
            especie="Perro",
            raza="Beagle",
            edad=5,
            propietario_email="pablo@example.com",
            propietario_telefono="600000005",
            zona="Centro",
            codigo_postal="28014",
            tipo_registro="desaparecida",
            color="tricolor",
            descripcion=None,
            chip=None,
            sexo="macho",
            peso=12.5,
            tamano="mediano",
            fecha_registro=date(2025, 10, 5),
        ),
        Mascota(
            nombre="encontrada",
            especie="Perro",
            raza="Mestizo",
            edad=2,
            propietario_email="sofia@example.com",
            propietario_telefono="600000006",
            zona="Sur",
            codigo_postal="28041",
            tipo_registro="encontrada",
            color="blanco",
            descripcion=None,
            chip=None,
            sexo="hembra",
            peso=10.0,
            tamano="mediano",
            fecha_registro=date(2025, 10, 6),
        ),
        Mascota(
            nombre="Coco",
            especie="Gato",
            raza="Maine Coon",
            edad=3,
            propietario_email="raul@example.com",
            propietario_telefono="600000007",
            zona="Norte",
            codigo_postal="28034",
            tipo_registro="desaparecida",
            color="gris",
            descripcion=None,
            chip=None,
            sexo="macho",
            peso=6.5,
            tamano="mediano",
            fecha_registro=date(2025, 10, 7),
        ),
        Mascota(
            nombre="encontrada",
            especie="Perro",
            raza="Pomerania",
            edad=1,
            propietario_email="laura@example.com",
            propietario_telefono="600000008",
            zona="Centro",
            codigo_postal="28010",
            tipo_registro="encontrada",
            color="naranja",
            descripcion=None,
            chip=None,
            sexo="hembra",
            peso=2.8,
            tamano="pequeño",
            fecha_registro=date(2025, 10, 8),
        ),
    ]

    try:
        db.session.add_all(mascotas)
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback
        print("ERROR UNIQUE al insertar mascotas:", exc)
        raise

    fotos_info = [
        (mascotas[0].id, "cara", "static/fotos/frontal4.jpg"),
        (mascotas[2].id, "frontal", "static/fotos/frontal1.jpg"),
        (mascotas[4].id, "lateral_izquierdo", "static/fotos/lateral1.jpg"),
        (mascotas[6].id, "cara", "static/fotos/lateral2.jpg"),
    ]

    fotos = []
    for mascota_id, tipo, ruta in fotos_info:
        datos = _cargar_foto(ruta)
        if not datos:
            continue
        fotos.append(
            Foto(
                mascota_id=mascota_id,
                tipo_foto=tipo,
                ruta=datos["ruta_rel"],
                data=datos["data"],
                mime_type=datos["mime_type"],
                nombre_archivo=datos["nombre_archivo"],
                tamano_bytes=datos["tamano_bytes"],
            )
        )

    try:
        db.session.add_all(fotos)
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        print("ERROR UNIQUE al insertar fotos:", exc)
        raise

    print("✅ Base de datos inicializada con ejemplos (mascotas + fotos con binario).")