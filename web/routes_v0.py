import os
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename
from .models import db, Mascota, FotoMascotaDesaparecida as Foto

main = Blueprint('main', __name__)

STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')
UPLOAD_FOLDER = os.path.join(STATIC_DIR, 'fotos')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
TIPOS_REGISTRO = {"desaparecida", "encontrada"}
TAMANOS = {"pequeño", "mediano", "grande"}
SEXOS = {"macho", "hembra", "no_sabe"}  # añadido 'no_sabe'


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_tipo_registro_from_request(default_val="desaparecida"):
    # Lee el tipo preferido desde ?tipo=... (GET) o, si no, usa el valor por defecto.
    tipo = (request.args.get("tipo") or "").strip().lower()
    if tipo in TIPOS_REGISTRO:
        return tipo
    return default_val


@main.route('/')
def index():
    return render_template('index.html')


@main.route('/buscar', methods=['GET', 'POST'])
def buscar_mascotas():
    """
    Búsqueda combinada. Filtros soportados (POST):
    - tipo_registro: 'desaparecida' | 'encontrada' | 'todas'
    - Texto (ILIKE): nombre, especie, raza, color, descripcion, chip, sexo, tamano,
                     propietario_email, propietario_telefono, zona, estado_aparecida
    - Exactos: edad (int), peso (float), fecha_aparecida (YYYY-MM-DD)
    Orden de resultados: tipo_registro ASC, especie ASC, tamano ASC, zona ASC, id ASC.
    """
    mensaje = None
    busqueda_realizada = False
    mascotas_con_fotos = []

    tipo_pref = _get_tipo_registro_from_request(default_val=None)  # None => no forzar si no viene

    if request.method == 'POST':
        # Validación suave del selector principal (UI lo marca required)
        tipo_sel = (request.form.get('tipo_registro') or "").strip().lower()
        if tipo_sel not in {'desaparecida', 'encontrada', 'todas'}:
            mensaje = "Selecciona el tipo: desaparecida, encontrada o todas."
            return render_template(
                'buscar.html',
                mascotas_con_fotos=[],
                mensaje=mensaje,
                busqueda_realizada=False
            )

        busqueda_realizada = True
        raw = {k: (v or "").strip() for k, v in request.form.items()}
        filtros = {k: v for k, v in raw.items() if v}

        query = Mascota.query

        # Filtro por tipo_registro desde selector o, en su defecto, desde ?tipo
        tipo_post = (filtros.get("tipo_registro") or "").lower()
        tipo_filtro = tipo_post or (tipo_pref or "")
        if tipo_filtro in TIPOS_REGISTRO:
            query = query.filter(Mascota.tipo_registro == tipo_filtro)
        # Si tipo_filtro == 'todas' o vacío -> sin filtro de tipo

        # Campos de texto con ILIKE (y los nuevos añadidos)
        campos_texto = {
            'nombre', 'especie', 'raza', 'color', 'descripcion',
            'chip', 'sexo', 'tamano', 'propietario_email',
            'propietario_telefono', 'zona', 'estado_aparecida'
        }

        for campo, valor in filtros.items():
            if campo == 'edad':
                if valor.isdigit():
                    query = query.filter(Mascota.edad == int(valor))
                continue
            if campo == 'peso':
                try:
                    query = query.filter(Mascota.peso == float(valor))
                except ValueError:
                    pass
                continue
            if campo == 'fecha_aparecida':
                # esperamos YYYY-MM-DD (input type=date)
                try:
                    dt = datetime.strptime(valor, "%Y-%m-%d").date()
                    query = query.filter(Mascota.fecha_aparecida == dt)
                except Exception:
                    pass
                continue
            if campo == 'tipo_registro':
                continue  # ya aplicado arriba
            if campo in campos_texto and hasattr(Mascota, campo):
                query = query.filter(getattr(Mascota, campo).ilike(f"%{valor}%"))

        # Orden solicitado
        query = query.order_by(
            Mascota.tipo_registro.asc(),
            Mascota.especie.asc(),
            Mascota.tamano.asc(),
            Mascota.zona.asc(),
            Mascota.id.asc()
        )
        mascotas = query.all()

        if not mascotas:
            mensaje = "No se encontraron mascotas."
        else:
            mascotas_con_fotos = [(m, m.fotos) for m in mascotas]

    return render_template(
        'buscar.html',
        mascotas_con_fotos=mascotas_con_fotos,
        mensaje=mensaje,
        busqueda_realizada=busqueda_realizada
    )


