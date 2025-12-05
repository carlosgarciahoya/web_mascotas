#!/usr/bin/env python3
import sys
import ast
import warnings
from pathlib import Path

def extract_imports(text, filename="<unknown>"):
    # Silencia SyntaxWarning (p. ej. "invalid escape sequence") al parsear
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        try:
            tree = ast.parse(text, filename=filename)
        except SyntaxError:
            return []
    lines = text.splitlines()
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            start = getattr(node, "lineno", None)
            end = getattr(node, "end_lineno", None) or start
            if start is None:
                continue
            snippet = "\n".join(line.rstrip() for line in lines[start-1:end]).strip()
            out.append(snippet)
    return out

def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    seen = set()
    uniques = []

    for py in root.rglob("*.py"):
        if not py.is_file():
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for snippet in extract_imports(text, filename=str(py)):
            if snippet not in seen:
                seen.add(snippet)
                uniques.append(snippet)

    out_path = Path(__file__).resolve().parent / "todos_imports.txt"
    with out_path.open("w", encoding="utf-8") as f:
        for i, s in enumerate(uniques):
            if i:
                f.write("\n")  # línea en blanco entre entradas
            f.write(s + "\n")

if __name__ == "__main__":
    main()
