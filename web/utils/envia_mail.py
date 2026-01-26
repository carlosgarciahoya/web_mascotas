import base64
import urllib.request
from datetime import date, datetime
from typing import Dict, Any, Iterable, Mapping, Optional, Sequence, Tuple, Union

import requests
from flask import current_app


def send_pet_email(
    subject: str,
    datos: Union[Mapping[str, object], Sequence[Tuple[str, object]]],
    fotos: Optional[Iterable[Dict[str, Any]]] = None,
    destinatarios_extra: Optional[Iterable[str]] = None,
) -> bool:
    """
    Envía un correo electrónico con los datos y archivos indicados usando la API de Brevo.
    """
    cfg = current_app.config
    # Reutilizamos las variables existentes
    smtp_user = cfg.get("SMTP_USERNAME")      # Remitente (validado en Brevo)
    smtp_password = cfg.get("SMTP_PASSWORD")  # Aquí guardas la API key de Brevo
    destino_principal = cfg.get("SMTP_TO_EMAIL")

    # Log básico de configuración (sin mostrar la contraseña)
    current_app.logger.info(
        "[MAIL] Config Brevo: sender=%s to=%s",
        smtp_user, destino_principal
    )
   # print("[MAIL] Config Brevo:", smtp_user, destino_principal)

    if not all([smtp_user, smtp_password, destino_principal]):
        current_app.logger.error(
            "Correo no enviado: faltan variables (SMTP_USERNAME / SMTP_PASSWORD / SMTP_TO_EMAIL)."
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
   # print("[MAIL] Destinatarios finales:", destinatarios)

    if not destinatarios:
        current_app.logger.error(
            "Correo no enviado: no se pudieron determinar destinatarios válidos."
        )
        return False

    # Construir el cuerpo de texto plano
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

    # Preparar adjuntos en base64 para Brevo
    fotos_lista = list(fotos or [])
    adjuntos = []
    current_app.logger.info("[MAIL] Nº de fotos a adjuntar: %d", len(fotos_lista))
   # print("[MAIL] Nº de fotos a adjuntar:", len(fotos_lista))

    for foto in fotos_lista:
        data_bytes = foto.get("data")
        mime_type = foto.get("mime_type") or "application/octet-stream"
        nombre_archivo = foto.get("nombre_archivo") or f"foto_{foto.get('id', 'sin_id')}.jpg"

        if not data_bytes:
            url_publica = foto.get("url")
            if url_publica:
                current_app.logger.info("[MAIL] Descargando foto de: %s", url_publica)
                try:
                    data_bytes, _ = descargar_url_local(url_publica)
                except Exception as exc:  # pylint: disable=broad-except
                    current_app.logger.warning(
                        "No se pudo descargar la foto %s para adjunto: %s",
                        url_publica,
                        exc,
                    )
                    data_bytes = None
            else:
                current_app.logger.warning(
                    "Foto sin datos adjuntables (id=%s). No se incluye en el correo.",
                    foto.get("id"),
                )

        if data_bytes:
            content_b64 = base64.b64encode(data_bytes).decode("ascii")
            adjuntos.append({
                "name": nombre_archivo,
                "content": content_b64,
            })

    # Construir el payload para la API de Brevo
    payload = {
        "sender": {"email": smtp_user, "name": "buscarmascotas.com"},
        "to": [{"email": d} for d in destinatarios],
        "subject": subject,
        "textContent": cuerpo,
    }
    if adjuntos:
        payload["attachment"] = adjuntos

    headers = {
        "api-key": smtp_password,
        "Content-Type": "application/json",
    }

    # Enviar el correo por HTTPS a Brevo
    try:
        current_app.logger.info("[MAIL] Enviando a Brevo API, destinatarios=%s", destinatarios)
       # print("[MAIL] Enviando a Brevo API...")
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        current_app.logger.info(
            "Correo enviado correctamente vía Brevo: %s -> %s",
            subject, ", ".join(destinatarios)
        )
       # print("[MAIL] Correo enviado OK vía Brevo")
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


def descargar_url_local(url_relativa: str, timeout: int = 30) -> tuple[bytes, Optional[str]]:
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
   # print("[MAIL] Descargando URL completa:", url_completa)

    with urllib.request.urlopen(url_completa, timeout=timeout) as resp:
        data = resp.read()
        mime = resp.info().get_content_type()
        return data, mime