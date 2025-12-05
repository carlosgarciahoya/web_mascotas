import fitz  # PyMuPDF
from pathlib import Path

def pdf_lineas(pdf_path):
    with fitz.open(pdf_path) as doc:
        for page in doc:
            # "text" devuelve texto con saltos de línea
            texto = page.get_text("text", flags=fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE)
            for linea in texto.splitlines():
                yield linea

pdf_path = Path(r"C:\Users\CGH\Documents\DNI todos\documentos jubilacion brecha genero\BG 1185 firmar formulario.pdf")
out_path = pdf_path.with_suffix(".txt")

with open(out_path, "w", encoding="utf-8", newline="\n") as f:
    for linea in pdf_lineas(pdf_path):
        f.write(linea + "\n")