import os
import re
import uuid
import base64
from collections import defaultdict
from datetime import datetime, date
from threading import Thread
from typing import List, Dict

import io
import mimetypes

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, jsonify, current_app,
    send_file, abort
)
from flask import has_request_context

from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from .models import db, Mascota, FotoMascotaDesaparecida as Foto
from .utils.envia_mail import send_pet_email

# from .utils.prueba_envio_facebook import send_pet_fb_message
from .utils.publicar_fb import publish_pet_fb_post

from .utils.comparar_fotos_todas import comparar_fotos_todas
from .utils.identificar_raza import identificar_raza
from openai import OpenAI

from .utils.cp_localidades import cp_localidades

from .utils.calcula_KM_con_CP import calcula_KM_con_CP  # nuevo import

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

PROMPT_IDENTIFICAR_RAZA = "Identifica la raza del perro en esta imagen:"
PROMPT_COMPARAR_DOS = (
    "¿Son el mismo perro o distintos? Da un porcentaje aproximado de match (0-100%) "
    "y explica brevemente por qué."
)

CODIGO_POSTAL_REGEX = re.compile(r"^\d{5}$")
RADIO_MAX_KM = 100
KM_POR_DIA = 20
RADIO_MINIMO_KM  = 20  # mínimo radio permitido

@main.route("/api/localidades/<codigo_postal>")
def api_localidades(codigo_postal: str):
    codigo_postal = (codigo_postal or "").strip()
    if len(codigo_postal) != 5 or not codigo_postal.isdigit():
        return jsonify({"error": "El código postal debe tener 5 dígitos."}), 400

    localidades = cp_localidades(codigo_postal)
    return jsonify({"localidades": localidades})

def normalizar_codigo_postal(valor: str | None) -> str:
    if not valor:
        return ""
    solo_digitos = re.sub(r"\D", "", valor.strip())
    if len(solo_digitos) >= 5:
        return solo_digitos[:5]
    return solo_digitos

def validar_codigo_postal(valor: str | None) -> bool:
    return bool(CODIGO_POSTAL_REGEX.match(valor or ""))

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def _get_static_root() -> str:
    try:
        static_root = current_app.static_folder
    except RuntimeError:
        static_root = None
    elegido = static_root or STATIC_DIR
    return elegido


def _resolver_ruta_absoluta(ruta_rel: str) -> str:
    ruta_abs = os.path.join(_get_static_root(), ruta_rel.replace("/", os.sep))
    return ruta_abs


def _extraer_ruta_absoluta_payload(info: dict | None) -> str | None:
    """
    Dado el diccionario de una foto enviado desde el frontend, intenta obtener
    la ruta absoluta en disco. Soporta distintos nombres de campo y rutas
    relativas (ej. 'static/fotos/...', '/static/...', 'fotos/...').
    """
    if not info or not isinstance(info, dict):
        return None

    posibles_claves = [
        "ruta_abs",
        "ruta_absoluta",
        "ruta",
        "ruta_rel",
        "ruta_relativa",
        "path",
        "filepath",
        "file_path",
        "url",
    ]

    for clave in posibles_claves:
        valor = info.get(clave)
        if not valor or not isinstance(valor, str):
            continue
        ruta = valor.strip()
        if not ruta:
            continue

        # Si ya viene en absoluto y existe, usarla directamente.
        if os.path.isabs(ruta) and os.path.isfile(ruta):
            return ruta

        ruta_norm = normalizar_ruta_foto(ruta)
        if ruta_norm:
            ruta_abs = _resolver_ruta_absoluta(ruta_norm)
            if os.path.isfile(ruta_abs):
                return ruta_abs

    return None


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def image_bytes_to_data_url(data: bytes, mime_type: str | None = None, nombre_archivo: str | None = None) -> str:
    if not mime_type and nombre_archivo:
        mime_type = mimetypes.guess_type(nombre_archivo)[0]
    mime = mime_type or "application/octet-stream"
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{b64}"

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
    if not ruta:
        return None
    ruta = ruta.strip().replace("\\", "/")
    partes = [p for p in ruta.split("/") if p]
    if not partes:
        return None
    partes_lower = [p.lower() for p in partes]
    if "static" in partes_lower:
        idx = partes_lower.index("static")
        partes = partes[idx + 1:]
        partes_lower = partes_lower[idx + 1:]
    if "fotos" in partes_lower:
        idx = partes_lower.index("fotos")
        partes = partes[idx:]
    ruta_normalizada = "/".join(partes)
    return ruta_normalizada or None


def eliminar_archivo_relativo(ruta_rel: str | None) -> None:
    if not ruta_rel:
        return
    ruta_norm = normalizar_ruta_foto(ruta_rel)
    if not ruta_norm:
        return
    ruta_abs = _resolver_ruta_absoluta(ruta_norm)
    try:
        if os.path.isfile(ruta_abs):
            os.remove(ruta_abs)
    except OSError:
        current_app.logger.warning("No se pudo eliminar el archivo de foto %s", ruta_abs)

def eliminar_foto_obj(foto: Foto | None) -> None:
    if not foto:
        return
    # Ya no borramos el archivo del sistema de ficheros, solo el registro en BD
    db.session.delete(foto)


from flask import has_request_context, url_for, current_app  # current_app ya lo importas arriba

def _foto_url(foto_id: int) -> str:
    """
    Devuelve la URL absoluta del endpoint de la foto.
    - Si hay contexto de petición: usa url_for con _external=True.
    - Si no hay contexto (tareas en segundo plano/CLI): usa EXTERNAL_BASE_URL.
    """
    if has_request_context():
        return url_for("main.ver_foto", foto_id=foto_id, _external=True)

    base = current_app.config.get("EXTERNAL_BASE_URL")
    if base:
        return f"{base.rstrip('/')}/foto/{foto_id}"

    raise RuntimeError(
        "No hay contexto de petición y no se definió EXTERNAL_BASE_URL; "
        "no se puede construir la URL de la foto."
    )


@main.route("/foto/<int:foto_id>")
def ver_foto(foto_id: int):
    foto = Foto.query.get_or_404(foto_id)

    if foto.data:
        return send_file(
            io.BytesIO(foto.data),
            mimetype=foto.mime_type or "application/octet-stream",
            download_name=foto.nombre_archivo or None,
        )

    # Sin datos binarios, devolvemos 404
    abort(404)

