import os
import json
import threading
import time
import base64
from datetime import datetime
from tkinter import *
from tkinter import filedialog, messagebox
from openai import OpenAI
from tkinter import simpledialog

# print (os.getenv("OPENAI_API_KEY_PERSONAL"))

# ------------- Configuración básica y seguridad -------------
API_KEYS = {
    "personal": os.getenv("OPENAI_API_KEY_PERSONAL", ""),
    "oposicion": os.getenv("OPENAI_API_KEY_OPOSICION", "")
}

# ------------- Variables globales de estado -------------
history = []  # [{'role':'user'/'assistant','content':[{'type':'text','text':...}, ...]}]
current_api = "personal"
current_model = "gpt-5.1-codex"

# Modelos que requieren endpoint v1/responses (no chat/completions)
RESP_MODELS = {"gpt-5-codex", "gpt-5.1-codex", "gpt-5-complex"}

waiting_timer_id = None
waiting_start_ms = 0
auto_follow_end = True  # seguir el final salvo que el usuario se mueva

# Parámetros acordados
WINDOW_RECENT_MESSAGES = 30
MAX_PROMPT_CHARS = 120_000
SUMMARIZE_EVERY_N_MSGS = 20
RENDER_LAST = 20
IMPORT_KEEP_RECENT = 20
IMPORT_SUMMARY_CHUNK = 120
MAX_LINES_PER_MSG = 40  # visual (si quisieras recortar, aquí podrías truncar texto al insertar)
SCROLL_LINES_PER_WHEEL = 8

memory_state = {
    "summary": "",
    "last_index": 0
}

def ask_large_string(title, prompt, initialvalue=""):
    return simpledialog.askstring(title, prompt, initialvalue=initialvalue, parent=root)

def build_client():
    key = API_KEYS[current_api]
    if not key:
        raise RuntimeError(f"Falta la variable de entorno OPENAI_API_KEY_{current_api.upper()}")
    return OpenAI(api_key=key)

client = build_client()

# ------------- Utilidades varias -------------
TEXT_EXTS = {
    ".txt", ".md", ".rst", ".log",
    ".csv", ".tsv",
    ".json", ".jsonl", ".xml", ".yaml", ".yml", ".ini", ".toml", ".cfg", ".env",
    ".html", ".htm",
    ".ipynb",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h", ".cs", ".go",
    ".rs", ".rb", ".php", ".swift", ".kt", ".kts", ".scala", ".sh", ".ps1", ".sql",
    ".r", ".m", ".jl", ".dart", ".lua", ".makefile", ".dockerfile"
}
RASTER_IMG_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")

MAX_TEXT_CHARS = 200_000

def read_file_as_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = f.read()
        if len(data) > MAX_TEXT_CHARS:
            head = data[:MAX_TEXT_CHARS]
            tail = f"\n\n[... contenido truncado, mostrado {MAX_TEXT_CHARS} de {len(data)} caracteres ...]"
            return head + tail
        return data
    except Exception:
        return None

# ------------- Memoria resumida y ventana reciente -------------
def _history_to_plain_text(hslice):
    parts = []
    for msg in hslice:
        if msg.get("role") not in ("user", "assistant"):
            continue
        for c in msg.get("content", []):
            if c.get("type") == "text":
                t = (c.get("text") or "").strip()
                if t:
                    parts.append(f"{msg['role']}: {t}")
    return "\n".join(parts)

def _estimate_chars(messages):
    return sum(len(m.get("content", "")) + 20 for m in messages)

def maybe_compact_history():
    try:
        # Dejar fuera del resumen las últimas WINDOW_RECENT_MESSAGES intervenciones
        k_left = WINDOW_RECENT_MESSAGES
        idx = len(history) - 1
        while idx >= 0 and k_left > 0:
            if history[idx].get("role") in ("user", "assistant"):
                k_left -= 1
            idx -= 1
        keep_from = max(0, idx + 1)

        start = memory_state.get("last_index", 0)
        end = max(start, keep_from)
        if end - start < SUMMARIZE_EVERY_N_MSGS:
            return

        chunk_text = _history_to_plain_text(history[start:end]).strip()
        current_summary = (memory_state.get("summary") or "").strip()
        if not chunk_text:
            memory_state["last_index"] = end
            return

        prompt_sys = ("Eres una memoria de conversación. Mantén un resumen breve, factual y útil "
                      "para continuar la charla: objetivos, decisiones, datos del usuario, "
                      "preferencias, tareas pendientes y referencias a archivos. Condensa y actualiza el resumen existente.")
        prompt_user = (f"Resumen actual:\n{current_summary or '(vacío)'}\n\n"
                       f"Nuevas intervenciones para incorporar:\n{chunk_text}\n\n"
                       "Devuelve solo el resumen actualizado.")

        updated = ask_text(current_model, [
            {"role": "system", "content": prompt_sys},
            {"role": "user", "content": prompt_user},
        ]) or ""

        memory_state["summary"] = (updated or current_summary).strip()
        memory_state["last_index"] = end
    except Exception:
        pass

