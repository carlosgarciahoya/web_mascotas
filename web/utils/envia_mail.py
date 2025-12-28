import smtplib
import urllib.request
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, Any, Iterable, Mapping, Optional, Sequence, Tuple, Union

from flask import current_app


def send_pet_email(
    subject: str,
    datos: Union[Mapping[str, object], Sequence[Tuple[str, object]]],
    fotos: Optional[Iterable[Dict[str, Any]]] = None,
    destinatarios_extra: Optional[Iterable[str]] = None,
) -> bool:
    """
    Envía un correo electrónico con los datos y archivos indicados.
    """
    cfg = current_app.config
    smtp_server = cfg.get("SMTP_SERVER")
    smtp_port = cfg.get("SMTP_PORT", 587)
    smtp_user = cfg.get("SMTP_USERNAME")
    smtp_password = cfg.get("SMTP_PASSWORD")
    destino_principal = cfg.get("SMTP_TO_EMAIL")

    # Log básico de configuración (sin mostrar la contraseña)
    current_app.logger.info(
        "[MAIL] Config SMTP: server=%s port=%s user=%s to=%s",
        smtp_server, smtp_port, smtp_user, destino_principal
    )
    print("[MAIL] Config SMTP:", smtp_server, smtp_port, smtp_user, destino_principal)

    if not all([smtp_server, smtp_port, smtp_user, smtp_password, destino_principal]):
        current_app.logger.error(
            "Correo no enviado: faltan variables SMTP (SERVER/PORT/USERNAME/PASSWORD/TO_EMAIL)."
        )
        return False

    # Construir lista de destinatarios
    destinatarios = [
        correo.strip() for correo in str(destino_principal).split(",") if correo.strip()
    ]
    correo_extra = "encontrar.mi.mascota@gmail.com"
    if correo_extra not in destinatarios:
        destinatarios.append(correo_extra)

    if destinatarios_extra:
        for correo in destinatarios_extra:
            correo_norm = str(correo).strip()
            if correo_norm and correo_norm not in destinatarios:
                destinatarios.append(correo_norm)

    current_app.logger.info("[MAIL] Destinatarios finales: %s", destinatarios)
    print("[MAIL] Destinatarios finales:", destinatarios)

    if not destinatarios:
        current_app.logger.error(
            "Correo no enviado: no se pudieron determinar destinatarios válidos."
        )
        return False

    if isinstance(datos, Mapping):
        items = list(datos.items())
    else:
        items = list(datos)

    cuerpo_lineas = [subject, "", "Datos de la mascota:", "--------------------"]
    for clave, valor in items:
        cuerpo_lineas.append(f"{clave}: {formatear_valor(valor)}")
    cuerpo_lineas.append("")
    cuerpo_lineas.append("Este correo se generó automáticamente desde Web Mascotas.")
    cuerpo = "\n".join(cuerpo_lineas)

    mensaje = MIMEMultipart()
    mensaje["From"] = smtp_user
    mensaje["To"] = ", ".join(destinatarios)
    mensaje["Subject"] = subject
    mensaje.attach(MIMEText(cuerpo, "plain", "utf-8"))

    # Adjuntar fotos, mostrando qué se va a hacer
    fotos_lista = list(fotos or [])
    current_app.logger.info("[MAIL] Nº de fotos a adjuntar: %d", len(fotos_lista))
    print("[MAIL] Nº de fotos a adjuntar:", len(fotos_lista))

    for foto in fotos_lista:
        data_bytes = foto.get("data")
        mime_type = foto.get("mime_type") or "application/octet-stream"
        nombre_archivo = foto.get("nombre_archivo") or f"foto_{foto.get('id', 'sin_id')}.jpg"

        if data_bytes:
            current_app.logger.info("[MAIL] Adjuntando foto en memoria: %s", nombre_archivo)
            adjuntar_bytes(mensaje, data_bytes, mime_type, nombre_archivo)
            continue

        url_publica = foto.get("url")
        if url_publica:
            current_app.logger.info("[MAIL] Descargando foto de: %s", url_publica)
            try:
                data_bytes, mime_descargado = descargar_url_local(url_publica)
                adjuntar_bytes(
                    mensaje,
                    data_bytes,
                    mime_descargado or mime_type,
                    nombre_archivo,
                )
                continue
            except Exception as exc:  # pylint: disable=broad-except
                current_app.logger.warning(
                    "No se pudo descargar la foto %s para adjunto: %s",
                    url_publica,
                    exc,
                )

        current_app.logger.warning(
            "Foto sin datos adjuntables (id=%s). No se incluye en el correo.",
            foto.get("id"),
        )

    # Enviar el correo
    try:
        current_app.logger.info(
            "[MAIL] Conectando a SMTP %s:%s con timeout %s",
            smtp_server, smtp_port, 10
        )
        print(f"[MAIL] Conectando a SMTP {smtp_server}:{smtp_port} timeout=10")
        servidor = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
        try:
            servidor.starttls()
            servidor.login(smtp_user, smtp_password)
            servidor.sendmail(smtp_user, destinatarios, mensaje.as_string())
        finally:
            servidor.quit()
        current_app.logger.info(
            "Correo enviado correctamente: %s -> %s", subject, ", ".join(destinatarios)
        )
        print("[MAIL] Correo enviado OK")
        return True
    except Exception as exc:  # pylint: disable=broad-except
        current_app.logger.exception("Error al enviar correo (%s): %s", subject, exc)
        print("[MAIL] Error al enviar correo:", exc)
        return False


def formatear_valor(valor) -> str:
    if valor is None or valor == "":
        return "N/D"
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y %H:%M")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    return str(valor)


def adjuntar_bytes(mensaje, data_bytes: bytes, mime_type: str, nombre_archivo: str):
    if "/" in mime_type:
        tipo, subtipo = mime_type.split("/", 1)
    else:
        tipo, subtipo = "application", "octet-stream"

    parte = MIMEBase(tipo, subtipo)
    parte.set_payload(data_bytes)
    encoders.encode_base64(parte)
    parte.add_header(
        "Content-Disposition",
        f'attachment; filename="{nombre_archivo}"'
    )
    mensaje.attach(parte)


def descargar_url_local(url_relativa: str, timeout: int = 10) -> tuple[bytes, Optional[str]]:
    """
    Descarga una URL servida por la propia aplicación (por ejemplo, /foto/5).
    Usa IG_MEDIA_BASE_URL si está configurada; de lo contrario, http://127.0.0.1:5000.
    """
    base = current_app.config.get("IG_MEDIA_BASE_URL") or "http://127.0.0.1:5000"

    if url_relativa.startswith(("http://", "https://")):
        url_completa = url_relativa
    else:
        url_completa = base.rstrip("/") + (url_relativa if url_relativa.startswith("/") else f"/{url_relativa}")

    current_app.logger.info("[MAIL] Descargando URL completa: %s", url_completa)
    print("[MAIL] Descargando URL completa:", url_completa)

    with urllib.request.urlopen(url_completa, timeout=timeout) as resp:
        data = resp.read()
        mime = resp.info().get_content_type()
        return data, mime