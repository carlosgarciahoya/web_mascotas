from flask import Flask
from .models import db
import os

def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static")
    )

    # ✅ Clave secreta para sesiones (flash, cookies, etc.)
    app.secret_key = os.environ.get("SECRET_KEY", "super_clave_segura_123")
    print(">>> Secret key configurada:", bool(app.secret_key))

    # Configuración de la base de datos
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        "DATABASE_URL",
        "sqlite:///mascotas.db"
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    # Importar y registrar el blueprint
    from .routes import main as main_bp
    app.register_blueprint(main_bp)

    return app