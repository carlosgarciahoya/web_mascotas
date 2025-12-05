import os
import json
import threading
import time
from datetime import datetime
from tkinter import *
from tkinter import filedialog, messagebox
from openai import OpenAI

# --- Carpetas de backups ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
BACKUP_DIRS = {
    "personal": os.path.join(BASE_DIR, "chat_backups_personal"),
    "oposicion": os.path.join(BASE_DIR, "chat_backups_oposicion")
}
for d in BACKUP_DIRS.values():
    os.makedirs(d, exist_ok=True)

API_KEYS = {
    "personal": "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",
    "oposicion": "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"
}

# --- Variables globales ---
history = []
current_api = "personal"
current_model = "gpt-5.1-codex"

chat_width = 1000  # ancho dinámico del chat

# Estado de espera (contador)
waiting_timer_id = None
waiting_start_ms = 0
waiting_label = None
waiting_frame = None

# Botón de copia de la última respuesta del asistente
last_assistant_button = None

# Último widget de texto de mensaje (para auto-scroll a su “última línea”)
last_message_text_widget = None

# --- Inicializar cliente OpenAI ---
client = OpenAI(api_key=API_KEYS[current_api])

# --- Utilidades de scroll ---
def is_at_bottom():
    try:
        lo, hi = canvas.yview()
        return hi >= 0.98
    except Exception:
        return True

def scroll_to_widget_end(widget):
    try:
        canvas.update_idletasks()
        chat_frame.update_idletasks()
        widget.update_idletasks()

        widget_bottom = widget.winfo_y() + widget.winfo_height()
        chat_h = max(1, chat_frame.winfo_height())
        canvas_h = max(1, canvas.winfo_height())

        if chat_h <= canvas_h:
            canvas.yview_moveto(1.0)
            return

        top_target = max(0, widget_bottom - canvas_h)
        max_top = max(1, chat_h - canvas_h)
        frac = 0.0 if max_top <= 0 else min(1.0, top_target / max_top)
        canvas.yview_moveto(frac)
    except Exception:
        pass

