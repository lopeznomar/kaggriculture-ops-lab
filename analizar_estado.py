"""
v3: ademas de precios, extrae ESTADO REAL del jugador turno a turno:
dinero, semillas en inventario, tiles ocupadas por cada cultivo, y
cuadrantes de tierra desbloqueados.

AJUSTE (mismo bug encontrado en investigate_spike.py, corregido aca
tambien de forma preventiva): antes esto dependia de que vos pasaras el
INDICE_JUGADOR correcto a mano cada vez, con default=0 -- facil de
pasar por alto, y ya confirmamos que el indice de RamonLopez cambia de
partida en partida. Ahora se detecta automaticamente por nombre de
equipo (mismo criterio que investigate_stall.py), y el argumento manual
queda solo como override opcional si hiciera falta forzarlo.

USO:
    python3 analizar_estado.py archivo.json [nombre_o_indice]

    Sin el segundo argumento: detecta "RamonLopez" automaticamente.
    Con texto (ej "RamonLopez" o "Lopez"): busca ese nombre de equipo.
    Con un numero (ej "1"): fuerza ese indice a mano.
"""
import json
import sys
import csv
import unicodedata
from pathlib import Path


def _normalizar(s):
    """Saca acentos/mayusculas para poder comparar 'RamonLopez' con
    'RamónLópez' sin que la tilde rompa la coincidencia."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s or "")
        if unicodedata.category(c) != "Mn"
    ).lower()

CULTIVOS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"]
ANIMALES = ["GOOSE", "COW", "SHEEP"]
NOMBRE_DEFAULT = "RamónLópez"


def cargar(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def buscar_pasos(data):
    if isinstance(data, dict):
        for key in ("steps", "state", "history", "frames", "turns"):
            if key in data and isinstance(data[key], list):
                return data[key]
    if isinstance(data, list):
        return data
    return []


def extraer_obs(paso, idx=None):
    """Si se pide un indice especifico, intenta leer paso[idx] primero
    (asi cada jugador ve SU PROPIA vista privada) antes de caer al
    generico."""
    if idx is not None and isinstance(paso, list) and idx < len(paso):
        candidato = paso[idx]
        if isinstance(candidato, dict):
            for key in ("observation", "obs", "state"):
                if key in candidato:
                    sub = candidato[key]
                    if isinstance(sub, dict):
                        return sub
    if isinstance(paso, dict):
        for key in ("observation", "obs", "state"):
            if key in paso:
                sub = paso[key]
                return sub if isinstance(sub, dict) else None
        return paso
    if isinstance(paso, list) and paso:
        for agente in paso:
            obs = extraer_obs(agente)
            if obs:
                return obs
    return None


def detectar_indice(data, nombre_o_indice):
    """Devuelve (indice, nombre_encontrado). Si nombre_o_indice es un
    numero, lo fuerza directo. Si no, busca por nombre de equipo en
    info.TeamNames (igual que investigate_stall.py)."""
    if nombre_o_indice is not None:
        try:
            idx = int(nombre_o_indice)
            info = data.get("info", {}) if isinstance(data, dict) else {}
            team_names = info.get("TeamNames", [])
            nombre = team_names[idx] if idx < len(team_names) else f"indice {idx}"
            return idx, nombre
        except (ValueError, TypeError):
            pass

    hint = nombre_o_indice or NOMBRE_DEFAULT
    info = data.get("info", {}) if isinstance(data, dict) else {}
    team_names = info.get("TeamNames") or []
    hint_norm = _normalizar(hint)
    for i, name in enumerate(team_names):
        name_norm = _normalizar(name)
        if hint_norm in name_norm or name_norm in hint_norm:
            return i, name

    # No se encontro info.TeamNames (formato distinto) -- avisar y caer a 0
    print(f"AVISO: no encontre 'info.TeamNames' en el archivo para confirmar el indice.")
    print(f"       Asumiendo indice 0 -- VERIFICA que sea correcto con el nombre que te muestre.")
    return 0, None


def contar_cultivo_en_tablero(tiles, crop):
    if not tiles:
        return 0
    n = 0
    for fila in tiles:
        for celda in (fila or []):
            if isinstance(celda, dict) and celda.get("kind") == "PLANT" and celda.get("crop") == crop:
                n += 1
    return n


def contar_animal_en_tablero(tiles, animal):
    if not tiles:
        return 0
    n = 0
    for fila in tiles:
        for celda in (fila or []):
            if isinstance(celda, dict) and celda.get("animal") == animal:
                n += 1
    return n


def contar_tiles_vacias(tiles):
    if not tiles:
        return 0
    n = 0
    for fila in tiles:
        for celda in (fila or []):
            if celda is None:
                n += 1
    return n


def main():
    if len(sys.argv) < 2:
        print("Uso: python3 analizar_estado.py archivo.json [nombre_o_indice]")
        sys.exit(1)

    path = sys.argv[1]
    arg2 = sys.argv[2] if len(sys.argv) > 2 else None

    data = cargar(path)
    pasos = buscar_pasos(data)
    if not pasos:
        print("No encontre una lista de pasos -- misma limitacion que analizar_precios.py")
        sys.exit(1)

    idx_jugador, nombre_encontrado = detectar_indice(data, arg2)
    if nombre_encontrado:
        print(f"Jugador detectado: indice {idx_jugador} = '{nombre_encontrado}'")
    else:
        print(f"Usando indice {idx_jugador} (sin confirmar por nombre -- revisa que sea el correcto)")
    print()

    filas = []
    for i, paso in enumerate(pasos):
        obs = extraer_obs(paso, idx_jugador)
        if not obs:
            continue
        farms = obs.get("farms")
        if not farms or idx_jugador >= len(farms):
            continue
        farm = farms[idx_jugador]
        tiles = farm.get("tiles")
        seeds = (obs.get("private") or {}).get("seeds") or {}
        shed = (obs.get("private") or {}).get("shed") or {}

        fila = {
            "paso": i,
            "day": obs.get("day"),
            "hour": obs.get("hour"),
            "money": farm.get("money"),
            "cuadrantes": len(farm.get("unlocked_quadrants") or []),
            "manos": len(farm.get("hands") or []),
            "tiles_vacias": contar_tiles_vacias(tiles),
        }
        for c in CULTIVOS:
            fila[f"tiles_{c}"] = contar_cultivo_en_tablero(tiles, c)
            fila[f"semilla_{c}"] = seeds.get(c, 0)
        for a in ANIMALES:
            fila[f"animal_{a}"] = contar_animal_en_tablero(tiles, a)
            fila[f"shed_{a}"] = shed.get(a, 0)
        filas.append(fila)

    if not filas:
        print("No pude extraer estado de ningun paso -- revisa el indice/nombre o mandame")
        print("un paso de ejemplo (obs['farms']) para ajustar el parser.")
        sys.exit(1)

    print(f"Extraje estado de {len(filas)} pasos para el jugador indice {idx_jugador}.")
    print()

    # --- tabla resumen en varios puntos de la partida ---
    puntos = [0, len(filas) // 8, len(filas) // 4, len(filas) * 3 // 8, len(filas) // 2,
              len(filas) * 5 // 8, len(filas) * 3 // 4, len(filas) * 7 // 8, len(filas) - 1]
    puntos = sorted(set(puntos))

    print("=" * 100)
    print("TILES OCUPADAS POR CULTIVO (y tiles vacias) A LO LARGO DE LA PARTIDA")
    print("=" * 100)
    header = f"{'dia/turno':10s}{'money':>9s}{'cuad':>5s}{'vacias':>7s}" + "".join(f"{c:>11s}" for c in CULTIVOS)
    print(header)
    for idx in puntos:
        f = filas[idx]
        etiqueta = f"d{f['day']}h{f['hour']}"
        linea = f"{etiqueta:10s}{f['money']:9.0f}{f['cuadrantes']:5d}{f['tiles_vacias']:7d}"
        linea += "".join(f"{f[f'tiles_{c}']:11d}" for c in CULTIVOS)
        print(linea)
    print()

    print("=" * 100)
    print("SEMILLAS EN INVENTARIO (compradas, esperando plantarse) EN LOS MISMOS PUNTOS")
    print("=" * 100)
    header = f"{'dia/turno':10s}" + "".join(f"{c:>11s}" for c in CULTIVOS)
    print(header)
    for idx in puntos:
        f = filas[idx]
        etiqueta = f"d{f['day']}h{f['hour']}"
        linea = f"{etiqueta:10s}" + "".join(f"{f[f'semilla_{c}']:11d}" for c in CULTIVOS)
        print(linea)
    print()

    print("=" * 100)
    print("ANIMALES EN TABLERO Y EN SHED (esperando colocarse) EN LOS MISMOS PUNTOS")
    print("=" * 100)
    header = f"{'dia/turno':10s}" + "".join(f"{a+'(tablero)':>14s}" for a in ANIMALES) + "".join(f"{a+'(shed)':>12s}" for a in ANIMALES)
    print(header)
    for idx in puntos:
        f = filas[idx]
        etiqueta = f"d{f['day']}h{f['hour']}"
        linea = f"{etiqueta:10s}" + "".join(f"{f[f'animal_{a}']:14d}" for a in ANIMALES) + "".join(f"{f[f'shed_{a}']:12d}" for a in ANIMALES)
        print(linea)
    print()

    # --- primera vez que aparece semilla/tile de cada cultivo (o "nunca") ---
    print("=" * 100)
    print("PRIMERA APARICION DE CADA CULTIVO/ANIMAL EN TODA LA PARTIDA")
    print("=" * 100)
    for c in CULTIVOS:
        primera_semilla = next((f["day"] for f in filas if f[f"semilla_{c}"] > 0), None)
        primera_tile = next((f["day"] for f in filas if f[f"tiles_{c}"] > 0), None)
        print(f"  {c:12s} primera semilla comprada: dia {primera_semilla!s:6s}  primera tile plantada: dia {primera_tile!s}")
    for a in ANIMALES:
        primera_shed = next((f["day"] for f in filas if f[f"shed_{a}"] > 0), None)
        primera_tablero = next((f["day"] for f in filas if f[f"animal_{a}"] > 0), None)
        print(f"  {a:12s} primera vez en shed: dia {primera_shed!s:6s}  primera vez colocado: dia {primera_tablero!s}")
    print()

    # --- csv completo ---
    out_csv = Path(path).with_name("estado_por_turno.csv")
    campos = list(filas[0].keys())
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        for fila in filas:
            w.writerow(fila)
    print(f"Serie completa guardada en: {out_csv}")


if __name__ == "__main__":
    main()
