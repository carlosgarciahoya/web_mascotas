directorio = r"C:\Users\CGH\Documents"  # Cambia esto a una carpeta donde tengas permiso de escritura
recursivo = True
quiet = False
aplicar_borrado = False  # Pon True para borrar realmente
estrategia_conservar = "shortestname"  # "first", "newest", "oldest", "shortestname", "longestname"
algoritmo_hash = "sha256"  # "sha256", "blake2b", "md5"
compara_bytes = False  # True para detectar (y opcionalmente borrar) duplicados por tamaño total de archivo

import os
import hashlib

CHUNK_SIZE = 1024 * 1024  # 1 MiB

def iter_mp3_files(base, recursive=False):
    if recursive:
        for root, dirs, files in os.walk(base, followlinks=False):
            for name in files:
                if name.lower().endswith(".mp3"):
                    path = os.path.join(root, name)
                    if os.path.islink(path):
                        continue
                    try:
                        if os.path.isfile(path):
                            yield path
                    except OSError:
                        continue
    else:
        with os.scandir(base) as it:
            for entry in it:
                if entry.is_file(follow_symlinks=False) and not entry.is_symlink():
                    if entry.name.lower().endswith(".mp3"):
                        yield entry.path

def _syncsafe_to_int(b4):
    # 4 bytes "syncsafe": 0xxxxxxx 0xxxxxxx 0xxxxxxx 0xxxxxxx
    return (b4[0] << 21) | (b4[1] << 14) | (b4[2] << 7) | b4[3]

def _mp3_audio_region(path, fsize):
    # Calcula [start, end) ignorando ID3v2 al inicio e ID3v1 al final.
    start = 0
    end = fsize
    with open(path, "rb") as f:
        # ID3v2 al inicio
        header = f.read(10)
        if len(header) == 10 and header[:3] == b"ID3":
            flags = header[5]
            size = _syncsafe_to_int(header[6:10])
            start = 10 + size + (10 if (flags & 0x10) else 0)

        # ID3v1 al final (128 bytes con "TAG")
        if fsize >= 128:
            try:
                f.seek(fsize - 128)
                tail = f.read(128)
                if tail.startswith(b"TAG"):
                    end = fsize - 128
            except OSError:
                pass

    if start < 0: start = 0
    if end > fsize: end = fsize
    if start >= end:
        start, end = 0, fsize
    return start, end

def mp3_audio_hash(path, algo="sha256", fsize=None):
    if fsize is None:
        st = os.stat(path, follow_symlinks=False)
        fsize = st.st_size
    h = hashlib.new(algo)
    start, end = _mp3_audio_region(path, fsize)
    with open(path, "rb") as f:
        f.seek(start)
        remaining = end - start
        while remaining > 0:
            chunk = f.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            h.update(chunk)
            remaining -= len(chunk)
    return h.hexdigest(), (end - start)

def choose_keep(paths, strategy):
    if strategy == "first":
        return paths[0]
    elif strategy == "newest":
        return max(paths, key=lambda p: os.stat(p, follow_symlinks=False).st_mtime)
    elif strategy == "oldest":
        return min(paths, key=lambda p: os.stat(p, follow_symlinks=False).st_mtime)
    elif strategy == "shortestname":
        return min(paths, key=lambda p: len(os.path.basename(p)))
    elif strategy == "longestname":
        return max(paths, key=lambda p: len(os.path.basename(p)))
    return paths[0]

def _abrir_log_en_directorio(base):
    nombre = "duplicados_mp3.txt"
    try:
        ruta = os.path.join(base, nombre)
        log = open(ruta, "w", encoding="utf-8")
        print("directorio y ruta  =", ruta)
        return log, ruta
    except Exception:
        ruta = os.path.abspath(nombre)
        log = open(ruta, "w", encoding="utf-8")
        return log, ruta

def formato_bytes(n):
    unidades = ["bytes", "KB", "MB", "GB", "TB"]
    v = float(n)
    i = 0
    while v >= 1024 and i < len(unidades) - 1:
        v /= 1024.0
        i += 1
    if i == 0:
        return f"{int(v)} {unidades[i]}"
    else:
        return f"{v:.2f} {unidades[i]}"

def registrar_estimacion(logw, bytes_audio, bytes_tamano, bytes_total):
    logw("")
    logw("Estimación de espacio recuperable si se borran todos los duplicados detectados:")
    logw(f"  - Por duplicados de AUDIO: {formato_bytes(bytes_audio)} ({bytes_audio} bytes)")
    if compara_bytes:
        logw(f"  - Por duplicados de TAMAÑO (excluyendo los ya marcados por AUDIO): {formato_bytes(bytes_tamano)} ({bytes_tamano} bytes)")
    logw(f"  - TOTAL estimado: {formato_bytes(bytes_total)} ({bytes_total} bytes)")

