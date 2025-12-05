import sys, math, unicodedata

FILENAME = "codigo_postal.txt"  # fichero tab-delimited de GeoNames

def cp_a_lonlat(cp, filename=FILENAME):
    cp = str(cp).strip()
    if cp.isdigit() and len(cp) < 5:
        cp = cp.zfill(5)  # asegurar 5 dígitos (ej. 04002)

    lat_sum = 0.0
    lon_sum = 0.0
    n = 0

    with open(filename, encoding="utf-8") as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 11:
                continue
            if cols[1] == cp:
                try:
                    lat = float(cols[9])   # columna latitud
                    lon = float(cols[10])  # columna longitud
                except ValueError:
                    continue
                lat_sum += lat
                lon_sum += lon
                n += 1

    if n == 0:
        return None
    return (lon_sum / n, lat_sum / n)  # (lon, lat)

def _norm(s):
    s = s.strip().lower()
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")

def _unquote(s):
    s = s.strip()
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        return s[1:-1]
    return s

def cp_localidad_a_lonlat(cp, localidad, filename=FILENAME):
    """
    localidad:
      - Si vacía o solo espacios: elige la fila de mayor accuracy del CP.
      - Si con texto: busca coincidencia exacta normalizada; si no, parcial; si no, mayor accuracy.
    Devuelve (lon, lat) o None.
    """
    cp = str(cp).strip()
    if cp.isdigit() and len(cp) < 5:
        cp = cp.zfill(5)

    loc_raw = _unquote(localidad or "")
    loc_clean = loc_raw.strip()
    loc_norm = _norm(loc_raw) if loc_clean else ""

    filas_cp = []  # (name, lat, lon, acc)
    with open(filename, encoding="utf-8") as f:
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
                lat = float(cols[9]); lon = float(cols[10])
                acc = int(cols[11])
            except ValueError:
                continue
            filas_cp.append((name, lat, lon, acc))

    if not filas_cp:
        return None

    candidatos = filas_cp
    if loc_clean:
        exact = [r for r in filas_cp if _norm(r[0]) == loc_norm]
        if exact:
            candidatos = exact
        else:
            parciales = [r for r in filas_cp if (loc_norm in _norm(r[0])) or (_norm(r[0]) in loc_norm)]
            if parciales:
                candidatos = parciales
            # si no hay parciales, se queda con todas (caerá a mayor accuracy)

    # Elegir por mayor accuracy; si hay empate, la primera aparición
    best = max(candidatos, key=lambda r: r[3])
    _, lat, lon, _ = best
    return (lon, lat)

def distancia_km(lon1, lat1, lon2, lat2):
    R = 6371.0
    import math as m
    phi1 = m.radians(lat1); phi2 = m.radians(lat2)
    dphi = m.radians(lat2 - lat1); dlmb = m.radians(lon2 - lon1)
    a = m.sin(dphi/2)**2 + m.cos(phi1)*m.cos(phi2)*m.sin(dlmb/2)**2
    return 2 * R * m.asin((a**0.5))

def calcula_KM_con_CP():
    # Siempre: <cp1> "<localidad1>" <cp2> "<localidad2>"
    if len(sys.argv) != 5:
        print('Uso: python calcula_codigo_postal <cp1> "<localidad1>" <cp2> "<localidad2>"', file=sys.stderr)
        print('Pon "" si no quieres especificar localidad y tomar la de mayor precisión.', file=sys.stderr)
        sys.exit(1)

    cp1, loc1, cp2, loc2 = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

    res1 = cp_localidad_a_lonlat(cp1, loc1)
    if res1 is None:
        print(f"No encontrado: {cp1} ({loc1})", file=sys.stderr)
        sys.exit(2)
    lon1, lat1 = res1

    res2 = cp_localidad_a_lonlat(cp2, loc2)
    if res2 is None:
        print(f"No encontrado: {cp2} ({loc2})", file=sys.stderr)
        sys.exit(2)
    lon2, lat2 = res2

    dist = distancia_km(lon1, lat1, lon2, lat2)

    etiqueta1 = f"{cp1}:{_unquote(loc1).strip()}" if _unquote(loc1).strip() else f"{cp1}"
    etiqueta2 = f"{cp2}:{_unquote(loc2).strip()}" if _unquote(loc2).strip() else f"{cp2}"
    print(f"{etiqueta1}\t{lon1:.6f}\t{lat1:.6f}")
    print(f"{etiqueta2}\t{lon2:.6f}\t{lat2:.6f}")
    print(f"dist_km\t{dist:.3f}")

if __name__ == "__main__":
    calcula_KM_con_CP()