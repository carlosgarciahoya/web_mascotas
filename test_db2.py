
import os
import sqlite3

basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, "instance", "mascotas.db")

print("Ruta esperada de la BD:", db_path)

# Intentar crear y abrir conexión directamente con sqlite3
conn = sqlite3.connect(db_path)
print("✅ Conexión abierta correctamente")
conn.close()
