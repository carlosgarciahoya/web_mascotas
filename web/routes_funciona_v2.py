import os
import uuid
import base64
from datetime import datetime, date
from threading import Thread
from typing import List, Dict

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, jsonify, current_app
)
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from .models import db, Mascota, FotoMascotaDesaparecida as Foto
from .utils.envia_mail import send_pet_email
from openai import OpenAI

main = Blueprint('main', __name__)

# Directorios según tu estructura: web/templates y web/static
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
UPLOAD_FOLDER = os.path.join(STATIC_DIR, 'fotos')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
TIPOS_REGISTRO = {"desaparecida", "encontrada"}
TAMANOS = {"pequeño", "mediano", "grande"}
SEXOS = {"macho", "hembra", "no_sabe"}
ESTADOS_APARECIDA = {"viva", "muerta"}

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def image_to_data_url(path):
    name = os.path.basename(path).lower()
    if name.endswith(".png"):
        mime = "image/png"
    elif name.endswith((".jpg", ".jpeg")):
        mime = "image/jpeg"
    elif name.endswith(".gif"):
        mime = "image/gif"
    elif name.endswith(".webp"):
        mime = "image/webp"
    else:
        mime = "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def parse_fecha(fecha_str: str | None) -> date | None:
    """
    Convierte una fecha de texto a un objeto date.
    Acepta formatos dd/mm/aaaa y aaaa-mm-dd (tipo <input type="date">).
    """
    if not fecha_str:
        return None
    fecha_str = fecha_str.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(fecha_str, fmt).date()
        except ValueError:
            continue
    return None


def normalizar_ruta_foto(ruta: str | None) -> str | None:
    """
    Normaliza la ruta (con independencia de cómo se guardara originalmente) para que quede
    siempre relativa a static y con barras '/'.
    Ejemplo de salida: 'fotos/mifoto.jpg'
    """
    if not ruta:
        return None

    ruta = ruta.strip().replace("\\", "/")
    partes = [p for p in ruta.split("/") if p]
    if not partes:
        return None

    partes_lower = [p.lower() for p in partes]
    if "static" in partes_lower:
        idx = partes_lower.index("static")
        partes = partes[idx + 1 :]
        partes_lower = partes_lower[idx + 1 :]
    if "fotos" in partes_lower:
        idx = partes_lower.index("fotos")
        partes = partes[idx:]
    ruta_normalizada = "/".join(partes)
    return ruta_normalizada or None


# =============================
# ENVÍO DE CORREOS EN BACKGROUND
# =============================
def _programar_envio_correo(mascota_id: int) -> None:
    """
    Programa el envío de correo en un hilo separado.
    """
    try:
        app = current_app._get_current_object()
        Thread(
            target=_worker_enviar_correo,
            args=(app, mascota_id),
            daemon=True
        ).start()
    except Exception:  # pylint: disable=broad-except
        current_app.logger.exception(
            "No se pudo programar el envío de correo para la mascota %s", mascota_id
        )


def _worker_enviar_correo(app, mascota_id: int) -> None:
    """
    Hilo en segundo plano que realiza el envío real del correo.
    """
    with app.app_context():
        mascota = Mascota.query.get(mascota_id)
        if not mascota:
            current_app.logger.error(
                "No se encontró la mascota %s para enviar correo.", mascota_id
            )
            return

        subject = (mascota.tipo_registro or "").strip() or "Mascota"
        datos_email = _construir_datos_email(mascota)
        fotos_email = _obtener_rutas_fotos(mascota)
        destinatarios_extra = _calcular_destinatarios_extra(mascota)

        ok = send_pet_email(
            subject,
            datos_email,
            fotos_email,
            destinatarios_extra=destinatarios_extra,
        )
        if not ok:
            current_app.logger.error(
                "Fallo al enviar correo automático de mascota %s", mascota_id
            )


def _construir_datos_email(mascota: Mascota) -> Dict[str, object]:
    """
    Prepara la información que irá en el cuerpo del correo.
    """
    return {
        "ID": mascota.id,
        "Tipo de registro": mascota.tipo_registro,
        "Nombre": mascota.nombre,
        "Especie": mascota.especie,
        "Raza": mascota.raza,
        "Edad": mascota.edad,
        "Zona": mascota.zona,
        "Email contacto": mascota.propietario_email,
        "Teléfono contacto": mascota.propietario_telefono,
        "Color": mascota.color,
        "Sexo": mascota.sexo,
        "Chip": mascota.chip,
        "Peso": mascota.peso,
        "Tamaño": mascota.tamano,
        "Descripción": mascota.descripcion,
        "Fecha registro": mascota.fecha_registro,
        "Fecha aparecida": mascota.fecha_aparecida,
        "Estado aparecida": mascota.estado_aparecida,
    }


