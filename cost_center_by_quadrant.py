"""
cost_center_by_quadrant.py
-----------------------------
Costeo por CENTRO DE COSTOS: cada uno de los 4 cuadrantes de tierra
(Cuarto 1=NW, Cuarto 2=NE, Cuarto 3=SW, Cuarto 4=SE) tratado como una
unidad de negocio separada, con sus propios costos e ingresos.

QUE ES DIRECTO (atribuible con precision, no una estimacion):
  - Costo de expansion de tierra: exacto, sabemos que cuadrante costo que.
  - Costo de semilla: se atribuye en el momento de la accion PLANT (no en
    el momento de compra), usando la posicion real donde se planto.
  - Costo de animal: se atribuye en el momento en que un animal aparece
    colocado en una tile (posicion real = cuadrante real).
  - Ingreso de cosecha: se atribuye en el momento de HARVEST/HARVEST_ANIMAL
    en una posicion real, valuado al precio de mercado de ESE turno y a
    max_yield (rendimiento pleno) -- es un ingreso "de libro" para poder
    comparar cuadrantes, no el monto exacto de la venta real (que se
    mezcla en el shed y pierde el origen). Ver nota mas abajo.

QUE ES PRORRATEADO (una aproximacion razonable, no un hecho):
  - Mano de obra (contratacion): no esta asignada a ningun cuadrante --
    se reparte cada dia en proporcion a cuantas acciones (turnos de
    unidad) se hicieron en cada cuadrante ese dia.

Uso:
    python cost_center_by_quadrant.py <archivo>.json [nombre_o_indice]

Genera:
    - Tabla en consola: ingreso directo, costo directo, mano de obra
      prorrateada, y neto por cuadrante
    - cost_center_by_quadrant.png: grafico de barras comparando los 4
      cuadrantes
"""
import json
import sys
import unicodedata
from pathlib import Path
from collections import defaultdict

SEED_COST = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50, "STRAWBERRY": 100, "MELON": 80}
ANIMAL_COST = {"GOOSE": 300, "COW": 400, "SHEEP": 500}
ANIMAL_PRODUCT = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}
MAX_YIELD = {"WHEAT": 4, "CARROT": 3, "TOMATO": 4, "STRAWBERRY": 4, "MELON": 6,
             "GOOSE": 4, "COW": 6, "SHEEP": 6}
LAND_COSTS_IN_ORDER = [1000, 2000, 4000]  # NE, SW, SE en ese orden de compra
QUADRANT_LABEL = {"NW": "Cuarto 1 (NW)", "NE": "Cuarto 2 (NE)", "SW": "Cuarto 3 (SW)", "SE": "Cuarto 4 (SE)"}


def _normalizar(s):
    return "".join(
        c for c in unicodedata.normalize("NFD", s or "")
        if unicodedata.category(c) != "Mn"
    ).lower()


def detectar_indice(info, nombre_o_indice):
    team_names = info.get("TeamNames") or []
    if nombre_o_indice is not None:
        try:
            idx = int(nombre_o_indice)
            nombre = team_names[idx] if idx < len(team_names) else f"indice {idx}"
            return idx, nombre
        except (ValueError, TypeError):
            pass
    hint = _normalizar(nombre_o_indice or "RamónLópez")
    for i, name in enumerate(team_names):
        name_norm = _normalizar(name)
        if hint in name_norm or name_norm in hint:
            return i, name
    print("AVISO: no pude confirmar el indice por nombre de equipo -- asumiendo 0.")
    return 0, None


def cuadrante_de(x, y, size):
    half = size // 2
    if x < half and y < half:
        return "NW"
    if x >= half and y < half:
        return "NE"
    if x < half and y >= half:
        return "SW"
    return "SE"