def obtener_fotos_existentes(mascota: Mascota) -> List[Dict[str, str]]:
    fotos_serializadas: List[Dict[str, str]] = []
    for foto in getattr(mascota, "fotos", []):
        fotos_serializadas.append({
            "id": foto.id,
            "tipo_foto": foto.tipo_foto or "desconocido",
            "ruta": None,               # o elimina esta línea si no la necesitas
            "url": _foto_url(foto.id),  # endpoint /foto/<id>
        })
    return fotos_serializadas

def _construir_mascotas_con_fotos(mascotas):
    resultado = []
    for mascota in mascotas:
        fotos = Foto.query.filter_by(mascota_id=mascota.id).all()
        fotos_info = []
        for foto in fotos:
            fotos_info.append({
                "id": foto.id,
                "tipo_foto": foto.tipo_foto or "desconocido",
                "url": _foto_url(foto.id),
                "ruta": None,  # si no necesitas esta clave, puedes eliminar esta línea
            })
        resultado.append((mascota, fotos_info))
    return resultado


def _es_mascota_desaparecida_valida(mascota: Mascota | None) -> bool:
    if not mascota or (mascota.tipo_registro or "").lower() != "desaparecida":
        return False
    if not (mascota.propietario_email and mascota.propietario_email.strip()):
        return False
    if mascota.fecha_aparecida is not None:
        return False
    estado = (mascota.estado_aparecida or "").strip()
    if estado:
        return False
    return True

def _serializar_foto(foto: Foto) -> Dict[str, str | None]:
    tipo = (foto.tipo_foto or "desconocido").strip().lower() or "desconocido"
    return {
        "id": foto.id,
        "tipo_foto": tipo,
        "ruta_rel": None,
        "ruta_abs": None,
        "url": _foto_url(foto.id),
    }


def _obtener_fotos_validas(mascota: Mascota | None) -> List[Dict[str, str]]:
    if not mascota:
        return []
    fotos_validas: List[Dict[str, str]] = []
    for foto in getattr(mascota, "fotos", []):
        datos = _serializar_foto(foto)
        if datos:
            fotos_validas.append(datos)
    return fotos_validas


