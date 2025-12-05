from collections import Counter
from datetime import date
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import OperationalError, ProgrammingError
import os

from app import app  # Usamos la misma instancia configurada para Postgres
from web.models import db, Mascota, FotoMascotaDesaparecida

TIPOS_REGISTRO = {"desaparecida", "encontrada"}
TAMANOS = {"pequeño", "mediano", "grande"}
SEXOS = {"macho", "hembra", "no_sabe"}
TIPOS_FOTO = {"cara", "frontal", "lateral_izquierdo", "lateral_derecho", "trasero", "desconocido"}

FECHA_MIN = date(2000, 1, 1)
FECHA_MAX = date(2100, 12, 31)


def safe_str(s):
    return "" if s is None else str(s)


def norm(s):
    return (s or "").strip().lower()


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "web", "static")
FOTOS_DIR = os.path.join(STATIC_DIR, "fotos")

with app.app_context():
    print("=== INSPECCIÓN BD ===")
    print("SQLALCHEMY_DATABASE_URI =", app.config.get("SQLALCHEMY_DATABASE_URI"))
    print("Engine URL              =", db.engine.url)
    print("STATIC_DIR (web)       =", STATIC_DIR)
    print("FOTOS_DIR (web)        =", FOTOS_DIR)
    print()

    inspector = sa_inspect(db.engine)
    tables = inspector.get_table_names()
    print("Tablas vistas por SQLAlchemy:", tables or "(ninguna)")
    if "mascota" not in tables:
        print("\n⚠️ La tabla 'mascota' no existe en esta base.")
        print("   - Ejecuta 'python init_db.py' usando ESTA misma configuración.")
        print("   - Verifica que los scripts usen la misma instancia/configuración.")
        raise SystemExit(1)
    print()

    cols = [c.name for c in Mascota.__table__.columns]
    print("Columnas en 'mascota':", cols)
    print()

    tabla = Mascota.__table__
    constraints = [type(c).__name__ + ":" + str(c) for c in tabla.constraints]
    print("Constraints sobre tabla 'mascota':")
    for c in constraints:
        print("  ", c)
    if not constraints:
        print("  (ninguna constraint declarada)")
    print()

    try:
        mascotas = Mascota.query.order_by(Mascota.id).all()
        fotos = FotoMascotaDesaparecida.query.order_by(FotoMascotaDesaparecida.id).all()
    except (OperationalError, ProgrammingError) as exc:
        print("⚠️ Error al consultar las tablas:", exc)
        print("   - Asegúrate de que la base actual tiene datos (init_db.py).")
        print("   - Comprueba que la URI coincida con la usada al inicializar.")
        raise SystemExit(1)

    print(f"Total mascotas: {len(mascotas)}")
    print(f"Total fotos: {len(fotos)}")

    dist_tipo = Counter((m.tipo_registro or "").lower() for m in mascotas)
    print("Distribución por tipo_registro:", dict(dist_tipo))

    fechas = [m.fecha_registro for m in mascotas if getattr(m, "fecha_registro", None)]
    if fechas:
        print(f"Rango fecha_registro: min={min(fechas)} max={max(fechas)} (total con fecha={len(fechas)})")
    else:
        print("Rango fecha_registro: (sin valores)")
    print()

    dup_map_newkey = {}
    for m in mascotas:
        key = (
            norm(m.propietario_email),
            norm(m.tipo_registro),
            norm(m.nombre),
            norm(m.zona),
            norm(m.codigo_postal),
            norm(m.especie),
            norm(m.color),
            norm(m.tamano),
            getattr(m, "fecha_registro", None),
        )
        dup_map_newkey.setdefault(key, []).append(m.id)
    duplicates_newkey = {k: v for k, v in dup_map_newkey.items() if len(v) > 1}
    if duplicates_newkey:
        print("⚠️ Duplicados por clave única (email, tipo, nombre, zona, CP, especie, color, tamano, fecha) -> ids:")
        for k, v in duplicates_newkey.items():
            print(" ", k, "->", v)
    else:
        print("✅ No se detectaron duplicados por la nueva clave única.")
    print()

    dup_map_fotos = {}
    for f in fotos:
        key = (f.mascota_id, safe_str(f.tipo_foto))
        dup_map_fotos.setdefault(key, []).append(f.id)
    duplicates_fotos = {k: v for k, v in dup_map_fotos.items() if len(v) > 1}
    if duplicates_fotos:
        print("⚠️ Duplicados en fotos (mascota_id, tipo_foto) -> ids:")
        for k, v in duplicates_fotos.items():
            print(" ", k, "->", v)
    else:
        print("✅ No se detectaron duplicados en fotos (mascota_id, tipo_foto).")
    print()

    fotos_por_mascota = {}
    for f in fotos:
        fotos_por_mascota.setdefault(f.mascota_id, []).append(f)

    hoy = date.today()
    total_issues = 0

    for m in mascotas:
        print("-" * 70)
        print(
            f"Mascota id={m.id} | tipo_registro={m.tipo_registro} | nombre={m.nombre} | "
            f"especie={m.especie} | raza={m.raza} | edad={m.edad}"
        )
        print(
            f"  zona={m.zona} | codigo_postal={m.codigo_postal} | "
            f"email={m.propietario_email} | tel={m.propietario_telefono}"
        )
        print(
            f"  color={m.color} | sexo={m.sexo} | chip={m.chip} | peso={m.peso} | tamano={m.tamano}"
        )
        print(
            f"  descripcion={safe_str(m.descripcion)[:120]}"
            f"{'...' if m.descripcion and len(m.descripcion) > 120 else ''}"
        )
        fr = getattr(m, "fecha_registro", None)
        print(
            f"  fecha_registro={fr} | fecha_aparecida={m.fecha_aparecida} | estado_aparecida={m.estado_aparecida}"
        )

        issues = []

        if not m.nombre or not str(m.nombre).strip():
            issues.append("nombre es obligatorio y está vacío")
        if not m.especie or not str(m.especie).strip():
            issues.append("especie es obligatoria y está vacía")
        if not m.propietario_email or not str(m.propietario_email).strip():
            issues.append("propietario_email es obligatorio y está vacío")
        if not m.propietario_telefono or not str(m.propietario_telefono).strip():
            issues.append("propietario_telefono es obligatorio y está vacío")
        if not m.zona or not str(m.zona).strip():
            issues.append("zona es obligatoria y está vacía")
        if not m.codigo_postal or not str(m.codigo_postal).strip():
            issues.append("codigo_postal es obligatorio y está vacío")
        if not m.color or not str(m.color).strip():
            issues.append("color es obligatorio y está vacío")
        if not m.tamano or not str(m.tamano).strip():
            issues.append("tamano es obligatorio y está vacío")
        if not m.sexo or not str(m.sexo).strip():
            issues.append("sexo es obligatorio y está vacío")

        if (m.tipo_registro or "").lower() not in TIPOS_REGISTRO:
            issues.append(f"tipo_registro inválido: {m.tipo_registro}")

        if (m.tamano or "").lower() not in TAMANOS:
            issues.append(f"tamano inválido (fuera de conjunto): {m.tamano}")
        if (m.sexo or "").lower() not in SEXOS:
            issues.append(f"sexo inválido (fuera de conjunto): {m.sexo}")

        if "fecha_registro" in cols:
            if m.fecha_registro is None:
                issues.append("fecha_registro es obligatoria y está NULL")
            else:
                if not (FECHA_MIN <= m.fecha_registro <= FECHA_MAX):
                    issues.append(f"fecha_registro fuera de rango razonable: {m.fecha_registro}")
                if m.fecha_registro > hoy:
                    issues.append(f"fecha_registro en el futuro: {m.fecha_registro}")

        if m.fecha_aparecida and not m.estado_aparecida:
            issues.append("fecha_aparecida informada pero estado_aparecida vacío")
        if m.estado_aparecida and not m.fecha_aparecida:
            issues.append("estado_aparecida informado sin fecha_aparecida")

        if m.chip == "":
            issues.append("chip vacío ('') → se recomienda usar NULL")
        if m.descripcion == "":
            issues.append("descripcion vacía ('') → se recomienda usar NULL")

        fields_norm = {
            "propietario_email": (m.propietario_email, norm(m.propietario_email)),
            "tipo_registro": (m.tipo_registro, norm(m.tipo_registro)),
            "nombre": (m.nombre, norm(m.nombre)),
            "zona": (m.zona, norm(m.zona)),
            "codigo_postal": (m.codigo_postal, norm(m.codigo_postal)),
            "especie": (m.especie, norm(m.especie)),
            "color": (m.color, norm(m.color)),
            "tamano": (m.tamano, norm(m.tamano)),
            "sexo": (m.sexo, norm(m.sexo)),
        }
        for fname, (orig, expected) in fields_norm.items():
            if (orig or "").strip().lower() != expected:
                issues.append(f"{fname} no normalizado (esperado lower().strip()): {orig!r} -> {expected!r}")

        if m.propietario_email and "@" not in m.propietario_email:
            issues.append(f"propietario_email parece inválido: {m.propietario_email}")
        if m.propietario_telefono and len(str(m.propietario_telefono)) < 6:
            issues.append(f"propietario_telefono parece demasiado corto: {m.propietario_telefono}")

        if issues:
            total_issues += len(issues)
            print("  ⚠️ Inconsistencias/avisos:")
            for it in issues:
                print("   -", it)

        f_list = fotos_por_mascota.get(m.id, [])
        if not f_list:
            print("  -> Sin fotos registradas.")
        else:
            for f in f_list:
                ruta_db = safe_str(f.ruta)
                nombre_archivo = os.path.basename(ruta_db)

                if os.path.isabs(ruta_db):
                    ruta_fs_esperada = ruta_db
                else:
                    ruta_fs_esperada = os.path.join(FOTOS_DIR, nombre_archivo)

                existe = os.path.exists(ruta_fs_esperada)
                ext = os.path.splitext(nombre_archivo)[1].lower().lstrip(".")
                tipo_foto_ok = (f.tipo_foto in TIPOS_FOTO)

                print(
                    f"  Foto id={f.id} | tipo_foto={f.tipo_foto} | ruta_db={ruta_db} | "
                    f"archivo={nombre_archivo} | existe_en_fs={existe} | path={ruta_fs_esperada}"
                )
                foto_issues = []
                if not tipo_foto_ok:
                    foto_issues.append(f"tipo de foto fuera de catálogo: {f.tipo_foto}")
                if ext not in {"jpg", "jpeg", "png", "webp", "gif"}:
                    foto_issues.append(f"extensión de archivo no estándar: .{ext}")
                if not existe:
                    foto_issues.append("archivo de imagen no existe en FS")
                if foto_issues:
                    for it in foto_issues:
                        print("     - ⚠️", it)

    ids_mascota = {m.id for m in mascotas}
    orphans = [f for f in fotos if f.mascota_id not in ids_mascota]
    print()
    if orphans:
        print("⚠️ Fotos huérfanas (mascota_id sin registro):")
        for f in orphans:
            print(f"  Foto id={f.id} mascota_id={f.mascota_id} tipo_foto={f.tipo_foto} ruta={f.ruta}")
    else:
        print("✅ No hay fotos huérfanas.")

    print()
    if total_issues:
        print(f"Resumen: ⚠️ Se encontraron {total_issues} avisos/inconsistencias en total.")
    else:
        print("Resumen: ✅ Sin avisos detectados.")

    print("\n=== FIN INSPECCIÓN ===")