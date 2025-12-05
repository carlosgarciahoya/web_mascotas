from web.models import db, Mascota, FotoMascotaDesaparecida

print("Importación de modelos correcta")

# Opcional: validar los atributos
print("Campos de Mascota:", [c.name for c in Mascota.__table__.columns])
print("Campos de FotoMascotaDesaparecida:", [c.name for c in FotoMascotaDesaparecida.__table__.columns])
