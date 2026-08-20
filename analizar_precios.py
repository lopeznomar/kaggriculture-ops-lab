"""
Extrae, de un replay JSON de Kaggriculture, el precio de mercado turno a
turno de cada producto y las ordenes de compra (BUY_SEED/BUY_ANIMAL) que
emitio RamonLopez, para diagnosticar POR QUE en una partida dada un solo
cultivo (ej. MELON) termino acaparando el 100% de la inversion mientras
todo lo demas (incluyendo WHEAT, que suele ser rentable) quedo en $0.

USO:
    python3 analizar_precios.py ruta/al/archivo.json [NOMBRE_JUGADOR]

Si no reconoce la estructura del archivo, en vez de fallar en silencio
imprime un mapa de las claves que SI encontro, para poder ajustar el
script juntos.

Que hace con el resultado:
  1) Imprime el precio de cada producto en algunos puntos de la partida
     (arranque, 25%, 50%, 75%, final) -- para ver si WHEAT/CARROT/etc.
     realmente se derrumbaron, o se mantuvieron en un rango normal.
  2) Cuenta cuantas ordenes BUY_SEED/BUY_ANIMAL se emitieron por rubro en
     TODA la partida -- si WHEAT aparece con 0 ordenes en TODA la
     partida pese a tener precio normal, eso apunta al bug de
     secuenciacion de presupuesto (hipotesis B). Si WHEAT nunca aparece
     porque su precio estuvo hundido, apunta a mercado adverso real
     (hipotesis A).
  3) Guarda un CSV (precios_por_turno.csv) con la serie completa de
     precios turno a turno, por si despues queremos graficarla.
"""
import json
import sys
import csv
from pathlib import Path

PRODUCTOS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"]