def _obtener_rutas_fotos(mascota: Mascota) -> List[str]:
    """
    Convierte las rutas relativas de las fotos en rutas absolutas
    (solo se incluyen las que existan físicamente).
    """
    rutas: List[str] = []
    for foto in getattr(mascota, "fotos", []):
        ruta_rel = normalizar_ruta_foto(foto.ruta)
        if not ruta_rel:
            continue

        ruta_abs = os.path.join(STATIC_DIR, ruta_rel.replace("/", os.sep))
        if os.path.isfile(ruta_abs):
            rutas.append(ruta_abs)
        else:
            current_app.logger.warning(
                "Foto no encontrada en disco: %s (mascota %s)", ruta_abs, mascota.id
            )

    return rutas


def _calcular_destinatarios_extra(mascota: Mascota) -> List[str]:
    """
    Calcula los destinatarios adicionales según el tipo de registro.
    - Desaparecida: solo el correo del propietario.
    - Encontrada : propietario + correos de mascotas desaparecidas anteriores
      (sin marcar como aparecidas).
    """
    destinatarios: List[str] = []
    correo_propietario = (mascota.propietario_email or "").strip()
    if correo_propietario:
        destinatarios.append(correo_propietario)

    if (mascota.tipo_registro or "").lower() == "encontrada":
        registros_previos = (
            Mascota.query.with_entities(Mascota.propietario_email)
            .filter(
                Mascota.tipo_registro == "desaparecida",
                Mascota.fecha_registro <= mascota.fecha_registro,
                Mascota.fecha_aparecida.is_(None),
                Mascota.propietario_email.isnot(None),
                Mascota.propietario_email != "",
            )
            .distinct()
            .all()
        )

        for (correo,) in registros_previos:
            correo_norm = (correo or "").strip()
            if correo_norm and correo_norm not in destinatarios:
                destinatarios.append(correo_norm)

    return destinatarios


# =============================
# RUTAS PRINCIPALES
# =============================

@main.route("/")
def index():
    return render_template("index.html")


@main.route("/crear_mascota", methods=["GET", "POST"])
def crear_mascota():
    tipo_registro = (request.args.get("tipo_registro") or "desaparecida").lower()

    if tipo_registro not in TIPOS_REGISTRO:
        flash("Tipo de registro inválido.", "error")
        return redirect(url_for("main.index"))

    if request.method == "POST":
        nombre = (request.form.get("nombre") or "").strip()
        especie = (request.form.get("especie") or "").strip()
        raza = (request.form.get("raza") or "").strip()
        edad = (request.form.get("edad") or "").strip()
        propietario_email = (request.form.get("propietario_email") or "").strip()
        propietario_telefono = (request.form.get("propietario_telefono") or "").strip()
        zona = (request.form.get("zona") or "").strip()
        color = (request.form.get("color") or "").strip()
        sexo = (request.form.get("sexo") or "").strip().lower()
        chip = (request.form.get("chip") or "").strip()
        peso = (request.form.get("peso") or "").strip()
        tamano = (request.form.get("tamano") or "").strip().lower()
        descripcion = (request.form.get("descripcion") or "").strip()
        fecha_registro_str = (request.form.get("fecha_registro") or "").strip()

        if tipo_registro == "encontrada":
            nombre = "encontrada"

        if not nombre:
            flash("El nombre de la mascota es obligatorio.", "error")
            return redirect(request.url)

        if not especie or not color or sexo not in SEXOS or tamano not in TAMANOS:
            flash("Faltan datos obligatorios (especie, color, sexo, tamaño).", "error")
            return redirect(request.url)

        fecha_registro = parse_fecha(fecha_registro_str) or datetime.utcnow().date()

        nueva = Mascota(
            tipo_registro=tipo_registro,
            nombre=nombre,
            especie=especie,
            raza=raza or None,
            edad=int(edad) if edad.isdigit() else None,
            propietario_email=propietario_email or None,
            propietario_telefono=propietario_telefono or None,
            zona=zona or None,
            color=color,
            descripcion=descripcion or None,
            chip=chip or None,
            sexo=sexo,
            peso=float(peso.replace(",", ".")) if peso else None,
            tamano=tamano,
            fecha_registro=fecha_registro
        )

        try:
            db.session.add(nueva)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Error de integridad al guardar la mascota (posible duplicado).", "error")
            return redirect(request.url)

        fotos = request.files.getlist("fotos")
        tipos_foto = request.form.getlist("tipo_foto")

        for idx, f in enumerate(fotos):
            if not f or not f.filename or not allowed_file(f.filename):
                continue

            tipo_actual = tipos_foto[idx] if idx < len(tipos_foto) else "desconocido"

            nombre_seguro = secure_filename(
                f"{nueva.id}_{tipo_actual}_{uuid.uuid4().hex}_{f.filename}"
            )
            ruta_fs = os.path.join(UPLOAD_FOLDER, nombre_seguro)
            f.save(ruta_fs)

            ruta_relativa = normalizar_ruta_foto(f"fotos/{nombre_seguro}")

            db.session.add(
                Foto(
                    mascota_id=nueva.id,
                    tipo_foto=tipo_actual,
                    ruta=ruta_relativa
                )
            )

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("La mascota se guardó, pero hubo un problema al registrar las fotos.", "error")
            return redirect(url_for("main.index"))

        flash(f"Mascota {tipo_registro} registrada correctamente.", "success")
        _programar_envio_correo(nueva.id)
        return redirect(url_for("main.index"))

    return render_template("crear_mascota.html", tipo_registro=tipo_registro)


