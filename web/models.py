from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint, CheckConstraint
from sqlalchemy.orm import validates

db = SQLAlchemy()


class Mascota(db.Model):
    __tablename__ = 'mascota'

    id = db.Column(db.Integer, primary_key=True)

    # Identificación básica
    nombre = db.Column(db.String(50), nullable=False)
    especie = db.Column(db.String(50), nullable=False)
    raza = db.Column(db.String(50))
    edad = db.Column(db.Integer)

    # Contacto
    propietario_email = db.Column(db.String(120), nullable=False)
    propietario_telefono = db.Column(db.String(20), nullable=False)

    # Zona y código postal de desaparición
    zona = db.Column(db.String(50), nullable=False)             # localidad
    codigo_postal = db.Column(db.String(5), nullable=False)     # nuevo campo

    # Estado del registro
    tipo_registro = db.Column(db.String(12), nullable=False)    # 'desaparecida' | 'encontrada'

    # Atributos adicionales de la mascota
    color = db.Column(db.String(30), nullable=False)            # obligatorio
    descripcion = db.Column(db.Text)                            # opcional
    chip = db.Column(db.String(20))                             # opcional
    sexo = db.Column(db.String(8), nullable=False)              # 'macho' | 'hembra' | 'no_sabe'

    # Aparición (cuando corresponda)
    fecha_aparecida = db.Column(db.Date)                        # opcional
    estado_aparecida = db.Column(db.String(6))                  # 'viva' | 'muerta'

    # Otros
    peso = db.Column(db.Float)
    tamano = db.Column(db.String(20), nullable=False)           # 'pequeño' | 'mediano' | 'grande'
    fecha_registro = db.Column(db.Date, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            'propietario_email', 'tipo_registro', 'nombre', 'zona', 'codigo_postal',
            'especie', 'color', 'tamano', 'fecha_registro',
            name='uix_email_tipo_nombre_zona_cp_especie_color_tamano_fecha'
        ),
        CheckConstraint("tamano IN ('pequeño','mediano','grande')", name='chk_tamano_valido'),
        CheckConstraint("sexo IN ('macho','hembra','no_sabe')", name='chk_sexo_valido'),
        CheckConstraint("tipo_registro IN ('desaparecida','encontrada')", name='chk_tipo_registro_valido'),
    )

    @validates('propietario_email', 'tipo_registro', 'nombre', 'zona',
               'codigo_postal', 'especie', 'color', 'tamano', 'sexo')
    def _val_lower_strip(self, key, value):
        v = (value or "").strip()
        return v.lower()

    @validates('propietario_telefono')
    def _val_tel(self, key, value):
        return (value or "").strip()

    @validates('raza', 'chip', 'descripcion', 'estado_aparecida')
    def _val_optional(self, key, value):
        v = (value or "").strip()
        if not v:
            return None
        if key == 'estado_aparecida':
            return v.lower()
        return v

    def __repr__(self):
        return (
            f"<Mascota id={self.id} nombre={self.nombre!r} "
            f"tipo_registro={self.tipo_registro!r} fecha_registro={self.fecha_registro}>"
        )


class FotoMascotaDesaparecida(db.Model):
    __tablename__ = "fotos_mascotas_desaparecidas"

    id = db.Column(db.Integer, primary_key=True)
    mascota_id = db.Column(db.Integer, db.ForeignKey('mascota.id'), nullable=False)
    tipo_foto = db.Column(db.String(30), nullable=False)

    ruta = db.Column(db.String(200), nullable=False)

    data = db.Column(db.LargeBinary, nullable=True)
    mime_type = db.Column(db.String(50), nullable=True)
    nombre_archivo = db.Column(db.String(120), nullable=True)
    tamano_bytes = db.Column(db.Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint('mascota_id', 'tipo_foto', name='uix_foto_mascota_tipo'),
    )

    mascota = db.relationship("Mascota", backref=db.backref("fotos", lazy=True))

    def __repr__(self):
        return f"<Foto id={self.id} tipo_foto={self.tipo_foto!r} mascota_id={self.mascota_id}>"