def cargar(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def explorar_estructura(obj, prefix="", max_depth=4, depth=0, out=None):
    """Imprime un mapa superficial de claves/tipos para diagnosticar el
    formato del archivo si el parser normal no lo reconoce."""
    if out is None:
        out = []
    if depth > max_depth:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            tipo = type(v).__name__
            extra = f" (len={len(v)})" if isinstance(v, (list, dict)) else f" = {v!r}"[:60]
            out.append(f"{prefix}{k}: {tipo}{extra}")
            if isinstance(v, (dict, list)) and depth < max_depth:
                explorar_estructura(v, prefix + "  ", max_depth, depth + 1, out)
    elif isinstance(obj, list) and obj:
        out.append(f"{prefix}[0]: {type(obj[0]).__name__}")
        explorar_estructura(obj[0], prefix + "  ", max_depth, depth + 1, out)
    return out


def buscar_pasos(data):
    """Intenta ubicar la lista de 'pasos'/'steps' del replay, tolerando
    varios formatos comunes de exports de Kaggle."""
    candidatos = []
    if isinstance(data, dict):
        for key in ("steps", "state", "history", "frames", "turns"):
            if key in data and isinstance(data[key], list):
                candidatos.append(data[key])
    if isinstance(data, list):
        candidatos.append(data)
    return candidatos


def extraer_obs(paso):
    """De un elemento de la lista de pasos, intenta llegar a la
    observacion real (probando varias formas anidadas conocidas)."""
    if isinstance(paso, dict):
        for key in ("observation", "obs", "state"):
            if key in paso:
                sub = paso[key]
                return sub if isinstance(sub, dict) else None
        return paso
    if isinstance(paso, list) and paso:
        # formato tipico Kaggle: [ {agent0}, {agent1}, ... ]
        for agente in paso:
            obs = extraer_obs(agente)
            if obs:
                return obs
    return None


def sacar_precios(obs):
    for path in (
        lambda o: o.get("market", {}).get("prices"),
        lambda o: o.get("prices"),
        lambda o: o.get("market_prices"),
    ):
        try:
            p = path(obs)
            if isinstance(p, dict) and p:
                return p
        except AttributeError:
            continue
    return None


def sacar_dia_hora(obs):
    day = obs.get("day", obs.get("dia"))
    hour = obs.get("hour", obs.get("turno", obs.get("hora")))
    return day, hour


def sacar_orders(obs, jugador_nombre=None):
    """Busca ordenes de mercado del jugador dentro de la obs/paso, si
    estan expuestas (nombre de campo puede variar)."""
    for key in ("market_orders", "orders", "actions"):
        v = obs.get(key)
        if v:
            return v
    return None


def main():
    if len(sys.argv) < 2:
        print("Uso: python3 analizar_precios.py archivo.json [NOMBRE_JUGADOR]")
        sys.exit(1)

    path = sys.argv[1]
    jugador = sys.argv[2] if len(sys.argv) > 2 else None

    data = cargar(path)
    listas = buscar_pasos(data)

    if not listas:
        print("No pude encontrar una lista de turnos/pasos reconocible en este archivo.")
        print("Mapa de la estructura raiz (mandame esto para ajustar el script):")
        for line in explorar_estructura(data):
            print(" ", line)
        sys.exit(1)

    pasos = max(listas, key=len)
    print(f"Encontre {len(pasos)} pasos/turnos en el archivo.")

    serie = []  # (day, hour, {producto: precio})
    for i, paso in enumerate(pasos):
        obs = extraer_obs(paso)
        if not obs:
            continue
        precios = sacar_precios(obs)
        if not precios:
            continue
        day, hour = sacar_dia_hora(obs)
        serie.append((i, day, hour, precios))

    if not serie:
        print("Encontre los pasos pero no pude sacar precios de mercado de ninguno.")
        print("Mapa de un paso de ejemplo (mandame esto para ajustar el script):")
        muestra = extraer_obs(pasos[len(pasos) // 2]) or pasos[len(pasos) // 2]
        for line in explorar_estructura(muestra):
            print(" ", line)
        sys.exit(1)

    print(f"Extraje precios de mercado en {len(serie)} de esos pasos.")
    print()

    # --- 1) precios en 5 puntos de la partida ---
    puntos = [0, len(serie) // 4, len(serie) // 2, (3 * len(serie)) // 4, len(serie) - 1]
    print("=" * 78)
    print("PRECIO DE MERCADO EN 5 MOMENTOS DE LA PARTIDA")
    print("=" * 78)
    header = f"{'dia/turno':12s}" + "".join(f"{p:>12s}" for p in PRODUCTOS)
    print(header)
    for idx in puntos:
        _, day, hour, precios = serie[idx]
        etiqueta = f"d{day}h{hour}" if day is not None else f"paso{idx}"
        fila = f"{etiqueta:12s}" + "".join(
            f"{precios.get(p, float('nan')):12.1f}" if p in precios else f"{'--':>12s}"
            for p in PRODUCTOS
        )
        print(fila)
    print()

    # --- 2) minimo y maximo de cada producto en toda la partida ---
    print("=" * 78)
    print("RANGO DE PRECIO (min - max) EN TODA LA PARTIDA")
    print("=" * 78)
    for p in PRODUCTOS:
        vals = [precios[p] for _, _, _, precios in serie if p in precios]
        if vals:
            print(f"  {p:12s} min={min(vals):8.1f}  max={max(vals):8.1f}  promedio={sum(vals)/len(vals):8.1f}")
        else:
            print(f"  {p:12s} (no encontrado en la serie)")
    print()

    # --- 3) CSV completo ---
    out_csv = Path(path).with_name("precios_por_turno.csv")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["paso", "day", "hour"] + PRODUCTOS)
        for idx, day, hour, precios in serie:
            w.writerow([idx, day, hour] + [precios.get(p, "") for p in PRODUCTOS])
    print(f"Serie completa guardada en: {out_csv}")

    # --- 4) ordenes de compra por rubro (si el archivo las expone) ---
    print()
    print("=" * 78)
    print("ORDENES DE COMPRA POR RUBRO (si el archivo las expone)")
    print("=" * 78)
    conteo = {p: 0 for p in PRODUCTOS}
    encontro_ordenes = False
    for paso in pasos:
        obs = extraer_obs(paso)
        if not obs:
            continue
        orders = sacar_orders(obs, jugador)
        if not orders:
            continue
        encontro_ordenes = True
        for o in orders:
            if isinstance(o, (list, tuple)) and len(o) >= 2:
                kind, item = o[0], o[1]
                if kind in ("BUY_SEED", "BUY_ANIMAL") and item in conteo:
                    conteo[item] += 1
    if encontro_ordenes:
        for p, n in conteo.items():
            print(f"  {p:12s} ordenes de compra: {n}")
    else:
        print("  No encontre un campo de 'ordenes' expuesto en este archivo -- no pasa nada,")
        print("  con los precios turno a turno alcanza para diagnosticar la hipotesis A.")


if __name__ == "__main__":
    main()