@main.route("/buscar_mascotas", methods=["GET", "POST"])
def buscar_mascotas():
    busqueda_realizada = request.method == "POST"
    mensaje = None
    mascotas_con_fotos = []
    filtros = {}

    query = Mascota.query

    if request.method == "POST":
        filtros = {
            "tipo_registro": (request.form.get("tipo_registro") or "").lower(),
            "nombre": (request.form.get("nombre") or "").strip(),
            "especie": (request.form.get("especie") or "").strip(),
            "raza": (request.form.get("raza") or "").strip(),
            "edad": (request.form.get("edad") or "").strip(),
            "propietario_email": (request.form.get("propietario_email") or "").strip(),
            "propietario_telefono": (request.form.get("propietario_telefono") or "").strip(),
            "zona": (request.form.get("zona") or "").strip(),
            "color": (request.form.get("color") or "").strip(),
            "sexo": (request.form.get("sexo") or "").lower().strip(),
            "chip": (request.form.get("chip") or "").strip(),
            "tamano": (request.form.get("tamano") or "").lower().strip(),
            "peso": (request.form.get("peso") or "").strip(),
            "fecha_registro": (request.form.get("fecha_registro") or "").strip(),
            "fecha_aparecida": (request.form.get("fecha_aparecida") or "").strip(),
            "estado_aparecida": (request.form.get("estado_aparecida") or "").lower().strip(),
            "descripcion": (request.form.get("descripcion") or "").strip(),
        }

        if filtros["tipo_registro"] in TIPOS_REGISTRO:
            query = query.filter(Mascota.tipo_registro == filtros["tipo_registro"])

        if filtros["nombre"]:
            query = query.filter(Mascota.nombre.ilike(f"%{filtros['nombre']}%"))

        if filtros["especie"]:
            query = query.filter(Mascota.especie.ilike(f"%{filtros['especie']}%"))

        if filtros["raza"]:
            query = query.filter(Mascota.raza.ilike(f"%{filtros['raza']}%"))

        if filtros["edad"].isdigit():
            query = query.filter(Mascota.edad == int(filtros["edad"]))

        if filtros["propietario_email"]:
            query = query.filter(Mascota.propietario_email.ilike(f"%{filtros['propietario_email']}%"))

        if filtros["propietario_telefono"]:
            query = query.filter(Mascota.propietario_telefono.ilike(f"%{filtros['propietario_telefono']}%"))

        if filtros["zona"]:
            query = query.filter(Mascota.zona.ilike(f"%{filtros['zona']}%"))

        if filtros["color"]:
            query = query.filter(Mascota.color.ilike(f"%{filtros['color']}%"))

        if filtros["sexo"] in SEXOS:
            query = query.filter(Mascota.sexo == filtros["sexo"])

        if filtros["chip"]:
            query = query.filter(Mascota.chip.ilike(f"%{filtros['chip']}%"))

        if filtros["tamano"] in TAMANOS:
            query = query.filter(Mascota.tamano == filtros["tamano"])

        if filtros["peso"]:
            try:
                peso_val = float(filtros["peso"].replace(",", "."))
                query = query.filter(Mascota.peso == peso_val)
            except ValueError:
                flash("Peso inválido. Usa números (puedes emplear coma o punto).", "error")

        if filtros["fecha_registro"]:
            fecha_filtrada = parse_fecha(filtros["fecha_registro"])
            if fecha_filtrada:
                query = query.filter(Mascota.fecha_registro == fecha_filtrada)
            else:
                flash("Formato de fecha de registro inválido. Usa dd/mm/aaaa.", "error")

        if filtros["fecha_aparecida"]:
            fecha_ap = parse_fecha(filtros["fecha_aparecida"])
            if fecha_ap:
                query = query.filter(Mascota.fecha_aparecida == fecha_ap)
            else:
                flash("Formato de fecha de aparición inválido.", "error")

        if filtros["estado_aparecida"] in ESTADOS_APARECIDA:
            query = query.filter(Mascota.estado_aparecida == filtros["estado_aparecida"])

        if filtros["descripcion"]:
            query = query.filter(Mascota.descripcion.ilike(f"%{filtros['descripcion']}%"))

    mascotas = query.order_by(Mascota.fecha_registro.desc()).all()

    if busqueda_realizada:
        if not mascotas:
            mensaje = "No se encontraron mascotas."
        else:
            for mascota in mascotas:
                fotos = Foto.query.filter_by(mascota_id=mascota.id).all()
                fotos_info = []
                for foto in fotos:
                    ruta_relativa = normalizar_ruta_foto(foto.ruta)
                    if ruta_relativa:
                        ruta_para_template = f"static/{ruta_relativa}"
                        url_absoluta = url_for("static", filename=ruta_relativa)
                    else:
                        ruta_para_template = ""
                        url_absoluta = ""
                    fotos_info.append({
                        "tipo_foto": foto.tipo_foto,
                        "ruta": ruta_para_template,
                        "url": url_absoluta
                    })
                mascotas_con_fotos.append((mascota, fotos_info))

    return render_template(
        "buscar.html",
        mascotas=mascotas,
        filtros=filtros,
        busqueda_realizada=busqueda_realizada,
        mensaje=mensaje,
        mascotas_con_fotos=mascotas_con_fotos,
    )


