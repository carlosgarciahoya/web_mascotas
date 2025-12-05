from __future__ import annotations

from pathlib import Path
import math
import unicodedata
from typing import Optional, Tuple

FICHERO_CP = Path(__file__).resolve().parent / "codigo_postal.txt"


def _norm(texto: str) -> str:
    texto = texto.strip().lower()
    texto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def _unquote(valor: str) -> str:
    valor = valor.strip()
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in {'"', "'"}:
        return valor[1:-1]
    return valor


def cp_localidad_a_lonlat(
    cp: str,
    localidad: str,
    filename: Path = FICHERO_CP,
) -> Optional[Tuple[float, float]]:
    cp = str(cp).strip()
    if cp.isdigit() and len(cp) < 5:
        cp = cp.zfill(5)

    loc_raw = _unquote(localidad or "")
    loc_clean = loc_raw.strip()
    loc_norm = _norm(loc_raw) if loc_clean else ""

    filas_cp = []
    with filename.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 12:
                continue
            if cols[1] != cp:
                continue
            name = cols[2]
            try:
                lat = float(cols[9])
                lon = float(cols[10])
                acc = int(cols[11])
            except ValueError:
                continue
            filas_cp.append((name, lat, lon, acc))

    if not filas_cp:
        return None

    candidatos = filas_cp
    if loc_clean:
        exactos = [fila for fila in filas_cp if _norm(fila[0]) == loc_norm]
        if exactos:
            candidatos = exactos
        else:
            parciales = [
                fila
                for fila in filas_cp
                if loc_norm in _norm(fila[0]) or _norm(fila[0]) in loc_norm
            ]
            if parciales:
                candidatos = parciales

    mejor = max(candidatos, key=lambda fila: fila[3])
    _, lat, lon, _ = mejor
    return (lon, lat)


def distancia_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


def calcula_KM_con_CP(
    cp1: str,
    localidad1: str,
    cp2: str,
    localidad2: str,
) -> Optional[float]:
    """
    Devuelve solo la distancia en km entre (cp1, localidad1) y (cp2, localidad2).
    Si alguno no se encuentra, retorna None.
    """
    res1 = cp_localidad_a_lonlat(cp1, localidad1)
    if res1 is None:
        return None
    lon1, lat1 = res1

    res2 = cp_localidad_a_lonlat(cp2, localidad2)
    if res2 is None:
        return None
    lon2, lat2 = res2

    return distancia_km(lon1, lat1, lon2, lat2)