@main.route('/verificar_mascota', methods=['POST'])
def verificar_mascota():
    """
    Verifica duplicado por (nombre, especie, raza, tipo_registro).
    El tipo se toma de ?tipo=... en la URL; si no viene, asumimos 'desaparecida'.
    Nota: para 'encontrada' la UI muestra 'encontrada' como nombre, pero en guardado se genera un nombre técnico único.
    """
    nombre = (request.form.get("nombre") or "").strip()
    especie = (request.form.get("especie") or "").strip()
    raza = (request.form.get("raza") or "").strip()

    tipo = _get_tipo_registro_from_request(default_val="desaparecida")

    if not nombre or not especie or not raza:
        return jsonify({"existe": False})

    existe = Mascota.query.filter_by(
        nombre=nombre,
        especie=especie,
        raza=raza,
        tipo_registro=tipo
    ).first() is not None
    return jsonify({"existe": existe})


@main.route('/crear', methods=['GET', 'POST'])
def crear_mascota():
    """
    Crea mascota con tipo_registro fijado por ?tipo=desaparecida|encontrada (por defecto 'desaparecida').
    Campos obligatorios clave:
      color, sexo (macho/hembra/no_sabe), tamano (pequeño/mediano/grande).
    Opcionales:
      chip, descripcion, peso; fecha_aparecida/estado_aparecida se gestionan en Modificar.
    """
    tipo_registro = _get_tipo_registro_from_request(default_val="desaparecida")

    if request.method == 'POST':
        try:
            nombre = (request.form.get('nombre') or "").strip()
            especie = (request.form.get('especie') or "").strip()
            raza = (request.form.get('raza') or "").strip()
            zona = (request.form.get('zona') or "").strip()
            propietario_email = (request.form.get('propietario_email') or "").strip()
            propietario_telefono = (request.form.get('propietario_telefono') or "").strip()

            edad_raw = (request.form.get('edad') or "").strip()
            edad = int(edad_raw) if edad_raw.isdigit() else None

            # Atributos obligatorios/opcionales
            color = (request.form.get('color') or "").strip()
            sexo = (request.form.get('sexo') or "").strip().lower()
            chip = (request.form.get('chip') or "").strip()
            descripcion = (request.form.get('descripcion') or "").strip()
            tamano = (request.form.get('tamano') or "").strip().lower()

            if not color:
                flash("⚠️ El campo 'color' es obligatorio.", "error")
                return render_template('crear.html')
            if sexo not in SEXOS:
                flash("⚠️ Debes seleccionar el 'sexo' (macho, hembra o no sabe).", "error")
                return render_template('crear.html')
            if tamano not in TAMANOS:
                flash("⚠️ El tamaño es obligatorio y debe ser pequeño, mediano o grande.", "error")
                return render_template('crear.html')

            # Ajustes especiales para 'encontrada'
            if tipo_registro == 'encontrada':
                # Generar nombre técnico único si viene 'encontrada' o vacío
                if not nombre or nombre.strip().lower() == 'encontrada':
                    slug = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]
                    nombre = f"encontrada-{slug}"
                # Si no se conoce la raza, fijar 'raza'
                if not raza:
                    raza = "raza"

            # peso (opcional)
            peso = None
            peso_raw = (request.form.get('peso') or "").strip()
            if peso_raw != "":
                try:
                    peso = float(peso_raw)
                except ValueError:
                    flash("⚠️ El 'peso' debe ser numérico (ej. 3.5).", "error")
                    return render_template('crear.html')

            nueva = Mascota(
                nombre=nombre,
                especie=especie,
                raza=raza,
                edad=edad,
                propietario_email=propietario_email or None,
                propietario_telefono=propietario_telefono or None,
                zona=zona,

                # modelo unificado
                tipo_registro=tipo_registro,
                color=color,
                descripcion=descripcion or None,
                chip=chip or None,
                sexo=sexo,

                # aparición (no se rellena al crear)
                fecha_aparecida=None,
                estado_aparecida=None,

                # otros
                peso=peso,
                tamano=tamano  # obligatorio y validado
            )
            db.session.add(nueva)
            db.session.commit()

            # Guardar fotos (coinciden los índices de listas)
            fotos = request.files.getlist('fotos')
            tipos = request.form.getlist('tipo_foto')
            for idx, foto in enumerate(fotos):
                if not foto or not foto.filename:
                    continue
                if not allowed_file(foto.filename):
                    continue
                tipo_f = tipos[idx] if idx < len(tipos) else 'desconocido'
                base_filename = secure_filename(foto.filename)
                unique = uuid.uuid4().hex[:8]
                filename = secure_filename(f"{nueva.id}_{tipo_f}_{idx}_{unique}_{base_filename}")
                ruta_fs = os.path.join(UPLOAD_FOLDER, filename)
                foto.save(ruta_fs)
                ruta_db = f"static/fotos/{filename}".replace("\\", "/")
                db.session.add(Foto(mascota_id=nueva.id, tipo=tipo_f, ruta=ruta_db))

            db.session.commit()
            flash("✅ Mascota creada correctamente.", "success")
            return redirect(url_for('main.index'))

        except IntegrityError:
            db.session.rollback()
            flash("⚠️ Ya existe una mascota con el mismo nombre, especie y raza para este tipo de registro.", "error")
        except Exception as e:
            db.session.rollback()
            flash(f"❌ Error al crear la mascota: {e}", "error")

    return render_template('crear.html')