@main.route("/modificar_mascotas", methods=["GET", "POST"])
def modificar_mascotas():
    busqueda_realizada = request.method == "POST"
    mensaje = None

    query = Mascota.query

    if request.method == "POST":
        filtros = {
            "tipo_registro": (request.form.get("tipo_registro") or "").lower(),
            "nombre": (request.form.get("nombre") or "").strip(),
            "especie": (request.form.get("especie") or "").strip(),
            "raza": (request.form.get("raza") or "").strip(),
            "zona": (request.form.get("zona") or "").strip(),
            "color": (request.form.get("color") or "").strip(),
            "tamano": (request.form.get("tamano") or "").lower().strip(),
            "descripcion": (request.form.get("descripcion") or "").strip(),
            "sexo": (request.form.get("sexo") or "").lower().strip(),
            "chip": (request.form.get("chip") or "").strip(),
            "peso": (request.form.get("peso") or "").strip(),
            "edad": (request.form.get("edad") or "").strip(),
            "propietario_email": (request.form.get("propietario_email") or "").strip(),
            "propietario_telefono": (request.form.get("propietario_telefono") or "").strip(),
            "fecha_registro": (request.form.get("fecha_registro") or "").strip(),
            "fecha_aparecida": (request.form.get("fecha_aparecida") or "").strip(),
            "estado_aparecida": (request.form.get("estado_aparecida") or "").lower().strip(),
        }

        if filtros["tipo_registro"] in TIPOS_REGISTRO:
            query = query.filter(Mascota.tipo_registro == filtros["tipo_registro"])

        if filtros["nombre"]:
            query = query.filter(Mascota.nombre.ilike(f"%{filtros['nombre']}%"))

        if filtros["especie"]:
            query = query.filter(Mascota.especie.ilike(f"%{filtros['especie']}%"))

        if filtros["raza"]:
            query = query.filter(Mascota.raza.ilike(f"%{filtros['raza']}%"))

        if filtros["zona"]:
            query = query.filter(Mascota.zona.ilike(f"%{filtros['zona']}%"))

        if filtros["color"]:
            query = query.filter(Mascota.color.ilike(f"%{filtros['color']}%"))

        if filtros["tamano"] in TAMANOS:
            query = query.filter(Mascota.tamano == filtros["tamano"])

        if filtros["descripcion"]:
            query = query.filter(Mascota.descripcion.ilike(f"%{filtros['descripcion']}%"))

        if filtros["sexo"] in SEXOS:
            query = query.filter(Mascota.sexo == filtros["sexo"])

        if filtros["chip"]:
            query = query.filter(Mascota.chip.ilike(f"%{filtros['chip']}%"))

        if filtros["peso"]:
            try:
                peso_val = float(filtros["peso"].replace(",", "."))
                query = query.filter(Mascota.peso == peso_val)
            except ValueError:
                flash("Peso inválido. Usa números (puedes emplear coma o punto).", "error")

        if filtros["edad"].isdigit():
            query = query.filter(Mascota.edad == int(filtros["edad"]))

        if filtros["propietario_email"]:
            query = query.filter(Mascota.propietario_email.ilike(f"%{filtros['propietario_email']}%"))

        if filtros["propietario_telefono"]:
            query = query.filter(Mascota.propietario_telefono.ilike(f"%{filtros['propietario_telefono']}%"))

        if filtros["fecha_registro"]:
            fecha_filtrada = parse_fecha(filtros["fecha_registro"])
            if fecha_filtrada:
                query = query.filter(Mascota.fecha_registro == fecha_filtrada)
            else:
                flash("Formato de fecha de registro inválido. Usa dd/mm/aaaa.", "error")

        if filtros["fecha_aparecida"]:
            fecha_ap = parse_fecha(filtros["fecha_aparecida"])
            if fecha_ap:
                query = query.filter(Mascota.fecha_aparecida == fecha_ap)
            else:
                flash("Formato de fecha de aparición inválido.", "error")

        if filtros["estado_aparecida"] in ESTADOS_APARECIDA:
            query = query.filter(Mascota.estado_aparecida == filtros["estado_aparecida"])

    mascotas = query.order_by(Mascota.fecha_registro.desc()).all()

    for mascota in mascotas:
        if getattr(mascota, "fotos", None):
            for foto in mascota.fotos:
                ruta_normalizada = normalizar_ruta_foto(foto.ruta)
                if ruta_normalizada:
                    foto.ruta = f"static/{ruta_normalizada}"

    if busqueda_realizada and not mascotas:
        mensaje = "No se encontraron mascotas."

    return render_template(
        "modificar.html",
        mascotas=mascotas,
        busqueda_realizada=busqueda_realizada,
        mensaje=mensaje,
    )