def run():
    base = directorio
    log, ruta_log = _abrir_log_en_directorio(base)

    print("directorio =", base, ruta_log)

    def logw(msg):
        log.write(str(msg) + "\n")

    logw(f"LOG en: {ruta_log}")

    if not os.path.isdir(base):
        logw(f"No es un directorio válido: {base}")
        log.close()
        return

    try:
        files = list(iter_mp3_files(base, recursive=recursivo))
    except OSError as e:
        files = []
        logw(f"Error leyendo el directorio {base}: {e}")

    if not quiet:
        logw(f"MP3 analizados: {len(files)}")

    grupos_audio = {}  # clave: (hash_audio, bytes_audio) -> [rutas]
    grupos_tamano = {} if compara_bytes else None  # clave: tamaño total -> [rutas]
    borrados_global = set()
    errores = 0

    # Guardamos tamaños de archivo para poder sumar espacio a liberar
    tamanos_archivo = {}

    for p in files:
        try:
            st = os.stat(p, follow_symlinks=False)
            size_total = st.st_size
            tamanos_archivo[p] = size_total

            if compara_bytes:
                grupos_tamano.setdefault(size_total, []).append(p)

            digest, audio_len = mp3_audio_hash(p, algoritmo_hash, fsize=size_total)
            key_audio = (digest, audio_len)
            grupos_audio.setdefault(key_audio, []).append(p)

        except (OSError, PermissionError) as e:
            errores += 1
            if not quiet:
                logw(f"No se pudo procesar {p}: {e}")

    # Conjuntos para estimación (evitan doble conteo)
    marcados_audio = set()
    marcados_tamano = set()

    # 1) Duplicados por AUDIO
    total_grupos_audio = 0
    total_a_borrar_audio = 0
    borrados_audio = 0
    bytes_liberados_audio = 0  # si aplicar_borrado=True

    for (digest, audio_len), paths in grupos_audio.items():
        vivos = [p for p in paths if os.path.exists(p)]
        if len(vivos) <= 1:
            continue

        total_grupos_audio += 1
        keep = choose_keep(vivos, estrategia_conservar)
        to_delete = [p for p in vivos if p != keep]

        if not quiet:
            logw("")
            logw(f"Duplicado por AUDIO hash={digest[:16]}..., bytes_audio={audio_len}")
            logw(f"  Conservar: {keep}")
            for p in to_delete:
                logw(f"  Eliminar:  {p}")

        total_a_borrar_audio += len(to_delete)
        # Estimación (marcar para no contarlo de nuevo)
        for p in to_delete:
            marcados_audio.add(p)

        if aplicar_borrado:
            for p in to_delete:
                try:
                    os.remove(p)
                    borrados_audio += 1
                    bytes_liberados_audio += tamanos_archivo.get(p, 0)
                    borrados_global.add(p)
                except OSError as e:
                    logw(f"No se pudo eliminar {p}: {e}")

    # 2) Duplicados por TAMAÑO (opcional)
    total_grupos_tamano = 0
    total_a_borrar_tamano = 0
    borrados_tamano = 0
    bytes_liberados_tamano = 0  # si aplicar_borrado=True

    if compara_bytes and grupos_tamano:
        for size, paths in grupos_tamano.items():
            # Para estimación evitar doble conteo con lo ya marcado por AUDIO
            if aplicar_borrado:
                vivos = [p for p in paths if os.path.exists(p) and p not in borrados_global]
            else:
                vivos = [p for p in paths if os.path.exists(p) and p not in marcados_audio]

            if len(vivos) <= 1:
                continue

            total_grupos_tamano += 1
            keep = choose_keep(vivos, estrategia_conservar)
            to_delete = [p for p in vivos if p != keep]

            if not quiet:
                logw("")
                logw(f"Duplicado por TAMAÑO total={size} bytes")
                logw(f"  Conservar: {keep}")
                for p in to_delete:
                    logw(f"  Eliminar:  {p}")

            total_a_borrar_tamano += len(to_delete)

            # Estimación (marcar)
            for p in to_delete:
                marcados_tamano.add(p)

            if aplicar_borrado:
                for p in to_delete:
                    try:
                        os.remove(p)
                        borrados_tamano += 1
                        bytes_liberados_tamano += tamanos_archivo.get(p, 0)
                        borrados_global.add(p)
                    except OSError as e:
                        logw(f"No se pudo eliminar {p}: {e}")

    # Resúmenes
    if aplicar_borrado:
        logw("")
        logw(f"Resumen AUDIO: grupos={total_grupos_audio}, eliminados={borrados_audio} archivos")
        if compara_bytes:
            logw(f"Resumen TAMAÑO: grupos={total_grupos_tamano}, eliminados={borrados_tamano} archivos")
            total_eliminados = borrados_audio + borrados_tamano
            total_bytes = bytes_liberados_audio + bytes_liberados_tamano
            logw(f"Total eliminados: {total_eliminados} archivos")
            registrar_estimacion(logw, bytes_liberados_audio, bytes_liberados_tamano, total_bytes)
        else:
            registrar_estimacion(logw, bytes_liberados_audio, 0, bytes_liberados_audio)
    else:
        logw("")
        logw(f"DRY-RUN AUDIO: grupos={total_grupos_audio}, se eliminarían={total_a_borrar_audio} archivos")
        if compara_bytes:
            logw(f"DRY-RUN TAMAÑO: grupos={total_grupos_tamano}, se eliminarían={total_a_borrar_tamano} archivos")

        # Estimación de espacio recuperable (sin borrar de verdad)
        bytes_est_audio = sum(tamanos_archivo.get(p, 0) for p in marcados_audio)
        bytes_est_tamano = sum(tamanos_archivo.get(p, 0) for p in marcados_tamano)
        # Total por la unión (ya evitamos doble conteo, pero así es robusto):
        total_est = sum(tamanos_archivo.get(p, 0) for p in (marcados_audio | marcados_tamano))
        registrar_estimacion(logw, bytes_est_audio, bytes_est_tamano, total_est)

        logw("Cambia aplicar_borrado = True para ejecutar los borrados.")

    if errores and not quiet:
        logw(f"Avisos/errores durante el proceso: {errores}")

    log.close()

if __name__ == "__main__":
    run()