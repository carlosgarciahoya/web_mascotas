import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(BASE_DIR, "instance", "mascotas.db")

print("Ruta absoluta esperada:", db_path)

# aseguramos que existe el directorio
os.makedirs(os.path.dirname(db_path), exist_ok=True)

# intentamos abrir directamente con sqlite3
import sqlite3
try:
    conn = sqlite3.connect(db_path)
    print("✅ SQLite abrió correctamente la BD en:", db_path)
    conn.close()
except Exception as e:
    print("❌ Error al abrir la BD:", e)