# --- UI: aviso de espera y autosize de textos ---
def start_waiting():
    global waiting_timer_id, waiting_start_ms, waiting_label, waiting_frame
    stop_waiting()

    waiting_start_ms = int(time.time() * 1000)

    wf = Frame(chat_frame, bg="#ffffff")
    wf.pack(fill="x", pady=(0, 5))
    lbl = Label(
        wf,
        text="✅ Enviado. Esperando respuesta… 00:00",
        bg="#E8F4FD",
        fg="#0b65c2",
        font=("Arial", 14),
        padx=14,
        pady=8,
        anchor="w",
        justify="left",
    )
    lbl.pack(anchor="w", padx=20)

    if is_at_bottom():
        canvas.update_idletasks()
        canvas.yview_moveto(1.0)

    def tick():
        global waiting_timer_id
        if lbl.winfo_exists():
            elapsed = int(time.time() * 1000) - waiting_start_ms
            s = elapsed // 1000
            mm = str(s // 60).zfill(2)
            ss = str(s % 60).zfill(2)
            lbl.config(text=f"✅ Enviado. Esperando respuesta… {mm}:{ss}")
            waiting_timer_id = root.after(500, tick)

    waiting_frame = wf
    waiting_label = lbl
    tick()

def stop_waiting(final_text=None):
    global waiting_timer_id, waiting_label, waiting_frame
    if waiting_timer_id:
        try:
            root.after_cancel(waiting_timer_id)
        except Exception:
            pass
        waiting_timer_id = None
    if waiting_label and final_text:
        waiting_label.config(text=final_text)
    if waiting_frame:
        wf = waiting_frame
        waiting_label = None
        waiting_frame = None
        root.after(1500, lambda: wf.destroy())

def finish_waiting(ok=True):
    ms = int(time.time() * 1000) - waiting_start_ms
    s = ms // 1000
    if ok:
        stop_waiting(f"✅ Respuesta recibida en {s}s")
    else:
        stop_waiting(f"⚠️ Error. Tiempo transcurrido: {s}s")

def autosize_text_widget(w: Text):
    try:
        was_disabled = (str(w.cget("state")) == "disabled")
        if was_disabled:
            w.configure(state="normal")
        w.update_idletasks()
        count = w.count("1.0", "end-1c", "displaylines")
        lines = int(count[0]) if count else 1
        w.configure(height=max(1, lines))
        if was_disabled:
            w.configure(state="disabled")
    except Exception:
        pass

def reflow_text_heights():
    for bubble in chat_frame.winfo_children():
        for child in bubble.winfo_children():
            if isinstance(child, Text):
                autosize_text_widget(child)

def copy_to_clipboard(text, btn=None):
    try:
        root.clipboard_clear()
        root.clipboard_append(text)
        if btn:
            btn.config(text="Copiado ✓")
            root.after(1200, lambda: btn.config(text="Copiar"))
    except Exception as e:
        messagebox.showerror("Copiar", f"No se pudo copiar: {e}")

def _on_request_done(answer, ok):
    finish_waiting(ok)
    add_message("assistant", answer)
    send_button.config(state="normal")

# --- Lógica principal ---
def send_message():
    user_input = input_text.get("1.0", END).strip()
    if not user_input:
        return

    input_text.delete("1.0", END)
    add_message("user", user_input)
    history.append({"role": "user", "content": user_input})

    start_waiting()
    send_button.config(state="disabled")

    threading.Thread(target=generate_response, args=(user_input,), daemon=True).start()

def generate_response(user_input):
    ok = True
    try:
        response = client.chat.completions.create(
            model=current_model,
            messages=history
        )
        answer = response.choices[0].message.content
    except Exception as e:
        ok = False
        answer = f"⚠️ Error: {e}"

    history.append({"role": "assistant", "content": answer})
    root.after(0, lambda ans=answer, ok=ok: _on_request_done(ans, ok))

def add_message(role, content):
    global last_assistant_button, last_message_text_widget

    bottom_before = is_at_bottom()

    if role == "user":
        bg_color = "#DCF8C6"
        text_color = "black"
        anchor = "e"
    else:
        bg_color = "#F1F0F0"
        text_color = "black"
        anchor = "w"

    bubble = Frame(chat_frame, bg="#ffffff")
    bubble.pack(fill="x", pady=5)

    text_widget = Text(
        bubble,
        bg=bg_color,
        fg=text_color,
        wrap="word",
        font=("Arial", 18),
        padx=20,
        pady=10,
        relief="flat",
        height=1
    )
    text_widget.insert("1.0", content)
    text_widget.pack(anchor=anchor, pady=(5, 0), padx=20, fill="x")

    def finalize():
        autosize_text_widget(text_widget)
        try:
            text_widget.configure(state="disabled")
        except Exception:
            pass

        if bottom_before:
            scroll_to_widget_end(text_widget)

    if role == "assistant":
        if last_assistant_button and last_assistant_button.winfo_exists():
            try:
                last_assistant_button.destroy()
            except Exception:
                pass

        copy_btn = Button(
            bubble,
            text="Copiar",
            font=("Arial", 12),
            padx=10,
            pady=3,
            bg="#E8F4FD",
            fg="#0b65c2",
            relief="groove",
            cursor="hand2",
        )
        def do_copy():
            copy_to_clipboard(content, copy_btn)
        copy_btn.config(command=do_copy)
        copy_btn.pack(anchor="e", padx=24, pady=(2, 2))
        last_assistant_button = copy_btn

    def finalize_and_set_last():
        global last_message_text_widget
        finalize()
        last_message_text_widget = text_widget

    root.after_idle(finalize_and_set_last)

def change_model(selected):
    global current_model
    current_model = selected

def change_api(selected):
    global current_api, client
    current_api = selected
    client = OpenAI(api_key=API_KEYS[current_api])

def export_chat():
    if not history:
        messagebox.showinfo("Exportar", "No hay mensajes para exportar")
        return
    filename = f"{current_api}_export_{datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}.json"
    path = os.path.join(BACKUP_DIRS[current_api], filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    messagebox.showinfo("Exportar", f"Chat exportado en:\n{path}")

def import_chat():
    file_path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
    if not file_path:
        return
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            global history
            history = data
            refresh_chat()
            messagebox.showinfo("Importar", "Chat importado correctamente")
        else:
            messagebox.showerror("Error", "Formato incorrecto")
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo importar: {e}")

def clear_chat():
    if messagebox.askyesno("Borrar", "¿Deseas borrar todo el chat actual?"):
        save_auto_chat("before_clear")
        global history
        history = []
        refresh_chat()

def refresh_chat():
    for widget in chat_frame.winfo_children():
        widget.destroy()

    global last_assistant_button, last_message_text_widget
    last_assistant_button = None
    last_message_text_widget = None

    for m in history:
        add_message(m["role"], m["content"])

    if last_message_text_widget and last_message_text_widget.winfo_exists():
        root.after_idle(lambda: scroll_to_widget_end(last_message_text_widget))

def save_auto_chat(prefix="chat_auto"):
    if not history:
        return
    filename = f"{current_api}_{prefix}_{datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}.json"
    path = os.path.join(BACKUP_DIRS[current_api], filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("⚠️ Error guardando chat automático:", e)

def copy_all_chat():
    text = ""
    for msg in history:
        prefix = "🧑💬 Tú: " if msg["role"] == "user" else "🤖 Asistente: "
        text += f"{prefix}{msg['content']}\n\n"
    root.clipboard_clear()
    root.clipboard_append(text)
    messagebox.showinfo("Copiar todo", "Chat copiado al portapapeles.")

# --- GUI ---
root = Tk()
root.title("💬 ChatGPT Tkinter")

sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
root.geometry(f"{int(sw*0.9)}x{int(sh*0.9)}+{int(sw*0.05)}+{int(sh*0.05)}")
root.configure(bg="#ffffff")

# --- Top frame ---
top_frame = Frame(root, bg="#ffffff")
top_frame.pack(fill=X, padx=15, pady=10)

label_font = ("Arial", 18)
button_font = ("Arial", 18, "bold")

Label(top_frame, text="Modelo:", bg="#ffffff", font=label_font).pack(side=LEFT)
model_var = StringVar(value=current_model)
OptionMenu(top_frame, model_var, "gpt-5", "gpt-5.1-codex", "gpt-5-mini", "gpt-5-nano", "gpt-5-codex", "gpt-5-codex", command=change_model).pack(side=LEFT, padx=10)

Label(top_frame, text="Clave API:", bg="#ffffff", font=label_font).pack(side=LEFT, padx=(20,0))
api_var = StringVar(value=current_api)
OptionMenu(top_frame, api_var, "personal", "oposicion", command=change_api).pack(side=LEFT, padx=10)

Button(top_frame, text="Copiar todo", font=button_font, command=copy_all_chat, width=12).pack(side=RIGHT, padx=5)
Button(top_frame, text="Exportar", font=button_font, command=export_chat, width=10).pack(side=RIGHT, padx=5)
Button(top_frame, text="Importar", font=button_font, command=import_chat, width=10).pack(side=RIGHT, padx=5)
Button(top_frame, text="Borrar", font=button_font, command=clear_chat, width=10).pack(side=RIGHT, padx=5)

# --- Input frame (abajo) ---
input_frame = Frame(root, bg="#ffffff", bd=2, relief="groove")
input_frame.pack(side=BOTTOM, fill=X, padx=15, pady=5)

input_scroll = Scrollbar(input_frame)
input_scroll.pack(side=RIGHT, fill=Y)

input_text = Text(input_frame, height=8, font=("Arial", 18), bg="#f7f7f8", wrap="word", yscrollcommand=input_scroll.set)
input_text.pack(side=LEFT, fill=X, expand=True, padx=(0,15))
input_scroll.config(command=input_text.yview)

send_button = Button(input_frame, text="Enviar", font=button_font, width=14, height=2, bg="#10a37f", fg="white", command=send_message)
send_button.pack(side=RIGHT)

# --- Chat frame con scroll (centro) ---
chat_canvas_frame = Frame(root)
chat_canvas_frame.pack(fill=BOTH, expand=True, padx=15, pady=(0,5))

canvas = Canvas(chat_canvas_frame, bg="#ffffff", highlightthickness=0)
canvas.pack(side=LEFT, fill=BOTH, expand=True)

def on_scrollbar(*args):
    canvas.yview(*args)

scrollbar = Scrollbar(chat_canvas_frame, orient=VERTICAL, command=on_scrollbar)
scrollbar.pack(side=RIGHT, fill=Y)
canvas.configure(yscrollcommand=scrollbar.set)

chat_frame = Frame(canvas, bg="#ffffff")
chat_window = canvas.create_window((0,0), window=chat_frame, anchor="nw")

def on_chat_frame_configure(event):
    canvas.configure(scrollregion=canvas.bbox("all"))

def on_canvas_configure(event):
    global chat_width
    chat_width = event.width
    canvas.itemconfig(chat_window, width=event.width)
    root.after_idle(reflow_text_heights)

chat_frame.bind("<Configure>", on_chat_frame_configure)
canvas.bind("<Configure>", on_canvas_configure)

def _on_mousewheel(event):
    try:
        if event.num == 4:
            canvas.yview_scroll(-3, "units")
        elif event.num == 5:
            canvas.yview_scroll(3, "units")
        else:
            delta = int(-1 * (event.delta / 120)) if hasattr(event, "delta") else -1
            canvas.yview_scroll(delta * 3, "units")
        return "break"
    except Exception:
        pass

canvas.bind("<MouseWheel>", _on_mousewheel)
canvas.bind("<Button-4>", _on_mousewheel)
canvas.bind("<Button-5>", _on_mousewheel)
chat_frame.bind("<MouseWheel>", _on_mousewheel)
chat_frame.bind("<Button-4>", _on_mousewheel)
chat_frame.bind("<Button-5>", _on_mousewheel)

def on_closing():
    save_auto_chat()
    try:
        if waiting_timer_id:
            root.after_cancel(waiting_timer_id)
    except Exception:
        pass
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)
root.mainloop()