def main():
    if len(sys.argv) < 2:
        print("Uso: python cost_center_by_quadrant.py archivo.json [nombre_o_indice]")
        sys.exit(1)

    path = sys.argv[1]
    arg2 = sys.argv[2] if len(sys.argv) > 2 else None

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    info = data.get("info", {}) if isinstance(data, dict) else {}
    steps = data.get("steps", []) if isinstance(data, dict) else data
    team_names = info.get("TeamNames", ["Player 0", "Player 1"])

    idx, nombre = detectar_indice(info, arg2)
    print(f"Jugador: indice {idx} = '{nombre or (team_names[idx] if idx < len(team_names) else idx)}'")
    print(f"Archivo: {path}\n")
  
    ingreso_directo = defaultdict(float)
    costo_directo = defaultdict(float)
    costo_tierra = defaultdict(float)
    actividad_por_cuadrante_dia = defaultdict(lambda: defaultdict(int))  # day -> {quad: n_acciones}
    gasto_conocido_dia = defaultdict(float)
    ingreso_dia = defaultdict(float)
    money_por_dia = {}
    cuadrantes_comprados = 0
    board_size = None

    for step in steps:
        if not isinstance(step, list) or len(step) <= idx:
            continue
        agente = step[idx]
        obs = agente.get("observation", {})
        action = agente.get("action", {})
        if not isinstance(action, dict):
            continue
        farms = obs.get("farms", [])
        if len(farms) <= idx:
            continue

        day = obs.get("day")
        farm = farms[idx]
        tiles = farm.get("tiles", [])
        if board_size is None:
            board_size = len(tiles)
        precios = obs.get("market", {}).get("prices", {})
        money = farm.get("money")
        if day not in money_por_dia:
            money_por_dia[day] = {"inicio": money, "fin": money}
        money_por_dia[day]["fin"] = money

        farmer_pos = farm.get("farmer", [None, None])
        hands_pos = farm.get("hands", [])
        posiciones_unidades = [farmer_pos] + list(hands_pos)

        acciones_unidades = [action.get("farmer")] + list(action.get("hands", []))

        for pos, act in zip(posiciones_unidades, acciones_unidades):
            if not act or pos is None or pos[0] is None:
                continue
            x, y = pos
            quad = cuadrante_de(x, y, board_size)

            # cualquier accion de unidad cuenta como "actividad" para el
            # prorrateo de mano de obra de ese dia y cuadrante
            actividad_por_cuadrante_dia[day][quad] += 1

            verbo = act[0]
            if verbo == "PLANT" and len(act) > 1:
                crop = act[1]
                costo_directo[quad] += SEED_COST.get(crop, 0)
            elif verbo == "HARVEST":
                # AJUSTE (bug real encontrado probando este mismo script):
                # el juego NO tiene un verbo separado "HARVEST_ANIMAL" --
                # HARVEST se usa tanto para cultivos como para animales, y
                # se distingue mirando que hay en la tile (crop vs animal),
                # no el verbo de la accion. La version anterior de este
                # script asumia un verbo que no existe, asi que todo el
                # ingreso de animales (MILK/WOOL/EGG) quedaba sin contar.
                tile = tiles[y][x] if y < len(tiles) and x < len(tiles[y]) else None
                if isinstance(tile, dict):
                    if tile.get("kind") == "PLANT" and tile.get("crop"):
                        crop = tile["crop"]
                        qty = MAX_YIELD.get(crop, 1)
                        precio = precios.get(crop, 0)
                        ingreso_directo[quad] += precio * qty
                    elif tile.get("animal"):
                        especie = tile["animal"]
                        producto = ANIMAL_PRODUCT.get(especie)
                        qty = MAX_YIELD.get(especie, 1)
                        precio = precios.get(producto, 0)
                        ingreso_directo[quad] += precio * qty
            elif verbo == "PLACE" and len(act) > 1:
                especie = act[1]
                costo_directo[quad] += ANIMAL_COST.get(especie, 0)

        for order in (action.get("market") or []):
            if not order:
                continue
            op = order[0]
            if op == "SELL":
                ingreso_dia[day] += precios.get(order[1], 0) * order[2]
            elif op == "BUY_SEED":
                gasto_conocido_dia[day] += SEED_COST.get(order[1], 0) * order[2]
            elif op == "BUY_ANIMAL":
                gasto_conocido_dia[day] += ANIMAL_COST.get(order[1], 0) * order[2]
            elif op == "BUY_PRODUCT":
                gasto_conocido_dia[day] += precios.get(order[1], 0) * order[2]
            elif op == "BUY_LAND":
                unlocked = farm.get("unlocked_quadrants", [])
                orden_quad = ["NE", "SW", "SE"]
                if cuadrantes_comprados < len(LAND_COSTS_IN_ORDER):
                    costo = LAND_COSTS_IN_ORDER[cuadrantes_comprados]
                    quad_comprado = orden_quad[cuadrantes_comprados]
                    costo_tierra[quad_comprado] += costo
                    gasto_conocido_dia[day] += costo
                    cuadrantes_comprados += 1

    # --- prorratear mano de obra por dia segun actividad de cada cuadrante ---
    costo_mano_obra = defaultdict(float)
    dias = sorted(money_por_dia.keys())
    for day in dias:
        m = money_por_dia[day]
        cambio_real = (m["fin"] - m["inicio"]) if (m["inicio"] is not None and m["fin"] is not None) else 0
        costo_hire_dia = max(0.0, ingreso_dia.get(day, 0) - gasto_conocido_dia.get(day, 0) - cambio_real)
        actividad = actividad_por_cuadrante_dia.get(day, {})
        total_actividad = sum(actividad.values())
        if total_actividad > 0 and costo_hire_dia > 0:
            for quad, n in actividad.items():
                costo_mano_obra[quad] += costo_hire_dia * (n / total_actividad)

    # --- reporte ---
    quads = ["NW", "NE", "SW", "SE"]
    print("=" * 90)
    print("COSTEO POR CENTRO DE COSTOS (CUADRANTE)".center(90))
    print("=" * 90)
    print(f"{'':20s}{'Ingreso directo':>18s}{'Costo directo':>16s}{'Costo tierra':>14s}{'Mano obra (prorr.)':>20s}{'NETO':>12s}")
    total_neto_general = 0
    for q in quads:
        ing = ingreso_directo.get(q, 0)
        cst = costo_directo.get(q, 0)
        tierra = costo_tierra.get(q, 0)
        mano = costo_mano_obra.get(q, 0)
        neto = ing - cst - tierra - mano
        total_neto_general += neto
        print(f"{QUADRANT_LABEL[q]:20s}{ing:18,.0f}{cst:16,.0f}{tierra:14,.0f}{mano:20,.0f}{neto:12,.0f}")
    print("-" * 90)
    print(f"{'TOTAL':20s}{sum(ingreso_directo.values()):18,.0f}{sum(costo_directo.values()):16,.0f}{sum(costo_tierra.values()):14,.0f}{sum(costo_mano_obra.values()):20,.0f}{total_neto_general:12,.0f}")
    print()
    print("NOTA: el ingreso por cosecha es un valor 'de libro' (rendimiento pleno x precio")
    print("del momento), no el monto exacto de cada venta real -- sirve para COMPARAR")
    print("cuadrantes entre si, no como cifra de caja. La mano de obra es prorrateada por")
    print("actividad, una aproximacion razonable, no un costo directo medido.")

    # ===================================================================
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        fig, ax = plt.subplots(figsize=(10, 6))
        x = np.arange(len(quads))
        width = 0.2

        ing_vals = [ingreso_directo.get(q, 0) for q in quads]
        cst_vals = [costo_directo.get(q, 0) for q in quads]
        tierra_vals = [costo_tierra.get(q, 0) for q in quads]
        mano_vals = [costo_mano_obra.get(q, 0) for q in quads]
        neto_vals = [ingreso_directo.get(q, 0) - costo_directo.get(q, 0) - costo_tierra.get(q, 0) - costo_mano_obra.get(q, 0) for q in quads]

        ax.bar(x - 1.5*width, ing_vals, width, label="Ingreso directo", color="#2E7D32")
        ax.bar(x - 0.5*width, cst_vals, width, label="Costo directo (semilla+animal)", color="#C62828")
        ax.bar(x + 0.5*width, tierra_vals, width, label="Costo de tierra", color="#8D6E63")
        ax.bar(x + 1.5*width, mano_vals, width, label="Mano de obra (prorrateada)", color="#F9A825")

        ax.plot(x, neto_vals, marker="o", color="black", linewidth=2, label="Neto")
        ax.axhline(0, color="gray", linewidth=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels([QUADRANT_LABEL[q] for q in quads])
        ax.set_ylabel("$")
        ax.set_title("Costeo por centro de costos (cuadrante)")
        ax.legend()
        ax.grid(alpha=0.3)

        plt.tight_layout()
        out_path = Path(path).with_name("cost_center_by_quadrant.png")
        plt.savefig(out_path, dpi=150)
        print(f"\nGrafico guardado en: {out_path}")
    except ImportError:
        print("\nmatplotlib no esta instalado. Corre: pip install matplotlib")
    except Exception as e:
        print(f"\nError al generar grafico: {e}")


if __name__ == "__main__":
    main()