def summarize_messages_to_state(msgs):
    try:
        summary = (memory_state.get("summary") or "").strip()
        CH = max(1, IMPORT_SUMMARY_CHUNK)
        for i in range(0, len(msgs), CH):
            chunk = msgs[i:i+CH]
            chunk_text = _history_to_plain_text(chunk).strip()
            if not chunk_text:
                continue
            prompt_sys = ("Eres una memoria de conversación. Mantén un resumen breve, factual y útil "
                          "para continuar la charla: objetivos, decisiones, datos del usuario, "
                          "preferencias, tareas pendientes y referencias a archivos. Condensa y actualiza el resumen existente.")
            prompt_user = (f"Resumen actual:\n{summary or '(vacío)'}\n\n"
                           f"Nuevas intervenciones para incorporar:\n{chunk_text}\n\n"
                           "Devuelve solo el resumen actualizado.")
            updated = ask_text(current_model, [
                {"role": "system", "content": prompt_sys},
                {"role": "user", "content": prompt_user},
            ]) or ""
            summary = (updated or summary).strip()
        memory_state["summary"] = summary
        memory_state["last_index"] = 0
        return summary
    except Exception:
        return None

# ------------- Chat básico (con Text único) -------------
def build_chat_messages_for_api():
    raw = []
    for msg in history:
        if msg.get("role") not in ("user", "assistant"):
            continue
        text_parts = [c.get("text", "") for c in msg.get("content", []) if c.get("type") == "text"]
        if not text_parts:
            continue
        content = "\n".join([p for p in text_parts if p]).strip()
        if not content:
            continue
        raw.append({"role": msg["role"], "content": content})

    # Ventana reciente
    recent = []
    k = WINDOW_RECENT_MESSAGES
    for m in reversed(raw):
        recent.append(m)
        k -= 1
        if k <= 0:
            break
    recent.reverse()

    msgs = []
    if memory_state.get("summary"):
        msgs.append({"role": "system", "content": f"Resumen de contexto para continuar:\n{memory_state['summary']}"})
    msgs.extend(recent)

    while _estimate_chars(msgs) > MAX_PROMPT_CHARS and len(recent) > 2:
        recent = recent[2:]
        msgs = ([{"role": "system", "content": f"Resumen de contexto para continuar:\n{memory_state.get('summary','')}"}]
                if memory_state.get("summary") else []) + recent
    return msgs

def ask_text(model, messages):
    if model in RESP_MODELS:
        prompt = "\n\n".join(f"{m['role']}: {m['content']}" for m in messages)
        resp = client.responses.create(model=model, input=prompt)
        return _extract_response_text(resp)
    else:
        resp = client.chat.completions.create(model=model, messages=messages)
        return resp.choices[0].message.content

def send_message():
    user_input = input_text.get("1.0", END).strip()
    if not user_input:
        return
    input_text.delete("1.0", END)
    add_message("user", user_input)
    history.append({"role": "user", "content": [{"type": "text", "text": user_input}]})
    start_waiting()
    send_button.config(state="disabled")
    threading.Thread(target=generate_response, daemon=True).start()

def generate_response():
    ok = True
    answer = ""
    try:
        maybe_compact_history()
        messages = build_chat_messages_for_api()
        answer = ask_text(current_model, messages)
    except Exception as e:
        ok = False
        answer = f" Error: {e}"
    history.append({"role": "assistant", "content": [{"type": "text", "text": answer}]})
    root.after(0, lambda ans=answer, ok=ok: _on_request_done(ans, ok))

# ------------- Text único: helpers de UI -------------
def is_at_bottom():
    try:
        _, hi = chat_display.yview()
        return hi >= 0.98
    except Exception:
        return True