@main.route('/modificar', methods=['GET', 'POST'])
def modificar_mascotas():
    """
    Listado para localizar mascotas a modificar/eliminar.
    Filtros y comportamiento alineados con /buscar.
    - Si viene ?mascota_id=ID (tras agregar/borrar/editar), se muestra solo esa tarjeta.
    - Si viene ?tipo=desaparecida|encontrada, se prefiltra por ese tipo.
    Orden de resultados: tipo_registro, especie, tamano, zona, id.
    """
    mascotas = None
    mensaje = None
    busqueda_realizada = False

    # Refresco a tarjeta concreta
    mascota_id = request.args.get('mascota_id', type=int)
    if request.method == 'GET' and mascota_id:
        m = Mascota.query.get_or_404(mascota_id)
        mascotas = [m]
        busqueda_realizada = True
        return render_template('modificar.html',
                               mascotas=mascotas,
                               mensaje=mensaje,
                               busqueda_realizada=busqueda_realizada)

    if request.method == 'POST':
        # Validación suave del selector principal (UI lo marca required)
        tipo_sel = (request.form.get('tipo_registro') or "").strip().lower()
        if tipo_sel not in {'desaparecida', 'encontrada', 'todas'}:
            mensaje = "Selecciona el tipo: desaparecida, encontrada o todas."
            return render_template('modificar.html',
                                   mascotas=None,
                                   mensaje=mensaje,
                                   busqueda_realizada=False)

        busqueda_realizada = True
        filtros = {k: (v or "").strip() for k, v in request.form.items() if (v or "").strip()}

        query = Mascota.query

        # Filtro por tipo del formulario o de la querystring
        tipo_pref = _get_tipo_registro_from_request(default_val=None)
        tipo_post = (filtros.get("tipo_registro") or "").lower()
        tipo_filtro = tipo_post or (tipo_pref or "")
        if tipo_filtro in TIPOS_REGISTRO:
            query = query.filter(Mascota.tipo_registro == tipo_filtro)
        # Si 'todas' o vacío: sin filtro de tipo

        # Texto ILIKE
        campos_texto = {
            'nombre', 'especie', 'raza', 'zona',
            'propietario_email', 'propietario_telefono',
            'color', 'chip', 'sexo', 'tamano', 'descripcion',
            'estado_aparecida'
        }

        for campo, valor in filtros.items():
            if campo == 'edad':
                if valor.isdigit():
                    query = query.filter(Mascota.edad == int(valor))
                continue
            if campo == 'peso':
                try:
                    query = query.filter(Mascota.peso == float(valor))
                except ValueError:
                    pass
                continue
            if campo == 'fecha_aparecida':
                try:
                    dt = datetime.strptime(valor, "%Y-%m-%d").date()
                    query = query.filter(Mascota.fecha_aparecida == dt)
                except Exception:
                    pass
                continue
            if campo == 'tipo_registro':
                continue
            if campo in campos_texto and hasattr(Mascota, campo):
                query = query.filter(getattr(Mascota, campo).ilike(f"%{valor}%"))

        # Orden igual que en buscar
        mascotas = query.order_by(
            Mascota.tipo_registro.asc(),
            Mascota.especie.asc(),
            Mascota.tamano.asc(),
            Mascota.zona.asc(),
            Mascota.id.asc()
        ).all()

    return render_template('modificar.html',
                           mascotas=mascotas,
                           mensaje=mensaje,
                           busqueda_realizada=busqueda_realizada)


