import os
import uuid
import base64
from collections import defaultdict
from datetime import datetime, date
from threading import Thread
from typing import List, Dict

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, jsonify, current_app
)
from sqlalchemy import or_
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

PROMPT_IDENTIFICAR_RAZA = "Identifica la raza del perro en esta imagen:"
PROMPT_COMPARAR_DOS = (
    "¿Son el mismo perro o distintos? Da un porcentaje aproximado de match (0-100%) "
    "y explica brevemente por qué."
)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def _get_static_root() -> str:
    try:
        static_root = current_app.static_folder
    except RuntimeError:
        static_root = None
    elegido = static_root or STATIC_DIR
    print(f"[DEBUG] _get_static_root -> {elegido}")
    return elegido


def _resolver_ruta_absoluta(ruta_rel: str) -> str:
    ruta_abs = os.path.join(_get_static_root(), ruta_rel.replace("/", os.sep))
    print(f"[DEBUG] _resolver_ruta_absoluta: {ruta_rel} -> {ruta_abs}")
    return ruta_abs


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
    print(f"[DEBUG] eliminar_archivo_relativo: {ruta_rel} -> {ruta_abs}")
    try:
        if os.path.isfile(ruta_abs):
            os.remove(ruta_abs)
    except OSError:
        current_app.logger.warning("No se pudo eliminar el archivo de foto %s", ruta_abs)


def eliminar_foto_obj(foto: Foto | None) -> None:
    if not foto:
        return
    eliminar_archivo_relativo(foto.ruta)
    db.session.delete(foto)


def obtener_fotos_existentes(mascota: Mascota) -> List[Dict[str, str]]:
    fotos_serializadas: List[Dict[str, str]] = []
    for foto in getattr(mascota, "fotos", []):
        ruta_rel = normalizar_ruta_foto(foto.ruta)
        if not ruta_rel:
            continue
        fotos_serializadas.append({
            "id": foto.id,
            "tipo_foto": foto.tipo_foto,
            "ruta": f"static/{ruta_rel}",
            "url": url_for("static", filename=ruta_rel)
        })
    return fotos_serializadas


def _construir_mascotas_con_fotos(mascotas):
    resultado = []
    for mascota in mascotas:
        fotos = Foto.query.filter_by(mascota_id=mascota.id).all()
        fotos_info = []
        for foto in fotos:
            ruta_relativa = normalizar_ruta_foto(foto.ruta)
            if ruta_relativa:
                fotos_info.append({
                    "id": foto.id,
                    "tipo_foto": foto.tipo_foto,
                    "ruta": f"static/{ruta_relativa}",
                    "url": url_for("static", filename=ruta_relativa)
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


def _serializar_foto(foto: Foto) -> Dict[str, str] | None:
    ruta_rel = normalizar_ruta_foto(foto.ruta)
    print(f"[DEBUG] _serializar_foto: foto_id={foto.id}, original={foto.ruta}, normalizada={ruta_rel}")
    if not ruta_rel:
        print(f"[DEBUG] _serializar_foto: foto_id={foto.id}, descartada (sin ruta normalizada)")
        return None
    ruta_abs = _resolver_ruta_absoluta(ruta_rel)
    existe = os.path.isfile(ruta_abs)
    print(f"[DEBUG] _serializar_foto: foto_id={foto.id}, ruta_abs={ruta_abs}, existe={existe}")
    if not existe:
        return None
    tipo = (foto.tipo_foto or "desconocido").strip().lower() or "desconocido"
    return {
        "id": foto.id,
        "tipo_foto": tipo,
        "ruta_rel": ruta_rel,
        "ruta_abs": ruta_abs,
        "url": url_for("static", filename=ruta_rel),
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
        model="gpt-5",
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
        subject = f"🐶🐱 mascota {(mascota.tipo_registro or '').strip()}".strip() or "Mascota"

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
    rutas: List[str] = []
    for foto in getattr(mascota, "fotos", []):
        ruta_rel = normalizar_ruta_foto(foto.ruta)
        if not ruta_rel:
            continue
        ruta_abs = _resolver_ruta_absoluta(ruta_rel)
        if os.path.isfile(ruta_abs):
            rutas.append(ruta_abs)
        else:
            current_app.logger.warning(
                "Foto no encontrada en disco: %s (mascota %s)", ruta_abs, mascota.id
            )
    return rutas


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
        color = (request.form.get("color") or "").strip()
        sexo = (request.form.get("sexo") or "").strip().lower()
        chip = (request.form.get("chip") or "").strip()
        peso = (request.form.get("peso") or "").strip()
        tamano = (request.form.get("tamano") or "").strip().lower()
        descripcion = (request.form.get("descripcion") or "").strip()
        fecha_registro_str = (request.form.get("fecha_registro") or "").strip()

        if tipo_registro == "encontrada" and sexo not in SEXOS:
            sexo = "no_sabe"
            print("[DBG CREAR] sexo vacío en encontrada -> forzado a 'no_sabe'")

        print("[DBG CREAR] Campos crudos:",
              "nombre=", repr(nombre),
              "especie=", repr(especie),
              "raza=", repr(raza),
              "zona=", repr(zona),
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
            flash("Ya existe un registro igual (email, tipo, nombre, zona, especie, color, tamaño y fecha).", "error")
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
        tipos_foto = request.form.getlist("tipo_foto")
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

            nombre_seguro = secure_filename(
                f"{mascota.id}_{tipo_actual}_{uuid.uuid4().hex}_{archivo.filename}"
            )
            ruta_fs = os.path.join(UPLOAD_FOLDER, nombre_seguro)
            print(f"[DEBUG] crear_mascota -> guardando foto en {ruta_fs}")
            archivo.save(ruta_fs)
            nuevas_rutas_guardadas.append(ruta_fs)

            ruta_relativa = normalizar_ruta_foto(f"fotos/{nombre_seguro}")

            db.session.add(
                Foto(
                    mascota_id=mascota.id,
                    tipo_foto=tipo_actual,
                    ruta=ruta_relativa
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
        modo="comparar_desaparecidas",
        mascotas=mascotas,
        filtros=filtros,
        busqueda_realizada=busqueda_realizada,
        mensaje=mensaje,
        mascotas_con_fotos=mascotas_con_fotos,
    )


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
                        data_desap = data_url_cache.setdefault(
                            foto_desap["id"],
                            image_to_data_url(foto_desap["ruta_abs"])
                        )
                        data_encon = data_url_cache.setdefault(
                            foto_encon["id"],
                            image_to_data_url(foto_encon["ruta_abs"])
                        )
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
                    data_desap = data_url_cache.setdefault(
                        foto_desap["id"],
                        image_to_data_url(foto_desap["ruta_abs"])
                    )
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
                        data_encon = data_url_cache.setdefault(
                            foto_encon["id"],
                            image_to_data_url(foto_encon["ruta_abs"])
                        )
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
    )


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
            print(f"[DEBUG] comparar_fotos -> guardando imagen temporal en {ruta_fs}")
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
                        print(f"[DEBUG] comparar_fotos -> archivo temporal eliminado: {ruta}")
                    except OSError:
                        current_app.logger.warning("No se pudo eliminar la imagen temporal %s", ruta)

    return render_template("comparar.html", resultado=resultado, error=error)