def scroll_to_bottom():
    try:
        chat_display.see("end")
    except Exception:
        pass

def update_auto_follow_from_yview(first, last):
    try:
        scrollbar.set(first, last)
        global auto_follow_end
        auto_follow_end = float(last) >= 0.98
    except Exception:
        pass

def wheel_scroll(event):
    try:
        # Shift = por página
        if getattr(event, "state", 0) & 0x0001:
            if hasattr(event, "delta"):
                chat_display.yview_scroll(-1 if event.delta > 0 else 1, "page")
            else:
                if getattr(event, "num", 0) == 4:
                    chat_display.yview_scroll(-1, "page")
                else:
                    chat_display.yview_scroll(1, "page")
        else:
            if hasattr(event, "delta"):
                direction = -1 if event.delta > 0 else 1
                chat_display.yview_scroll(direction * SCROLL_LINES_PER_WHEEL, "units")
            else:
                if getattr(event, "num", 0) == 4:
                    chat_display.yview_scroll(-SCROLL_LINES_PER_WHEEL, "units")
                else:
                    chat_display.yview_scroll(SCROLL_LINES_PER_WHEEL, "units")
        # Actualiza flag de seguimiento
        update_auto_follow_from_yview(*chat_display.yview())
        return "break"
    except Exception:
        pass

def go_end(event=None):
    chat_display.yview_moveto(1.0)
    global auto_follow_end
    auto_follow_end = True

def go_home(event=None):
    chat_display.yview_moveto(0.0)
    update_auto_follow_from_yview(*chat_display.yview())

# ------------- Mostrar mensajes en Text -------------
def add_message(role, content_text):
    # Recorte visual opcional por líneas
    # Si quisieras truncar visualmente cada mensaje: tomar primeras MAX_LINES_PER_MSG líneas.
    # Aquí mostramos completo, confiando en mostrar solo últimos 20 en refresh_chat().
    prefix = "Tú: " if role == "user" else "Asistente: "
    tag = "user" if role == "user" else "assistant"

    chat_display.configure(state="normal")
    chat_display.insert("end", prefix, ("prefix", tag))
    chat_display.insert("end", content_text + "\n\n", (tag,))
    chat_display.configure(state="disabled")

    if auto_follow_end:
        scroll_to_bottom()

