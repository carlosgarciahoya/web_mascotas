from __future__ import annotations

from pathlib import Path
from typing import List

# import sys

# Ajusta esta ruta a la ubicación real de tu fichero
# (por ejemplo, en la carpeta data/ o donde lo tengas guardado).
RUTA_FICHERO_CP = Path(__file__).resolve().parents[2] / "web"  / "utils"/  "codigo_postal.txt"


def cp_localidades(cp: str) -> List[str]:
    """
    Devuelve la lista de localidades asociadas a un código postal.
    - cp: código postal en formato texto (se normaliza a 5 dígitos).
    - return: lista sin duplicados, ordenada alfabéticamente.
    """
    if not cp:
        return []

    cp_normalizado = cp.strip()
    if not cp_normalizado.isdigit():
        return []

    localidades: set[str] = set()

    with RUTA_FICHERO_CP.open("r", encoding="utf-8") as fh:
        for linea in fh:
            if not linea or linea.startswith("#"):
                continue

            campos = linea.rstrip("\n").split("\t")
            if len(campos) < 3:
                continue

            pais, codigo_postal, place_name = campos[0], campos[1], campos[2]

            # Filtramos solo España (código ES) y el CP pedido
            if pais != "ES" or codigo_postal != cp_normalizado:
                continue

            localidad = place_name.strip()
            if localidad:
                localidades.add(localidad)

    print ( sorted(localidades))
    return sorted(localidades)

# if __name__ == "__main__":
#    print (cp_localidades (sys.argv[1]))