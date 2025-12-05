
from flask import Flask
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

# Configuración de la base de datos
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mascotas.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Registrar blueprint
app.register_blueprint(main)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        print(">>> Secret key configurada:", bool(app.secret_key))
    host = "0.0.0.0"
    port = 5000
    app.run(host=host, port=port, debug=False)