# ------------- Estado de espera en Text -------------
def start_waiting():
    global waiting_timer_id, waiting_start_ms
    stop_waiting()
    waiting_start_ms = int(time.time() * 1000)

    chat_display.configure(state="normal")
    chat_display.insert("end", " Enviado. Esperando respuesta… 00:00\n", ("wait",))
    chat_display.configure(state="disabled")
    if auto_follow_end:
        scroll_to_bottom()

    def tick():
        global waiting_timer_id
        if "wait" in chat_display.tag_names():
            if chat_display.tag_ranges("wait"):
                elapsed = int(time.time() * 1000) - waiting_start_ms
                s = elapsed // 1000
                mm = str(s // 60).zfill(2)
                ss = str(s % 60).zfill(2)
                chat_display.configure(state="normal")
                start, end = chat_display.tag_ranges("wait")
                chat_display.delete(start, end)
                chat_display.insert(start, f" Enviado. Esperando respuesta… {mm}:{ss}\n", ("wait",))
                chat_display.configure(state="disabled")
                if auto_follow_end:
                    scroll_to_bottom()
                waiting_timer_id = root.after(500, tick)

    waiting_timer_id = root.after(500, tick)

def stop_waiting(final_text=None):
    global waiting_timer_id
    if waiting_timer_id:
        try:
            root.after_cancel(waiting_timer_id)
        except Exception:
            pass
        waiting_timer_id = None

    if chat_display.tag_ranges("wait"):
        chat_display.configure(state="normal")
        start, end = chat_display.tag_ranges("wait")
        if final_text:
            chat_display.delete(start, end)
            chat_display.insert(start, final_text + "\n", ())
        chat_display.tag_remove("wait", "1.0", "end")
        chat_display.configure(state="disabled")
        if auto_follow_end:
            scroll_to_bottom()

def finish_waiting(ok=True):
    ms = int(time.time() * 1000) - waiting_start_ms
    s = ms // 1000
    stop_waiting(f" Respuesta recibida en {s}s" if ok else f" Error. Tiempo transcurrido: {s}s")

def _on_request_done(answer, ok):
    finish_waiting(ok)
    add_message("assistant", answer)
    send_button.config(state="normal")

# ------------- Helper para Responses -------------
def _extract_response_text(resp):
    try:
        return resp.output_text
    except Exception:
        try:
            parts = []
            for item in getattr(resp, "output", []) or []:
                for c in getattr(item, "content", []) or []:
                    t = getattr(c, "type", "")
                    if t in ("output_text", "text"):
                        txt_obj = getattr(c, "text", None)
                        if txt_obj is not None:
                            val = getattr(txt_obj, "value", None)
                            if val:
                                parts.append(val)
                        elif hasattr(c, "text"):
                            parts.append(c.text)
            return "\n".join([p for p in parts if p]) or "(sin texto)"
        except Exception:
            return "(sin texto)"

# ------------- Análisis de archivo -------------
def ask_about_file_assistants(file_path, question, model=None):
    mdl = model or current_model
    filename = os.path.basename(file_path)
    ext = os.path.splitext(filename)[1].lower()

    if ext in RASTER_IMG_EXTS:
        data_url = image_to_data_url(file_path)
        if mdl in RESP_MODELS:
            resp = client.responses.create(
                model=mdl,
                input=[{"role": "user",
                        "content": [
                            {"type": "input_text", "text": question},
                            {"type": "input_image", "image_url": data_url}
                        ]}]
            )
            return None, _extract_response_text(resp)
        else:
            resp = client.chat.completions.create(
                model=mdl,
                messages=[{"role": "user",
                           "content": [
                               {"type": "text", "text": question},
                               {"type": "image_url", "image_url": {"url": data_url}}
                           ]}]
            )
            return None, resp.choices[0].message.content

    if mdl in RESP_MODELS and ext == ".pdf":
        with open(file_path, "rb") as f:
            up = client.files.create(file=f, purpose="assistants")
        file_id = up.id
        resp = client.responses.create(
            model=mdl,
            input=[{"role": "user",
                    "content": [
                        {"type": "input_text", "text": question},
                        {"type": "input_file", "file_id": file_id}
                    ]}]
        )
        return file_id, _extract_response_text(resp)

    text = read_file_as_text(file_path) if ext in TEXT_EXTS else None
    if not text:
        return None, f"No puedo incluir {filename} como contexto directo. Convierte el archivo a texto o PDF e inténtalo de nuevo."

    prompt_text = f"Archivo: {filename}\n\n{('```' + ext.lstrip('.') + '\\n' + text + '\\n```') if ext in TEXT_EXTS else text}"

    if mdl in RESP_MODELS:
        resp = client.responses.create(
            model=mdl,
            input=[{"role": "user",
                    "content": [
                        {"type": "input_text", "text": question},
                        {"type": "input_text", "text": prompt_text}
                    ]}]
        )
        return None, _extract_response_text(resp)
    else:
        resp = client.chat.completions.create(
            model=mdl,
            messages=[
                {"role": "user", "content": question},
                {"role": "user", "content": f"Contexto del archivo {filename}:\n\n{prompt_text}"}
            ]
        )
        return None, resp.choices[0].message.content

def action_analyze_file_assistants():
    file_path = filedialog.askopenfilename(
        filetypes=[
            ("Documentos y código", "*.pdf;*.docx;*.pptx;*.xlsx;*.txt;*.md;*.rst;*.html;*.htm;*.json;*.jsonl;*.yaml;*.yml;*.xml;*.csv;*.tsv;*.ini;*.toml;*.cfg;*.env;*.ipynb;*.py;*.js;*.ts;*.jsx;*.tsx;*.java;*.c;*.cpp;*.h;*.cs;*.go;*.rs;*.rb;*.php;*.swift;*.kt;*.kts;*.scala;*.sh;*.ps1;*.sql;*.r;*.m;*.jl;*.dart;*.lua"),
            ("Imágenes (raster)", "*.png;*.jpg;*.jpeg;*.gif;*.webp;*.bmp"),
            ("Todos los archivos", "*.*"),
        ]
    )
    if not file_path:
        return
    q = ask_large_string("Pregunta", "¿Qué quieres preguntar sobre el archivo?",
                         initialvalue="Resume el archivo, por favor.")
    if not q:
        return
    filename = os.path.basename(file_path)
    add_message("user", f"Analizando archivo: {filename}\nPregunta: {q}")
    history.append({"role": "user", "content": [{"type": "text", "text": f"Analizando archivo: {filename}\nPregunta: {q}"}]})
    start_waiting(); send_button.config(state="disabled")

    def worker():
        ok = True
        ans = ""
        try:
            file_id, ans = ask_about_file_assistants(file_path, q, model=current_model)
            if file_id:
                ans = f"(file_id: {file_id})\n\n{ans}"
        except Exception as e:
            ok = False
            ans = f" Error analizando archivo: {e}"
        history.append({"role": "assistant", "content": [{"type": "text", "text": ans}]})
        root.after(0, lambda: _on_request_done(ans, ok))
    threading.Thread(target=worker, daemon=True).start()

# ------------- Análisis de imagen con base64 -------------
def image_to_data_url(path):
    name = os.path.basename(path).lower()
    if name.endswith(".png"):
        mime = "image/png"
    elif name.endswith(".jpg") or name.endswith(".jpeg"):
        mime = "image/jpeg"
    elif name.endswith(".gif"):
        mime = "image/gif"
    elif name.endswith(".webp"):
        mime = "image/webp"
    elif name.endswith(".bmp"):
        mime = "image/bmp"
    else:
        mime = "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def analyze_image_base64(file_path, question, model=None):
    mdl = model or current_model
    data_url = image_to_data_url(file_path)
    if mdl in RESP_MODELS:
        resp = client.responses.create(
            model=mdl,
            input=[{"role": "user",
                    "content": [
                        {"type": "input_text", "text": question},
                        {"type": "input_image", "image_url": data_url}
                    ]}]
        )
        return _extract_response_text(resp)
    else:
        response = client.chat.completions.create(
            model=mdl,
            messages=[{"role": "user",
                       "content": [
                           {"type": "text", "text": question},
                           {"type": "image_url", "image_url": {"url": data_url}}
                       ]}]
        )
        return response.choices[0].message.content

def action_analyze_image_base64():
    file_path = filedialog.askopenfilename(filetypes=[("Imágenes", "*.png;*.jpg;*.jpeg;*.gif;*.webp;*.bmp")])
    if not file_path:
        return
    q = ask_large_string("Pregunta", "¿Qué quieres preguntar sobre la imagen?",
                         initialvalue="Describe el contenido de la imagen.")
    if not q:
        return
    filename = os.path.basename(file_path)
    add_message("user", f"Analizando imagen por base64: {filename}\nPregunta: {q}")
    history.append({"role": "user", "content": [{"type": "text", "text": f"Analizando imagen por base64: {filename}\nPregunta: {q}"}]})
    start_waiting(); send_button.config(state="disabled")

    def worker():
        ok = True
        ans = ""
        try:
            ans = analyze_image_base64(file_path, q, model=current_model)
        except Exception as e:
            ok = False
            ans = f" Error analizando imagen: {e}"
        history.append({"role": "assistant", "content": [{"type": "text", "text": ans}]})
        root.after(0, lambda: _on_request_done(ans, ok))
    threading.Thread(target=worker, daemon=True).start()

# ------------- Varias (exportar, importar, etc.) -------------
def change_model(selected):
    global current_model
    current_model = selected

def change_api(selected):
    global current_api, client
    current_api = selected
    client = build_client()

def export_chat():
    if not history:
        messagebox.showinfo("Exportar", "No hay mensajes para exportar")
        return
    filename = f"{current_api}_export_{datetime.now().strftime('%d-%m-%Y-T%H-%M-%S')}.json"
    base_dir = os.path.abspath(os.path.dirname(__file__))
    base_dir = os.path.join(base_dir,  "chat_backups_personal")
    path = os.path.join(base_dir, filename)
    payload = {
        "history": history[-IMPORT_KEEP_RECENT:],
        "memory_state": {
            "summary": memory_state.get("summary", ""),
            "last_index": 0
        }
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    messagebox.showinfo("Exportar", f"Chat exportado en:\n{path}\n(Resumen + últimos {IMPORT_KEEP_RECENT} mensajes)")

def import_chat():
    file_path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
    if not file_path:
        return
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        global history
        loaded_summary = ""

        if isinstance(data, dict) and isinstance(data.get("history"), list):
            history = data["history"]
            ms = data.get("memory_state") or {}
            loaded_summary = (ms.get("summary") or "").strip()
        elif isinstance(data, list):
            history = data
            loaded_summary = ""
        else:
            messagebox.showerror("Error", "Formato incorrecto")
            return

        if len(history) > IMPORT_KEEP_RECENT:
            older = history[:-IMPORT_KEEP_RECENT]
            if loaded_summary:
                memory_state["summary"] = loaded_summary
            else:
                summarize_messages_to_state(older)
            history = history[-IMPORT_KEEP_RECENT:]
            notice = f"(Se han resumido {len(older)} mensajes anteriores en la memoria de contexto)"
            history.insert(0, {"role": "assistant", "content": [{"type": "text", "text": notice}]})
        else:
            memory_state["summary"] = loaded_summary

        memory_state["last_index"] = 0
        refresh_chat()
        messagebox.showinfo("Importar", f"Chat importado. Mostrando últimos {min(len(history), RENDER_LAST)} mensajes.")
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo importar: {e}")

def clear_chat():
    if messagebox.askyesno("Borrar", "¿Deseas borrar todo el chat actual?"):
        global history
        history = []
        memory_state["summary"] = ""
        memory_state["last_index"] = 0
        refresh_chat()

def refresh_chat():
    chat_display.configure(state="normal")
    chat_display.delete("1.0", "end")
    # Mostrar sólo los últimos RENDER_LAST
    items = []
    for m in reversed(history):
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        texts = [c.get("text", "") for c in m.get("content", []) if c.get("type") == "text"]
        if not texts:
            continue
        items.append((role, "\n".join([t for t in texts if t])))
        if len(items) >= RENDER_LAST:
            break
    items.reverse()
    for role, text in items:
        prefix = "Tú: " if role == "user" else "Asistente: "
        tag = "user" if role == "user" else "assistant"
        chat_display.insert("end", prefix, ("prefix", tag))
        chat_display.insert("end", text + "\n\n", (tag,))
    chat_display.configure(state="disabled")
    # Posicionarse al final
    global auto_follow_end
    auto_follow_end = True
    scroll_to_bottom()

def save_auto_chat(prefix="chat_auto"):
    if not history:
        return
    base_dir = os.path.abspath(os.path.dirname(__file__))
    base_dir = os.path.join(base_dir,  "chat_backups_personal")
    filename = f"{current_api}_{prefix}_{datetime.now().strftime('%d-%m-%Y-T%H-%M-%S')}.json"
    path = os.path.join(base_dir, filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(" Error guardando chat automático:", e)

def copy_all_chat():
    text = ""
    for msg in history:
        for c in msg.get("content", []):
            if c.get("type") == "text":
                prefix = " Tú: " if msg["role"] == "user" else " Asistente: "
                text += f"{prefix}{c['text']}\n\n"
    root.clipboard_clear()
    root.clipboard_append(text)
    messagebox.showinfo("Copiar todo", "Chat copiado al portapapeles.")

# ------------- GUI -------------
root = Tk()
root.title("Chat con archivos (Text único, sin cortes)")

# Arrancar grande/maximizado
sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
root.geometry(f"{int(sw * 0.96)}x{int(sh * 0.96)}+{int(sw * 0.02)}+{int(sh * 0.02)}")
try:
    root.state("zoomed")
except Exception:
    try:
        root.attributes("-zoomed", True)
    except Exception:
        pass
root.configure(bg="#ffffff")

top_frame = Frame(root, bg="#ffffff")
top_frame.pack(fill=X, padx=15, pady=6)
top_label_font = ("Arial", 12)
top_button_font = ("Arial", 12, "bold")

Label(top_frame, text="Modelo:", bg="#ffffff", font=top_label_font).pack(side=LEFT)
model_var = StringVar(value=current_model)
model_menu = OptionMenu(
    top_frame, model_var,
    "gpt-5", "gpt-5.1-codex", "gpt-5-codex", "gpt-5-complex", "gpt-5-chat-latest", "gpt-5-mini", "gpt-image-1",
    command=change_model
)
model_menu.config(font=top_label_font, width=14)
model_menu["menu"].config(font=top_label_font)
model_menu.pack(side=LEFT, padx=8)

Label(top_frame, text="Clave API:", bg="#ffffff", font=top_label_font).pack(side=LEFT, padx=(16, 0))
api_var = StringVar(value=current_api)
api_menu = OptionMenu(top_frame, api_var, "personal", "oposicion", command=change_api)
api_menu.config(font=top_label_font, width=12)
api_menu["menu"].config(font=top_label_font)
api_menu.pack(side=LEFT, padx=8)

Button(top_frame, text="Analizar archivo", font=top_button_font,
       command=action_analyze_file_assistants, width=20, height=1).pack(side=RIGHT, padx=4)
Button(top_frame, text="Analizar imagen", font=top_button_font,
       command=action_analyze_image_base64, width=18, height=1).pack(side=RIGHT, padx=4)
Button(top_frame, text="Copiar todo", font=top_button_font,
       command=copy_all_chat, width=10, height=1).pack(side=RIGHT, padx=4)
Button(top_frame, text="Exportar", font=top_button_font,
       command=export_chat, width=9, height=1).pack(side=RIGHT, padx=4)
Button(top_frame, text="Importar", font=top_button_font,
       command=import_chat, width=9, height=1).pack(side=RIGHT, padx=4)
Button(top_frame, text="Borrar", font=top_button_font,
       command=clear_chat, width=8, height=1).pack(side=RIGHT, padx=4)

# Área de entrada
input_frame = Frame(root, bg="#ffffff", bd=2, relief="groove")
input_frame.pack(side=BOTTOM, fill=X, padx=15, pady=5)
input_scroll = Scrollbar(input_frame); input_scroll.pack(side=RIGHT, fill=Y)
input_text = Text(input_frame, height=6, font=("Arial", 16), bg="#f7f7f8", wrap="word", yscrollcommand=input_scroll.set)
input_text.pack(side=LEFT, fill=X, expand=True, padx=(0, 15))
input_scroll.config(command=input_text.yview)

send_button_font = ("Arial", 16, "bold")
send_button = Button(input_frame, text="Enviar", font=send_button_font,
                     width=14, height=2, bg="#10a37f", fg="white", command=send_message)
send_button.pack(side=RIGHT)

# Chat display (Text único + Scrollbar)
chat_frame = Frame(root, bg="#ffffff")
chat_frame.pack(fill=BOTH, expand=True, padx=15, pady=(0, 5))

scrollbar = Scrollbar(chat_frame, orient=VERTICAL)
scrollbar.pack(side=RIGHT, fill=Y)

chat_display = Text(chat_frame, wrap="word", font=("Arial", 16),
                    bg="#ffffff", fg="black", state="disabled")
chat_display.pack(side=LEFT, fill=BOTH, expand=True)

# Tags de estilo
chat_display.tag_configure("prefix", foreground="#555", font=("Arial", 14, "italic"))
chat_display.tag_configure("user", background="#DCF8C6", lmargin1=14, lmargin2=14, rmargin=14, spacing1=6, spacing3=6)
chat_display.tag_configure("assistant", background="#F1F0F0", lmargin1=14, lmargin2=14, rmargin=14, spacing1=6, spacing3=6)
chat_display.tag_configure("wait", foreground="#0b65c2", background="#E8F4FD", lmargin1=14, lmargin2=14, rmargin=14)

# Scrollbar y seguimiento
def on_scrollbar(*args):
    chat_display.yview(*args)
    update_auto_follow_from_yview(*chat_display.yview())
scrollbar.config(command=on_scrollbar)
chat_display.config(yscrollcommand=lambda f, l: update_auto_follow_from_yview(f, l))

# Eventos de scroll
chat_display.bind("<MouseWheel>", wheel_scroll)
chat_display.bind("<Button-4>", wheel_scroll)
chat_display.bind("<Button-5>", wheel_scroll)

# Teclas rápidas
root.bind_all("<End>", go_end)
root.bind_all("<Home>", go_home)
root.bind_all("<Next>", lambda e: (chat_display.yview_scroll(1, "page"), update_auto_follow_from_yview(*chat_display.yview())))
root.bind_all("<Prior>", lambda e: (chat_display.yview_scroll(-1, "page"), update_auto_follow_from_yview(*chat_display.yview())))

# ------------- Cierre -------------
def on_closing():
    try:
        if waiting_timer_id:
            root.after_cancel(waiting_timer_id)
    except Exception:
        pass
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)

# Posicionarse al final por defecto al iniciar
root.after(200, scroll_to_bottom)

# ------------- Main loop -------------
root.mainloop()