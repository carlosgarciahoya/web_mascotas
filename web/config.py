import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(BASE_DIR, "instance", "mascotas.db")

class Config:
    SECRET_KEY = "clave-super-secreta"  # necesaria para formularios / sesiones
    
    # SQLALCHEMY_DATABASE_URI = f"sqlite:///{DB_PATH}"

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or f"sqlite:///{DB_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False