# =============================
# VERIFICACIÓN AJAX DUPLICADOS
# =============================

@main.route("/verificar_mascota", methods=["POST"])
def verificar_mascota():
    tipo_registro = (request.args.get("tipo_registro") or "desaparecida").lower()
    nombre = (request.form.get("nombre") or "").strip()
    especie = (request.form.get("especie") or "").strip()
    raza = (request.form.get("raza") or "").strip()

    existe = False
    if tipo_registro == "desaparecida" and nombre and especie and raza:
        existe = (
            Mascota.query.filter_by(
                tipo_registro=tipo_registro,
                nombre=nombre,
                especie=especie,
                raza=raza
            ).first()
            is not None
        )

    return jsonify({"existe": existe})


# =============================
# COMPARAR FOTOS
# =============================

@main.route("/comparar_fotos", methods=["GET", "POST"])
def comparar_fotos():
    resultado = None
    error = None

    if request.method == "POST":
        imagenes = request.files.getlist("fotos")
        imagenes_validas = [img for img in imagenes if img and allowed_file(img.filename)]
        if not imagenes_validas:
            error = "Debes subir al menos una imagen válida (jpg, png, webp, gif)."
            return render_template("comparar.html", resultado=resultado, error=error)

        rutas = []
        for img in imagenes_validas:
            nombre = secure_filename(f"{uuid.uuid4().hex}_{img.filename}")
            ruta_fs = os.path.join(UPLOAD_FOLDER, nombre)
            img.save(ruta_fs)
            rutas.append(ruta_fs)

        try:
            if len(rutas) == 1:
                data1 = image_to_data_url(rutas[0])
                resp = client.chat.completions.create(
                    model="gpt-5",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Identifica la raza del perro en esta imagen:"},
                            {"type": "image_url", "image_url": {"url": data1}},
                        ]
                    }]
                )
                resultado = resp.choices[0].message.content

            elif len(rutas) >= 2:
                data_urls = [image_to_data_url(p) for p in rutas[:2]]
                mensajes = [
                    {"type": "text", "text": "¿Son el mismo perro o distintos? Da un porcentaje aproximado de match (0-100%) y explica brevemente por qué."},
                    {"type": "image_url", "image_url": {"url": data_urls[0]}},
                    {"type": "image_url", "image_url": {"url": data_urls[1]}},
                ]
                resp = client.chat.completions.create(
                    model="gpt-5",
                    messages=[{"role": "user", "content": mensajes}]
                )
                resultado = resp.choices[0].message.content

        except Exception as e:
            error = f"Error al procesar las imágenes: {e}"

    return render_template("comparar.html", resultado=resultado, error=error)