@main.route('/modificar/<int:id>', methods=['GET', 'POST'])
def modificar_registro(id):
    """
    Edición de un registro concreto. Reglas:
    - Se pueden editar todos los campos básicos y atributos (color, sexo, chip, descripcion, peso, tamano).
    - tamano es obligatorio y debe ser: pequeño | mediano | grande.
    - El bloque 'Aparición' (fecha_aparecida, estado_aparecida) SOLO se puede editar si tipo_registro == 'desaparecida'.
      En registros 'encontrada' se ignora cualquier entrada y se conserva lo que haya.
    - Si se informa fecha_aparecida, estado_aparecida es obligatorio ('viva'|'muerta').
    """
    mascota = Mascota.query.get_or_404(id)

    if request.method == 'POST':
        try:
            # Básicos
            mascota.nombre = (request.form.get('nombre') or "").strip()
            mascota.especie = (request.form.get('especie') or "").strip()
            mascota.raza = (request.form.get('raza') or "").strip()
            edad_raw = (request.form.get('edad') or "").strip()
            mascota.edad = int(edad_raw) if edad_raw.isdigit() else None
            mascota.propietario_email = (request.form.get('propietario_email') or "").strip()
            mascota.propietario_telefono = (request.form.get('propietario_telefono') or "").strip()
            mascota.zona = (request.form.get('zona') or "").strip()

            # Atributos
            color = (request.form.get('color') or "").strip()
            sexo = (request.form.get('sexo') or "").strip().lower()
            chip = (request.form.get('chip') or "").strip()
            descripcion = (request.form.get('descripcion') or "").strip()

            if not color:
                flash("⚠️ El campo 'color' es obligatorio.", "error")
                return render_template('modificar_registro.html', mascota=mascota)
            if sexo not in SEXOS:
                flash("⚠️ Debes seleccionar el 'sexo' (macho, hembra o no sabe).", "error")
                return render_template('modificar_registro.html', mascota=mascota)

            mascota.color = color
            mascota.sexo = sexo
            mascota.chip = chip or None
            mascota.descripcion = descripcion or None

            # Peso / Tamaño
            peso_raw = (request.form.get('peso') or "").strip()
            if peso_raw != "":
                try:
                    mascota.peso = float(peso_raw)
                except ValueError:
                    flash("⚠️ El 'peso' debe ser numérico (ej. 3.5).", "error")
                    return render_template('modificar_registro.html', mascota=mascota)
            else:
                mascota.peso = None

            tamano = (request.form.get('tamano') or "").strip().lower()
            if tamano not in TAMANOS:
                flash("⚠️ El tamaño es obligatorio y debe ser pequeño, mediano o grande.", "error")
                return render_template('modificar_registro.html', mascota=mascota)
            mascota.tamano = tamano

            # Aparición: SOLO editable cuando es 'desaparecida'
            if mascota.tipo_registro == 'desaparecida':
                fecha_raw = (request.form.get('fecha_aparecida') or "").strip()
                estado = (request.form.get('estado_aparecida') or "").strip().lower()

                if fecha_raw:
                    try:
                        fecha = datetime.strptime(fecha_raw, "%Y-%m-%d").date()
                    except Exception:
                        flash("⚠️ Fecha aparecida inválida (usa YYYY-MM-DD).", "error")
                        return render_template('modificar_registro.html', mascota=mascota)
                    if estado not in {"viva", "muerta"}:
                        flash("⚠️ Debes indicar el estado (viva o muerta) si informas la fecha.", "error")
                        return render_template('modificar_registro.html', mascota=mascota)
                    mascota.fecha_aparecida = fecha
                    mascota.estado_aparecida = estado
                else:
                    # Sin fecha, limpiar ambos
                    mascota.fecha_aparecida = None
                    mascota.estado_aparecida = None
            # Si es 'encontrada', se ignoran campos de aparición (no se tocan)

            db.session.commit()
            flash("✅ Mascota modificada correctamente.", "success")
        except IntegrityError:
            db.session.rollback()
            flash("⚠️ Ya existe otra mascota con el mismo nombre, especie y raza para este tipo de registro.", "error")

        return redirect(url_for('main.modificar_mascotas', mascota_id=mascota.id))

    return render_template('modificar_registro.html', mascota=mascota)


