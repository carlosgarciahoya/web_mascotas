from web.models import db, Mascota, Foto
from flask import Flask

# Configuración mínima de Flask con SQLite en local
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///instance/mascotas.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    # Crear las tablas
    db.drop_all()  # 🔴 cuidado: borra todo si ya existía
    db.create_all()

    # Crear una mascota de ejemplo
    mascota = Mascota(
        email="dueño@example.com",
        telefono="600123456",
        nombre="Toby",
        lugar="Madrid",
        peso=12.5,
        tamaño="mediano",
        descripcion="Perro mestizo marrón, muy juguetón"
    )

    db.session.add(mascota)
    db.session.commit()

    # Consultar todas las mascotas
    mascotas = Mascota.query.all()
    for m in mascotas:
        print(f"📌 Mascota: {m.nombre}, Email: {m.email}, Tel: {m.telefono}")
