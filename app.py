from flask import Flask
from flask_migrate import Migrate, upgrade
from sqlalchemy import inspect
from web.routes import main
from web.models import db
import os

# 📌 Le decimos explícitamente a Flask dónde buscar templates y static
app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "web", "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "web", "static")
)

# ✅ Clave secreta para habilitar sesiones y flash()
app.secret_key = os.environ.get("SECRET_KEY", "super_clave_segura_123")

# Configuración de la base de datos (usa env var si existe)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///mascotas.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# Útil en desarrollo para ver el SQL generado (activar con SQLALCHEMY_ECHO=1)
app.config["SQLALCHEMY_ECHO"] = os.environ.get("SQLALCHEMY_ECHO", "0") == "1"

app.config["EXTERNAL_BASE_URL"] = os.environ.get("EXTERNAL_BASE_URL", "")
app.config["IG_MEDIA_BASE_URL"] = os.getenv("IG_MEDIA_BASE_URL")

# Inicializar ORM y migraciones
db.init_app(app)
Migrate(app, db)  # Requiere: pip install Flask-Migrate
from web.models import Mascota, FotoMascotaDesaparecida

# Registrar blueprint
app.register_blueprint(main)

if __name__ == "__main__":
    with app.app_context():
        print(">>> Secret key configurada:", bool(app.secret_key))

        # Intentar aplicar migraciones si existen; si la BD está vacía y no hay migraciones, usar create_all()
        try:
            migrations_dir = os.path.join(os.path.dirname(__file__), "migrations")
            inspector = inspect(db.engine)
            has_tables = bool(inspector.get_table_names())
            has_migrations = os.path.isdir(migrations_dir) and bool(os.listdir(migrations_dir))

            if not has_tables:
                if has_migrations:
                    print(">>> BD vacía: aplicando migración inicial...")
                    upgrade()
                else:
                    print(">>> BD vacía y sin migraciones: creando tablas con create_all() (solo desarrollo).")
                    db.create_all()
            else:
                if has_migrations:
                    print(">>> Aplicando migraciones pendientes (si las hay)...")
                    upgrade()
                else:
                    print(">>> No hay carpeta de migraciones; omitiendo upgrade().")
        except Exception as e:
            print(f">>> Advertencia durante el setup de la BD: {e}")

    # Parámetros de ejecución (configurables por variables de entorno)
    host = os.environ.get("FLASK_RUN_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_RUN_PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"  # Por defecto True en desarrollo

    app.run(host=host, port=port, debug=False, use_reloader=False) # debug false para reload false y ver con facebook