@main.route('/eliminar/<int:id>', methods=['GET', 'POST'])
def eliminar_registro(id):
    mascota = Mascota.query.get_or_404(id)
    if request.method == 'POST':
        db.session.delete(mascota)
        db.session.commit()
        flash("🗑️ Mascota eliminada correctamente.", "success")
        return redirect(url_for('main.modificar_mascotas'))
    return render_template('eliminar_registro.html', mascota=mascota)


# ==========================
# FOTOS: Eliminar y Agregar
# ==========================

@main.route('/foto/eliminar/<int:foto_id>', methods=['POST'])
def eliminar_foto(foto_id):
    foto = Foto.query.get_or_404(foto_id)
    mascota_id = foto.mascota_id
    # Borrar archivo físico
    try:
        basename = os.path.basename(foto.ruta)
        ruta_fs = os.path.join(UPLOAD_FOLDER, basename)
        if os.path.exists(ruta_fs):
            os.remove(ruta_fs)
    except Exception:
        pass
    # Borrar BD
    db.session.delete(foto)
    db.session.commit()
    flash("🗑️ Foto eliminada.", "success")
    return redirect(url_for('main.modificar_mascotas', mascota_id=mascota_id))


@main.route('/foto/agregar/<int:mascota_id>', methods=['POST'])
def agregar_foto(mascota_id):
    mascota = Mascota.query.get_or_404(mascota_id)
    file = request.files.get('foto')
    tipo = (request.form.get('tipo_foto') or "desconocido").strip()

    if not file or not file.filename:
        flash("⚠️ Debes seleccionar una imagen.", "error")
        return redirect(url_for('main.modificar_mascotas', mascota_id=mascota.id))

    if not allowed_file(file.filename):
        flash("⚠️ Formato no permitido. Usa jpg, jpeg, png, webp o gif.", "error")
        return redirect(url_for('main.modificar_mascotas', mascota_id=mascota.id))

    base = secure_filename(file.filename)
    unique = uuid.uuid4().hex[:8]
    filename = secure_filename(f"{mascota.id}_{tipo}_{unique}_{base}")
    ruta_fs = os.path.join(UPLOAD_FOLDER, filename)
    file.save(ruta_fs)

    ruta_db = f"static/fotos/{filename}".replace("\\", "/")
    nueva_foto = Foto(mascota_id=mascota.id, tipo=tipo, ruta=ruta_db)
    db.session.add(nueva_foto)
    db.session.commit()
    flash("✅ Foto añadida.", "success")
    return redirect(url_for('main.modificar_mascotas', mascota_id=mascota.id))