def _agrupar_fotos_por_tipo(fotos: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    agrupado: dict[str, list[dict[str, str]]] = defaultdict(list)
    for foto in fotos:
        agrupado[foto["tipo_foto"]].append(foto)
    return dict(agrupado)


def _comparar_imagenes_openai(prompt: str, data_urls: List[str]) -> str:
    mensajes = [{"type": "text", "text": prompt}]
    for data_url in data_urls:
        mensajes.append({"type": "image_url", "image_url": {"url": data_url}})
    respuesta = client.chat.completions.create(
        model="gpt-5.2",
        messages=[{"role": "user", "content": mensajes}]
    )
    return respuesta.choices[0].message.content


def _cargar_smtp_env(app) -> None:
    app.config["SMTP_SERVER"] = os.getenv("SMTP_SERVER", "")
    app.config["SMTP_PORT"] = int(os.getenv("SMTP_PORT", "587"))
    app.config["SMTP_USERNAME"] = os.getenv("SMTP_USERNAME", "")
    app.config["SMTP_PASSWORD"] = os.getenv("SMTP_PASSWORD", "")
    app.config["SMTP_TO_EMAIL"] = os.getenv("SMTP_TO_EMAIL", "")


def _programar_envio_correo(mascota_id: int) -> None:
    try:
        app = current_app._get_current_object()
        _cargar_smtp_env(app)
        Thread(
            target=_worker_enviar_correo,
            args=(app, mascota_id),
            daemon=True
        ).start()
    except Exception:
        current_app.logger.exception(
            "No se pudo programar el envío de correo para la mascota %s", mascota_id
        )

def _worker_enviar_correo(app, mascota_id: int) -> None:
    with app.app_context():
        mascota = Mascota.query.get(mascota_id)
        if not mascota:
            current_app.logger.error(
                "No se encontró la mascota %s para enviar correo.", mascota_id
            )
            return


        subject = (
            f"🐶🐱 mascota {(mascota.tipo_registro or '').strip()}".strip() or "Mascota"
        )
        datos_email = _construir_datos_email(mascota)
        fotos_detalle = _obtener_rutas_fotos(mascota)
        destinatarios_extra = _calcular_destinatarios_extra(mascota)

        ok_email = send_pet_email(
            subject,
            datos_email,
            fotos_detalle,
            destinatarios_extra=destinatarios_extra,
        )

        if not ok_email:
            current_app.logger.error(
                "Fallo al enviar correo automático de mascota %s", mascota_id
            )

        ok_fb_post = publish_pet_fb_post(
            subject,
            datos_email,
            fotos_detalle,
        )
              
        if not ok_fb_post:
            current_app.logger.error(
                "Fallo al publicar en el feed de Facebook de la mascota %s", mascota_id
            )

def _construir_datos_email(mascota: Mascota) -> Dict[str, object]:
    return {
        "ID": mascota.id,
        "Tipo de registro": mascota.tipo_registro,
        "Nombre": mascota.nombre,
        "Especie": mascota.especie,
        "Raza": mascota.raza,
        "Edad": mascota.edad,
        "Zona": mascota.zona,
        "Código postal": mascota.codigo_postal,
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

def _obtener_rutas_fotos(mascota: Mascota | None) -> List[Dict[str, object]]:
    """
    Devuelve, para cada foto de la mascota, un diccionario con toda la
    información necesaria para reutilizarla (binarios incluidos).
    """
    fotos_info: List[Dict[str, object]] = []

    if not mascota:
        return fotos_info

    for foto in getattr(mascota, "fotos", []):
        fotos_info.append(
            {
                "id": foto.id,
                "tipo_foto": foto.tipo_foto or "desconocido",
                "ruta_rel": None,
                "ruta_abs": None,
                "url": _foto_url(foto.id),
                "data": foto.data,
                "mime_type": foto.mime_type,
                "nombre_archivo": foto.nombre_archivo,
                "tamano_bytes": foto.tamano_bytes,
            }
        )

    return fotos_info

def _calcular_radio_permitido(fecha_desaparecida: date, fecha_encontrada: date) -> int:
    dias = max((fecha_encontrada - fecha_desaparecida).days, 0)
    dias_efectivos = max(1, dias)  # garantiza al menos 1 día
    return min(RADIO_MAX_KM, dias_efectivos * KM_POR_DIA)

def _calcular_destinatarios_extra(mascota: Mascota) -> List[str]:
    destinatarios: List[str] = []
    correo_propietario = (mascota.propietario_email or "").strip()
    if correo_propietario:
        destinatarios.append(correo_propietario)

    if (mascota.tipo_registro or "").lower() != "encontrada":
        return destinatarios

    # Traemos todos los datos necesarios para el filtro de distancia
    registros_previos = (
        Mascota.query.with_entities(
            Mascota.propietario_email,
            Mascota.codigo_postal,
            Mascota.zona,
            Mascota.fecha_registro,
        )
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

    cp_encontrada = (mascota.codigo_postal or "").strip()
    zona_encontrada = (mascota.zona or "").strip()

    for correo, cp_desap, zona_desap, fecha_desap in registros_previos:
        correo_norm = (correo or "").strip()
        if not correo_norm or correo_norm in destinatarios:
            continue

        incluir = True

        if (
            mascota.fecha_registro
            and fecha_desap
            and cp_encontrada
            and zona_encontrada
            and cp_desap
            and zona_desap
        ):
            radio_permitido = _calcular_radio_permitido(fecha_desap, mascota.fecha_registro)
            if radio_permitido > 0:
                distancia = calcula_KM_con_CP(cp_encontrada, zona_encontrada, cp_desap, zona_desap)
                if distancia is not None and distancia > radio_permitido:
                    incluir = False

        if incluir:
            destinatarios.append(correo_norm)

    return destinatarios


def _calcular_destinatarios_extra(mascota: Mascota) -> List[str]:
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


def construir_filtros_generales(form) -> Dict[str, str]:
    return {
        "tipo_registro": (form.get("tipo_registro") or "").lower(),
        "nombre": (form.get("nombre") or "").strip(),
        "especie": (form.get("especie") or "").strip(),
        "raza": (form.get("raza") or "").strip(),
        "zona": (form.get("zona") or "").strip(),
        "codigo_postal": normalizar_codigo_postal(form.get("codigo_postal")),
        "color": (form.get("color") or "").strip(),
        "tamano": (form.get("tamano") or "").strip().lower(),
        "descripcion": (form.get("descripcion") or "").strip(),
        "sexo": (form.get("sexo") or "").strip().lower(),
        "chip": (form.get("chip") or "").strip(),
        "peso": (form.get("peso") or "").strip(),
        "edad": (form.get("edad") or "").strip(),
        "propietario_email": (form.get("propietario_email") or "").strip(),
        "propietario_telefono": (form.get("propietario_telefono") or "").strip(),
        "fecha_registro": (form.get("fecha_registro") or "").strip(),
        "fecha_aparecida": (form.get("fecha_aparecida") or "").strip(),
        "estado_aparecida": (form.get("estado_aparecida") or "").strip().lower(),
    }


def aplicar_filtros_generales(query, filtros: Dict[str, str]):
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

    if filtros["codigo_postal"]:
        query = query.filter(Mascota.codigo_postal == filtros["codigo_postal"])

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

    return query


@main.route("/")
def index():
    return render_template("index.html")

@main.route("/crear_mascota", methods=["GET", "POST"])
@main.route("/mascotas/<int:mascota_id>/editar", methods=["GET", "POST"])
def crear_mascota(mascota_id=None):
    edit_mode = mascota_id is not None
    mascota = None

    if edit_mode:
        mascota = Mascota.query.get_or_404(mascota_id)
        tipo_registro = (mascota.tipo_registro or "desaparecida").lower()
    else:
        tipo_registro = (request.args.get("tipo_registro") or "desaparecida").lower()
        if tipo_registro not in TIPOS_REGISTRO:
            flash("Tipo de registro inválido.", "error")
            return redirect(url_for("main.index"))

    if request.method == "POST":

        print("FORM COMPLETO:", request.form.to_dict(flat=False))
        print("FILES:", [f.filename for f in request.files.getlist('fotos')])

        print("[DBG CREAR] POST recibido:",
              "args.tipo_registro=", request.args.get("tipo_registro"),
              "form.tipo_registro=", request.form.get("tipo_registro"))

        tipo_registro_form = (request.form.get("tipo_registro") or '').strip().lower()
        if edit_mode and tipo_registro_form in TIPOS_REGISTRO:
            tipo_registro = tipo_registro_form
        elif not edit_mode and tipo_registro_form:
            tipo_registro = tipo_registro_form

        if not edit_mode and tipo_registro not in TIPOS_REGISTRO:
            flash("Tipo de registro inválido.", "error")
            return redirect(url_for("main.index"))

        nombre = (request.form.get("nombre") or "").strip()
        especie = (request.form.get("especie") or "").strip()
        raza = (request.form.get("raza") or "").strip()
        edad = (request.form.get("edad") or "").strip()
        propietario_email = (request.form.get("propietario_email") or "").strip()
        propietario_telefono = (request.form.get("propietario_telefono") or "").strip()
        zona = (request.form.get("zona") or "").strip()
        codigo_postal_raw = request.form.get("codigo_postal")
        codigo_postal = normalizar_codigo_postal(codigo_postal_raw)
        color = (request.form.get("color") or "").strip()
        sexo = (request.form.get("sexo") or "").strip().lower()
        chip = (request.form.get("chip") or "").strip()
        peso = (request.form.get("peso") or "").strip()
        tamano = (request.form.get("tamano") or "").strip().lower()
        descripcion = (request.form.get("descripcion") or "").strip()
        fecha_registro_str = (request.form.get("fecha_registro") or "").strip()

        if not validar_codigo_postal(codigo_postal):
            flash("Debes indicar un código postal válido de 5 dígitos.", "error")
            return redirect(request.url)

        if tipo_registro == "encontrada" and sexo not in SEXOS:
            sexo = "no_sabe"
            print("[DBG CREAR] sexo vacío en encontrada -> forzado a 'no_sabe'")

        print("[DBG CREAR] Campos crudos:",
              "nombre=", repr(nombre),
              "especie=", repr(especie),
              "raza=", repr(raza),
              "zona=", repr(zona),
              "codigo_postal=", repr(codigo_postal),
              "color=", repr(color),
              "sexo=", repr(sexo),
              "tamano=", repr(tamano),
              "email=", repr(propietario_email),
              "tel=", repr(propietario_telefono),
              "fecha_registro=", repr(fecha_registro_str))

        if tipo_registro == "encontrada":
            nombre = "encontrada"

        print("[DBG CREAR] Tipo y nombre efectivos:",
              "tipo_registro=", tipo_registro,
              "nombre=", nombre)

        if not nombre:
            flash("El nombre de la mascota es obligatorio.", "error")
            return redirect(request.url)

        if not especie or not color or sexo not in SEXOS or tamano not in TAMANOS:
            flash("Faltan datos obligatorios (especie, color, sexo, tamaño).", "error")
            return redirect(request.url)

        if not codigo_postal:
            flash("El código postal es obligatorio.", "error")
            return redirect(request.url)

        edad_val = int(edad) if edad.isdigit() else None

        peso_val = None
        if peso:
            try:
                peso_val = float(peso.replace(",", "."))
            except ValueError:
                flash("Peso inválido. Usa números (puedes emplear coma o punto).", "error")
                return redirect(request.url)

        fecha_registro = parse_fecha(fecha_registro_str)
        if not fecha_registro:
            fecha_registro = mascota.fecha_registro if edit_mode and mascota.fecha_registro else datetime.utcnow().date()

        print("[DBG CREAR] Normalizados:",
              "especie=", repr(especie),
              "raza=", repr(raza),
              "zona=", repr(zona),
              "codigo_postal=", repr(codigo_postal),
              "color=", repr(color),
              "sexo=", repr(sexo),
              "tamano=", repr(tamano),
              "fecha_registro=", fecha_registro)
        print("[DBG CREAR] Obligatorios presentes?",
              "zona=", bool(zona),
              "email=", bool(propietario_email),
              "tel=", bool(propietario_telefono))

        email_norm = (propietario_email or "").strip().lower()
        dup_q = Mascota.query.filter_by(
            propietario_email=email_norm,
            tipo_registro=tipo_registro,
            nombre=(nombre or "").strip().lower(),
            zona=(zona or "").strip().lower(),
            codigo_postal=codigo_postal,
            especie=(especie or "").strip().lower(),
            color=(color or "").strip().lower(),
            tamano=(tamano or "").strip().lower(),
            fecha_registro=fecha_registro
        )
        if edit_mode:
            dup_q = dup_q.filter(Mascota.id != mascota.id)

        try:
            dup_count = dup_q.count()
        except Exception as e:
            dup_count = f"error count: {e}"
        print("[DBG CREAR] Duplicados (clave UNIQUE) encontrados:", dup_count)

        if dup_q.first():
            print("[DBG CREAR] BLOQUEADO por duplicado según clave UNIQUE")
            flash("Ya existe un registro igual (email, tipo, nombre, zona, código postal, especie, color, tamaño y fecha).", "error")
            return redirect(request.url)

        if edit_mode:
            mascota.tipo_registro = tipo_registro
            mascota.nombre = nombre
            mascota.especie = especie
            mascota.raza = raza or None
            mascota.edad = edad_val
            mascota.propietario_email = propietario_email or None
            mascota.propietario_telefono = propietario_telefono or None
            mascota.zona = zona or None
            mascota.codigo_postal = codigo_postal
            mascota.color = color
            mascota.descripcion = descripcion or None
            mascota.chip = chip or None
            mascota.sexo = sexo
            mascota.peso = peso_val
            mascota.tamano = tamano
            mascota.fecha_registro = fecha_registro
        else:
            mascota = Mascota(
                tipo_registro=tipo_registro,
                nombre=nombre,
                especie=especie,
                raza=raza or None,
                edad=edad_val,
                propietario_email=propietario_email or None,
                propietario_telefono=propietario_telefono or None,
                zona=zona or None,
                codigo_postal=codigo_postal,
                color=color,
                descripcion=descripcion or None,
                chip=chip or None,
                sexo=sexo,
                peso=peso_val,
                tamano=tamano,
                fecha_registro=fecha_registro
            )
            db.session.add(mascota)

        print("[DBG CREAR] Antes de flush: mascota.id=", getattr(mascota, "id", None))
        try:
            db.session.flush()
        except IntegrityError as exc:
            print("[DBG CREAR] IntegrityError en flush:", repr(exc))
            try:
                print("[DBG CREAR] IntegrityError.orig:", getattr(exc, "orig", None))
                if getattr(exc, "orig", None) is not None and hasattr(exc.orig, "args"):
                    print("[DBG CREAR] IntegrityError.orig.args:", exc.orig.args)
            except Exception:
                pass
            db.session.rollback()
            flash("Error de integridad al guardar la mascota (posible duplicado).", "error")
            return redirect(request.url)

        fotos_eliminar_ids = request.form.getlist("fotos_eliminar_id")
        if edit_mode and fotos_eliminar_ids:
            for foto_id in fotos_eliminar_ids:
                if not foto_id.isdigit():
                    continue
                foto_obj = Foto.query.filter_by(id=int(foto_id), mascota_id=mascota.id).first()
                if foto_obj:
                    eliminar_foto_obj(foto_obj)

        existing_photos_by_type = {}
        if edit_mode:
            for foto in list(mascota.fotos):
                if foto in db.session.deleted:
                    continue
                existing_photos_by_type[foto.tipo_foto] = foto

        fotos = request.files.getlist("fotos")
        tipos_foto = request.form.getlist("fotos_tipo")  # antes ponía "tipo_foto"
        print("[DBG CREAR] files.fotos len=", len(fotos),
              "tipos_foto len=", len(tipos_foto))
        print("[DBG CREAR] tipos_foto=", tipos_foto)

        nuevas_rutas_guardadas: List[str] = []

        for idx, archivo in enumerate(fotos):
            if not archivo or not archivo.filename:
                continue
            if not allowed_file(archivo.filename):
                flash(f"Archivo '{archivo.filename}' ignorado: formato no permitido.", "warning")
                continue

            tipo_actual = tipos_foto[idx] if idx < len(tipos_foto) else ""
            tipo_actual = (tipo_actual or "desconocido").strip().lower()

            if edit_mode and tipo_actual in existing_photos_by_type:
                eliminar_foto_obj(existing_photos_by_type[tipo_actual])
                existing_photos_by_type.pop(tipo_actual, None)

            # --- NUEVO: capturar contenido y metadatos ---
            data_bytes = archivo.read()
            tamano_bytes = len(data_bytes)
            mime_type = archivo.mimetype or mimetypes.guess_type(archivo.filename)[0] or "application/octet-stream"
            nombre_original = secure_filename(archivo.filename)  # guardamos el nombre original “limpio”
            archivo.stream.seek(0)  # IMPORTANTÍSIMO para poder volver a guardar en disco
            # ------------------------------------------------

            nombre_seguro = secure_filename(
                f"{mascota.id}_{tipo_actual}_{uuid.uuid4().hex}_{archivo.filename}"
            )
            ruta_fs = os.path.join(UPLOAD_FOLDER, nombre_seguro)
            archivo.save(ruta_fs)
            nuevas_rutas_guardadas.append(ruta_fs)

            ruta_relativa = normalizar_ruta_foto(f"fotos/{nombre_seguro}")

            db.session.add(
                Foto(
                    mascota_id=mascota.id,
                    tipo_foto=tipo_actual,
                    ruta=ruta_relativa,
                    data=data_bytes,              # nuevo
                    mime_type=mime_type,          # nuevo
                    nombre_archivo=nombre_original,  # nuevo
                    tamano_bytes=tamano_bytes,    # nuevo
                )
            )

        print("[DBG CREAR] Antes de commit: mascota.id=", getattr(mascota, "id", None))
        try:
            db.session.commit()
        except IntegrityError as exc:
            print("[DBG CREAR] IntegrityError en commit:", repr(exc))
            try:
                print("[DBG CREAR] IntegrityError.orig:", getattr(exc, "orig", None))
                if getattr(exc, "orig", None) is not None and hasattr(exc.orig, "args"):
                    print("[DBG CREAR] IntegrityError.orig.args:", exc.orig.args)
            except Exception:
                pass
            db.session.rollback()
            for ruta_guardada in nuevas_rutas_guardadas:
                try:
                    if os.path.isfile(ruta_guardada):
                        os.remove(ruta_guardada)
                except OSError:
                    current_app.logger.warning("No se pudo eliminar archivo %s tras fallo de commit.", ruta_guardada)
            flash("No se pudo guardar los datos de la mascota por un conflicto de integridad.", "error")
            return redirect(request.url)
        except Exception as exc:
            db.session.rollback()
            for ruta_guardada in nuevas_rutas_guardadas:
                try:
                    if os.path.isfile(ruta_guardada):
                        os.remove(ruta_guardada)
                except OSError:
                    current_app.logger.warning("No se pudo eliminar archivo %s tras fallo de commit.", ruta_guardada)
            current_app.logger.exception("Error al guardar la mascota: %s", exc)
            flash("Ocurrió un error al guardar la mascota.", "error")
            return redirect(request.url)

        print("[DBG CREAR] Mascota creada/actualizada OK. id=", mascota.id, "tipo=", mascota.tipo_registro)

        if edit_mode:
            flash("Mascota actualizada correctamente.", "success")
            _programar_envio_correo(mascota.id)
            return redirect(url_for("main.modificar_mascotas"))
        else:
            flash(f"Mascota {tipo_registro} registrada correctamente.", "success")
            _programar_envio_correo(mascota.id)
            return redirect(url_for("main.index"))

    fotos_existentes = obtener_fotos_existentes(mascota) if edit_mode else []
    form_action = (
        url_for("main.crear_mascota", mascota_id=mascota.id)
        if edit_mode else
        url_for("main.crear_mascota", tipo_registro=tipo_registro)
    )

    return render_template(
        "crear_mascota.html",
        tipo_registro=tipo_registro,
        modo="modificar" if edit_mode else "crear",
        mascota=mascota,
        fotos_existentes=fotos_existentes,
        form_action=form_action
    )


@main.route("/mascotas/<int:mascota_id>/eliminar", methods=["POST"])
def eliminar_mascota(mascota_id):
    mascota = Mascota.query.get_or_404(mascota_id)

    for foto in list(mascota.fotos):
        eliminar_foto_obj(foto)

    try:
        db.session.delete(mascota)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Error al eliminar mascota %s: %s", mascota_id, exc)
        flash("No se pudo eliminar la mascota.", "error")
        return redirect(url_for("main.modificar_mascotas"))

    flash("Mascota eliminada correctamente.", "success")
    return redirect(url_for("main.modificar_mascotas"))


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
            "codigo_postal": normalizar_codigo_postal(request.form.get("codigo_postal")),
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

        if filtros["codigo_postal"]:
            query = query.filter(Mascota.codigo_postal == filtros["codigo_postal"])

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
    else:
        filtros["codigo_postal"] = ""

    mascotas = query.order_by(Mascota.fecha_registro.desc()).all()

    if busqueda_realizada:
        if not mascotas:
            mensaje = "No se encontraron mascotas."
        else:
            mascotas_con_fotos = _construir_mascotas_con_fotos(mascotas)

    return render_template(
        "buscar.html",
        modo="buscar",
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
    mascotas_con_fotos = []

    query = Mascota.query
    filtros = construir_filtros_generales(request.form)

    if request.method == "POST":
        query = aplicar_filtros_generales(query, filtros)

    mascotas = query.order_by(Mascota.fecha_registro.desc()).all()

    if busqueda_realizada:
        if not mascotas:
            mensaje = "No se encontraron mascotas."
        else:
            mascotas_con_fotos = _construir_mascotas_con_fotos(mascotas)

    return render_template(
        "buscar.html",
        modo="modificar",
        mascotas=mascotas,
        filtros=filtros,
        busqueda_realizada=busqueda_realizada,
        mensaje=mensaje,
        mascotas_con_fotos=mascotas_con_fotos,
    )


@main.route("/comparar_mascotas/desaparecidas", methods=["GET", "POST"])
def comparar_mascotas_desaparecidas():
    busqueda_realizada = request.method == "POST"
    mensaje = None

   # --- NUEVO: detectar si se pidió el modo “identificar raza” ---
    modo_param = (
        request.args.get("modo")
        or request.form.get("modo")
        or ""
    ).strip().lower()
    modo_vista = "identificar_raza" if modo_param == "identificar_raza" else "comparar_desaparecidas"
    # ----------------------------------------------------------------

    query = Mascota.query.filter(
        Mascota.tipo_registro == "desaparecida",
        Mascota.propietario_email.isnot(None),
        Mascota.propietario_email != "",
        Mascota.fecha_aparecida.is_(None),
        or_(Mascota.estado_aparecida.is_(None), Mascota.estado_aparecida == ""),
    )

    filtros = construir_filtros_generales(request.form)
    filtros["tipo_registro"] = "desaparecida"

    if request.method == "POST":
        query = aplicar_filtros_generales(query, filtros)

    mascotas = query.order_by(Mascota.fecha_registro.desc()).all()
    if busqueda_realizada and not mascotas:
        mensaje = "No se localizaron mascotas desaparecidas que cumplan los criterios."

    mascotas_con_fotos = _construir_mascotas_con_fotos(mascotas) if mascotas else []

    return render_template(
        "buscar.html",
        modo=modo_vista,
        mascotas=mascotas,
        filtros=filtros,
        busqueda_realizada=busqueda_realizada,
        mensaje=mensaje,
        mascotas_con_fotos=mascotas_con_fotos,
    )

@main.route("/mascotas/<int:mascota_id>/identificar_raza", methods=["POST"])
def identificar_raza_api(mascota_id: int):
    mascota = Mascota.query.get_or_404(mascota_id)
    if (mascota.tipo_registro or "").lower() != "desaparecida":
        return jsonify({"ok": False, "mensaje": "Solo se pueden identificar razas de mascotas registradas como desaparecidas."}), 400

    # Genera data: URLs desde los binarios almacenados
    fotos_obj = [f for f in mascota.fotos if f.data]
    data_urls = [
        image_bytes_to_data_url(f.data, f.mime_type, f.nombre_archivo)
        for f in fotos_obj
    ][:5]  # opcional: límite de 5

    if not data_urls:
        return jsonify({"ok": False, "mensaje": "Esta mascota no tiene fotos disponibles para identificar la raza."}), 400

    try:
        resultado = identificar_raza(data_urls)
    except ValueError as exc:
        return jsonify({"ok": False, "mensaje": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("Error al identificar raza para la mascota %s", mascota_id)
        return jsonify({"ok": False, "mensaje": f"Ocurrió un error al identificar la raza: {exc}"}), 500

    return jsonify({"ok": True, "resultado": resultado})


@main.route("/comparar_mascotas/<int:desaparecida_id>/candidatas", methods=["GET"])
def comparar_mascotas_candidatas(desaparecida_id: int):
    desaparecida = Mascota.query.get_or_404(desaparecida_id)

    if not _es_mascota_desaparecida_valida(desaparecida):
        flash("La mascota seleccionada no cumple los requisitos para comparar.", "error")
        return redirect(url_for("main.comparar_mascotas_desaparecidas"))

    if not _obtener_fotos_validas(desaparecida):
        flash("Para comparar fotos, solo se pueden seleccionar registros con fotos.", "error")
        return redirect(url_for("main.comparar_mascotas_desaparecidas"))

    candidatas_query = Mascota.query.filter(
        Mascota.tipo_registro == "encontrada",
        Mascota.id != desaparecida.id,
        Mascota.fotos.any(),
    )

     # Restringir a la misma especie
    especie_ref = (desaparecida.especie or "").strip()
    if especie_ref:
        candidatas_query = candidatas_query.filter(
            func.lower(Mascota.especie) == especie_ref.lower()
        )

    if desaparecida.fecha_registro:
        candidatas_query = candidatas_query.filter(
            Mascota.fecha_registro >= desaparecida.fecha_registro
        )

    candidatas = candidatas_query.order_by(Mascota.fecha_registro.asc()).all()
    candidatas_con_fotos = _construir_mascotas_con_fotos(candidatas)

    if not candidatas:
        flash(
            "No se encontraron mascotas encontradas con fotos posteriores a la fecha de desaparición.",
            "warning"
        )

    return render_template(
        "comparar_candidatas.html",
        mascota_desaparecida=desaparecida,
        candidatas=candidatas,
        candidatas_con_fotos=candidatas_con_fotos,
    )


@main.route(
    "/comparar_mascotas/<int:desaparecida_id>/con/<int:encontrada_id>",
    methods=["GET", "POST"]
)
def comparar_mascotas_detalle(desaparecida_id: int, encontrada_id: int):
    mascota_desaparecida = Mascota.query.get_or_404(desaparecida_id)
    mascota_encontrada = Mascota.query.get_or_404(encontrada_id)

    if not _es_mascota_desaparecida_valida(mascota_desaparecida):
        flash("La mascota desaparecida seleccionada ya no es válida para comparar.", "error")
        return redirect(url_for("main.comparar_mascotas_desaparecidas"))

    if (mascota_encontrada.tipo_registro or "").lower() != "encontrada":
        flash("La mascota encontrada seleccionada no es válida.", "error")
        return redirect(url_for("main.comparar_mascotas_candidatas", desaparecida_id=desaparecida_id))

    fotos_desap = _obtener_fotos_validas(mascota_desaparecida)
    fotos_encon = _obtener_fotos_validas(mascota_encontrada)

    if not fotos_desap or not fotos_encon:
        flash("No hay fotos suficientes para realizar la comparación.", "error")
        return redirect(url_for("main.comparar_mascotas_candidatas", desaparecida_id=desaparecida_id))

    fotos_desap_por_tipo = _agrupar_fotos_por_tipo(fotos_desap)
    fotos_encon_por_tipo = _agrupar_fotos_por_tipo(fotos_encon)
    tipos_comunes = sorted(set(fotos_desap_por_tipo.keys()) & set(fotos_encon_por_tipo.keys()))

    tipos_compartidos = {
        "desaparecida": sorted([tipo for tipo, fotos in fotos_desap_por_tipo.items() if fotos]),
        "encontrada": sorted([tipo for tipo, fotos in fotos_encon_por_tipo.items() if fotos]),
    }

    diagnostico_individual = None
    diagnosticos_globales: List[Dict[str, object]] = []
    error = None

    fotos_desap_dict = {str(foto["id"]): foto for foto in fotos_desap}
    fotos_encon_dict = {str(foto["id"]): foto for foto in fotos_encon}
    data_url_cache: Dict[int, str] = {}

    def _get_data_url_from_id(foto_id: int) -> str:
        if foto_id in data_url_cache:
            return data_url_cache[foto_id]
        foto_obj = Foto.query.get(foto_id)
        if not foto_obj or not foto_obj.data:
            raise ValueError("No se encontró la foto en la base de datos.")
        data_url_cache[foto_id] = image_bytes_to_data_url(
            foto_obj.data,
            foto_obj.mime_type,
            foto_obj.nombre_archivo,
        )
        return data_url_cache[foto_id]

    if request.method == "POST":
        accion = (request.form.get("accion") or "").strip()

        if accion == "comparar_tipo":
            tipo = (request.form.get("tipo_foto") or "").strip().lower()
            foto_desap_id = request.form.get("foto_desaparecida") or ""
            foto_encon_id = request.form.get("foto_encontrada") or ""

            if tipo not in tipos_comunes:
                error = "El tipo de foto seleccionado no es válido."
            else:
                foto_desap = fotos_desap_dict.get(foto_desap_id)
                foto_encon = fotos_encon_dict.get(foto_encon_id)

                if not foto_desap or not foto_encon:
                    error = "Debes seleccionar una foto de cada mascota."
                elif foto_desap["tipo_foto"] != tipo or foto_encon["tipo_foto"] != tipo:
                    error = "Las fotos seleccionadas no coinciden con el tipo elegido."
                else:
                    try:
                        data_desap = _get_data_url_from_id(foto_desap["id"])
                        data_encon = _get_data_url_from_id(foto_encon["id"])
                        prompt = (
                            f"Compara estas dos fotos de perros (tipo de foto: {tipo}). "
                            "¿Corresponden al mismo perro? Da un porcentaje aproximado de match "
                            "(0-100%) y explica brevemente tu conclusión."
                        )
                        resultado = _comparar_imagenes_openai(prompt, [data_desap, data_encon])
                        diagnostico_individual = {
                            "tipo": tipo,
                            "foto_desap": foto_desap,
                            "foto_encon": foto_encon,
                            "resultado": resultado,
                        }
                    except Exception as exc:
                        current_app.logger.exception(
                            "Error al comparar fotos (tipo igual) desaparecida %s vs encontrada %s",
                            desaparecida_id,
                            encontrada_id
                        )
                        error = f"Error al comparar las fotos: {exc}"

        elif accion == "comparar_todas":
            for foto_desap in fotos_desap:
                try:
                    data_desap = _get_data_url_from_id(foto_desap["id"])
                except Exception as exc:
                    current_app.logger.exception(
                        "Error al convertir la foto %s de la desaparecida %s",
                        foto_desap["id"],
                        desaparecida_id
                    )
                    diagnosticos_globales.append({
                        "foto_desap": foto_desap,
                        "foto_encon": None,
                        "resultado": f"No se pudo procesar la foto de la desaparecida: {exc}",
                    })
                    continue

                for foto_encon in fotos_encon:
                    try:
                        data_encon = _get_data_url_from_id(foto_encon["id"])
                        resultado = _comparar_imagenes_openai(
                            PROMPT_COMPARAR_DOS,
                            [data_desap, data_encon]
                        )
                        diagnosticos_globales.append({
                            "foto_desap": foto_desap,
                            "foto_encon": foto_encon,
                            "resultado": resultado,
                        })
                    except Exception as exc:
                        current_app.logger.exception(
                            "Error al comparar fotos (todas) desaparecida %s vs encontrada %s",
                            desaparecida_id,
                            encontrada_id
                        )
                        diagnosticos_globales.append({
                            "foto_desap": foto_desap,
                            "foto_encon": foto_encon,
                            "resultado": f"No se pudo comparar este par de fotos: {exc}",
                        })

        else:
            error = "Acción no reconocida para la comparación."

    return render_template(
        "comparar_parejas.html",
        mascota_desaparecida=mascota_desaparecida,
        mascota_encontrada=mascota_encontrada,
        fotos_desap_por_tipo=fotos_desap_por_tipo,
        fotos_encon_por_tipo=fotos_encon_por_tipo,
        tipos_comunes=tipos_comunes,
        tipos_compartidos=tipos_compartidos,
        diagnostico_individual=diagnostico_individual,
        diagnosticos_globales=diagnosticos_globales,
        error=error,
        url_comparar_tipo=url_for(
                "main.comparar_pareja_tipo_api",
                desaparecida_id=desaparecida_id,
                encontrada_id=encontrada_id,
            ),
            url_comparar_todas=url_for(
                "main.comparar_pareja_todas_api",
                desaparecida_id=desaparecida_id,
                encontrada_id=encontrada_id,
            ),
        )

@main.route(
    "/comparaciones/desaparecida/<int:desaparecida_id>/encontrada/<int:encontrada_id>/comparar_tipo",
    methods=["POST"],
)
def comparar_pareja_tipo_api(desaparecida_id: int, encontrada_id: int):
    """
    Endpoint JSON utilizado por la plantilla comparar_parejas.html.
    Recibe el tipo de foto y las referencias de cada imagen, ejecuta la comparación
    y devuelve el texto (y porcentaje estimado si se puede extraer).
    """
    mascota_desaparecida = Mascota.query.get_or_404(desaparecida_id)
    mascota_encontrada = Mascota.query.get_or_404(encontrada_id)

    if not _es_mascota_desaparecida_valida(mascota_desaparecida):
        return jsonify({
            "ok": False,
            "mensaje": "La mascota desaparecida ya no es válida para comparar."
        }), 400

    if (mascota_encontrada.tipo_registro or "").lower() != "encontrada":
        return jsonify({
            "ok": False,
            "mensaje": "La mascota encontrada indicada no es válida."
        }), 400

    payload = request.get_json(silent=True) or {}
    tipo = (payload.get("tipo") or "").strip().lower()
    if not tipo:
        return jsonify({"ok": False, "mensaje": "Debes indicar el tipo de foto a comparar."}), 400

    foto_desap_payload = payload.get("foto_desap") or {}
    foto_encon_payload = payload.get("foto_encon") or {}

    fotos_desap_validas = _obtener_fotos_validas(mascota_desaparecida)
    fotos_encon_validas = _obtener_fotos_validas(mascota_encontrada)
    fotos_desap_por_tipo = _agrupar_fotos_por_tipo(fotos_desap_validas)
    fotos_encon_por_tipo = _agrupar_fotos_por_tipo(fotos_encon_validas)

    if tipo not in fotos_desap_por_tipo or tipo not in fotos_encon_por_tipo:
        return jsonify({
            "ok": False,
            "mensaje": "Ninguna de las mascotas tiene fotos de ese tipo."
        }), 400

    foto_desap_id = foto_desap_payload.get("id")
    foto_encon_id = foto_encon_payload.get("id")

    # Buscar las fotos en BD y validar tipo
    foto_desap_obj = Foto.query.get(foto_desap_id) if foto_desap_id else None
    foto_encon_obj = Foto.query.get(foto_encon_id) if foto_encon_id else None

    if not foto_desap_obj or foto_desap_obj.mascota_id != mascota_desaparecida.id:
        return jsonify({"ok": False, "mensaje": "No se encontró la foto desaparecida en la base de datos."}), 400
    if not foto_encon_obj or foto_encon_obj.mascota_id != mascota_encontrada.id:
        return jsonify({"ok": False, "mensaje": "No se encontró la foto encontrada en la base de datos."}), 400

    if (foto_desap_obj.tipo_foto or "").strip().lower() != tipo:
        return jsonify({"ok": False, "mensaje": "La foto desaparecida no coincide con el tipo elegido."}), 400
    if (foto_encon_obj.tipo_foto or "").strip().lower() != tipo:
        return jsonify({"ok": False, "mensaje": "La foto encontrada no coincide con el tipo elegido."}), 400

    if not foto_desap_obj.data or not foto_encon_obj.data:
        return jsonify({"ok": False, "mensaje": "No hay datos binarios de alguna foto."}), 400

    try:
        data_desap = image_bytes_to_data_url(foto_desap_obj.data, foto_desap_obj.mime_type, foto_desap_obj.nombre_archivo)
        data_encon = image_bytes_to_data_url(foto_encon_obj.data, foto_encon_obj.mime_type, foto_encon_obj.nombre_archivo)
    except Exception as exc:
        current_app.logger.exception("Error al convertir imágenes a data URL")
        return jsonify({"ok": False, "mensaje": f"No se pudieron procesar las imágenes: {exc}"}), 500

    prompt = (
        f"Compara estas dos fotos (tipo: {tipo}). "
        "¿Corresponden al mismo perro? Da un porcentaje aproximado de match (0-100%) "
        "y explica brevemente tu conclusión."
    )

    try:
        resultado_texto = _comparar_imagenes_openai(prompt, [data_desap, data_encon])
    except Exception as exc:
        current_app.logger.exception(
            "Error al invocar la comparación OpenAI para la pareja (%s, %s)",
            desaparecida_id, encontrada_id
        )
        return jsonify({
            "ok": False,
            "mensaje": f"Ocurrió un error al comparar las imágenes: {exc}"
        }), 500

    score = None
    match = re.search(r"(\d{1,3})\s*%", resultado_texto or "", re.UNICODE)
    if match:
        try:
            score_val = int(match.group(1))
            score = max(0, min(100, score_val))
        except ValueError:
            score = None

    return jsonify({
        "ok": True,
        "mensaje": resultado_texto,
        "score": score,
        "tipo": tipo,
        "foto_desap_id": foto_desap_obj.id,
        "foto_encon_id": foto_encon_obj.id,
    })

@main.route(
    "/comparaciones/desaparecida/<int:desaparecida_id>/encontrada/<int:encontrada_id>/comparar_todas",
    methods=["POST"],
)
def comparar_pareja_todas_api(desaparecida_id: int, encontrada_id: int):
    mascota_desaparecida = Mascota.query.get_or_404(desaparecida_id)
    mascota_encontrada = Mascota.query.get_or_404(encontrada_id)

    if not _es_mascota_desaparecida_valida(mascota_desaparecida):
        return jsonify({
            "ok": False,
            "mensaje": "La mascota desaparecida ya no es válida para comparar."
        }), 400

    if (mascota_encontrada.tipo_registro or "").lower() != "encontrada":
        return jsonify({
            "ok": False,
            "mensaje": "La mascota encontrada indicada no es válida."
        }), 400

    fotos_desap_obj = [f for f in mascota_desaparecida.fotos if f.data]
    fotos_encon_obj = [f for f in mascota_encontrada.fotos if f.data]

    if not fotos_desap_obj:
        return jsonify({
            "ok": False,
            "mensaje": "La mascota desaparecida no tiene fotos disponibles."
        }), 400

    if not fotos_encon_obj:
        return jsonify({
            "ok": False,
            "mensaje": "La mascota encontrada no tiene fotos disponibles."
        }), 400

    try:
        data_desap = [
            image_bytes_to_data_url(f.data, f.mime_type, f.nombre_archivo)
            for f in fotos_desap_obj
        ]
        data_encon = [
            image_bytes_to_data_url(f.data, f.mime_type, f.nombre_archivo)
            for f in fotos_encon_obj
        ]
    except Exception as exc:
        current_app.logger.exception("Error al convertir imágenes a data URL en comparar_todas")
        return jsonify({"ok": False, "mensaje": f"No se pudieron procesar las imágenes: {exc}"}), 500

    try:
        resultado = comparar_fotos_todas(data_desap, data_encon)
    except ValueError as exc:
        return jsonify({"ok": False, "mensaje": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception(
            "Error al comparar todas las fotos (desaparecida %s vs encontrada %s)",
            desaparecida_id,
            encontrada_id,
        )
        return jsonify({"ok": False, "mensaje": f"Error al comparar las fotos: {exc}"}), 500

    return jsonify(resultado)

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
                resultado = _comparar_imagenes_openai(PROMPT_IDENTIFICAR_RAZA, [data1])
            elif len(rutas) >= 2:
                data_urls = [image_to_data_url(p) for p in rutas[:2]]
                resultado = _comparar_imagenes_openai(PROMPT_COMPARAR_DOS, data_urls)
        except Exception as exc:
            current_app.logger.exception("Error al procesar imágenes en /comparar_fotos")
            error = f"Error al procesar las imágenes: {exc}"
        finally:
            for ruta in rutas:
                if os.path.isfile(ruta):
                    try:
                        os.remove(ruta)
                        
                    except OSError:
                        current_app.logger.warning("No se pudo eliminar la imagen temporal %s", ruta)

    return render_template("comparar.html", resultado=resultado, error=error)