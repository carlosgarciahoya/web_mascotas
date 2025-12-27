# listar_fotos.py

import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import os
from sqlalchemy import func
from app import app, db          # tu instancia Flask y la sesión SQLAlchemy
from web.models import FotoMascotaDesaparecida  # el modelo de fotos

def main():
    base = os.environ.get("EXTERNAL_BASE_URL", "https://buscarmascotas.com")
    print (base)
    with app.app_context():
        filas = (
            db.session.query(
                FotoMascotaDesaparecida.id,
                FotoMascotaDesaparecida.nombre_archivo,
                FotoMascotaDesaparecida.mime_type,
                func.octet_length(FotoMascotaDesaparecida.data).label("bytes"),
            )
            .order_by(FotoMascotaDesaparecida.id.desc())
            .limit(20)
            .all()
        )
        for f in filas:
            mb = f.bytes / 1024 / 1024 if f.bytes else 0
            print(f"{f.id} | {f.nombre_archivo} | {f.mime_type} | {mb:.2f} MB | {base}/foto/{f.id}")

if __name__ == "__main__":
    main()
