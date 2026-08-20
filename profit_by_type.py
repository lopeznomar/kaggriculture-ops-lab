"""
profit_by_type.py
-------------------
Analiza un replay completo y muestra cuanto INGRESO genero cada tipo
de cultivo y cada tipo de animal (por venta de su producto), cuanto
COSTO tuvo (semilla/compra), y la GANANCIA NETA de cada uno.

AJUSTE (bug real encontrado, misma clase que el de investigate_spike.py):
antes esto usaba "step_data = step[0]" FIJO para sacar observation/action,
sin importar cual fuera my_index. my_index solo se usaba para el titulo
del grafico y para el chequeo de "len(farms) <= my_index" -- pero las
ORDENES DE MERCADO (base de todo el calculo de ingreso/costo) siempre
salian del jugador 0, aunque nosotros fueramos el indice 1. Resultado:
en cualquier partida donde no fueramos el indice 0, este script mostraba
la economia DEL RIVAL, con nuestro nombre puesto en el titulo por error
(confirmado con partida real 93825311, donde el grafico resultante no
coincidia para nada con el calculo directo del replay). Ahora usa
step[my_index] siempre.

Genera una tabla en texto y un grafico de barras (profit_by_type.png).

Uso:
    python profit_by_type.py <archivo>.json <nombre_jugador>
    Ejemplo: python profit_by_type.py replay.json "RamónLópez"
"""

import json
import sys
import unicodedata


def _normalizar(s):
    """Saca acentos/mayusculas para comparar 'RamonLopez' con
    'RamónLópez' sin que la tilde rompa la coincidencia."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s or "")
        if unicodedata.category(c) != "Mn"
    ).lower()


filename = sys.argv[1] if len(sys.argv) > 1 else "replay.json"
my_name_hint = sys.argv[2] if len(sys.argv) > 2 else "RamónLópez"

# Costos conocidos (de la spec del juego)
SEED_COST = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50, "STRAWBERRY": 100, "MELON": 80}
ANIMAL_COST = {"GOOSE": 300, "COW": 400, "SHEEP": 500}
ANIMAL_PRODUCT = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}
PRODUCT_TO_ANIMAL = {v: k for k, v in ANIMAL_PRODUCT.items()}

with open(filename, "r", encoding="utf-8") as f:
    data = json.load(f)

# --- DETECTAR FORMATO DEL REPLAY ---
if isinstance(data, dict):
    info = data.get("info", {})
    steps = data.get("steps", [])
elif isinstance(data, list):
    info = {}
    steps = data
else:
    print("Formato de replay no reconocido.")
    sys.exit(1)

team_names = info.get("TeamNames", ["Player 0", "Player 1"])

my_index = None
hint_norm = _normalizar(my_name_hint)
for i, name in enumerate(team_names):
    name_norm = _normalizar(name)
    if hint_norm in name_norm or name_norm in hint_norm:
        my_index = i
        break

if my_index is None:
    try:
        my_index = int(my_name_hint)
        print(f"Usando indice {my_index} como jugador")
    except ValueError:
        print(f"AVISO: no pude identificar cual jugador sos vos entre {team_names}.")
        print("Asumiendo indice 0 -- VERIFICA que sea correcto.")
        my_index = 0

print(f"Jugadores: {team_names} -- vos sos el indice {my_index} ({team_names[my_index] if len(team_names) > my_index else 'Unknown'})\n")
print(f"Archivo Analizado: {filename}")
revenue = {}   # producto -> ingreso total por venta
cost = {}      # producto/animal -> costo total (semilla o compra de animal)
overhead_cost = {"HIRE": 0, "BUY_LAND": 0, "FERTILIZER": 0, "WHEAT_FEED": 0}

for step in steps:
    # AJUSTE: leer siempre step[my_index], NO step[0] fijo -- cada
    # jugador tiene su propia observation/action en su propio indice.
    if isinstance(step, list) and len(step) > my_index:
        step_data = step[my_index]
    elif isinstance(step, list) and len(step) > 0:
        step_data = step[0]
    else:
        step_data = step

    obs = step_data.get("observation", {})
    action = step_data.get("action", {})
    if not isinstance(action, dict):
        continue

    farms = obs.get("farms", [])
    if len(farms) <= my_index:
        continue

    prices = obs.get("market", {}).get("prices", {})
    market_orders = action.get("market", []) or []

    for order in market_orders:
        if not order:
            continue
        op = order[0]

        if op == "SELL":
            product, qty = order[1], order[2]
            price = prices.get(product, 0)
            revenue[product] = revenue.get(product, 0) + price * qty

        elif op == "BUY_SEED":
            crop, qty = order[1], order[2]
            cost[crop] = cost.get(crop, 0) + SEED_COST.get(crop, 0) * qty

        elif op == "BUY_ANIMAL":
            animal, qty = order[1], order[2]
            cost[animal] = cost.get(animal, 0) + ANIMAL_COST.get(animal, 0) * qty

        elif op == "BUY_PRODUCT":
            item, qty = order[1], order[2]
            price = prices.get(item, 0)
            if item == "WHEAT":
                overhead_cost["WHEAT_FEED"] += price * qty
            elif item == "FERTILIZER":
                overhead_cost["FERTILIZER"] += price * qty

        elif op == "HIRE":
            pass

        elif op == "BUY_LAND":
            pass

# --- Armar la tabla de cultivos ---
print("=" * 70)
print("CULTIVOS")
print("=" * 70)
print(f"{'Cultivo':<14}{'Ingreso':>12}{'Costo semilla':>16}{'Ganancia neta':>16}")
crop_results = []
for crop in SEED_COST:
    rev = revenue.get(crop, 0)
    cst = cost.get(crop, 0)
    net = rev - cst
    crop_results.append((crop, rev, cst, net))

for crop, rev, cst, net in sorted(crop_results, key=lambda x: -x[3]):
    print(f"{crop:<14}{rev:>12.0f}{cst:>16.0f}{net:>16.0f}")

# --- Armar la tabla de animales ---
print()
print("=" * 70)
print("ANIMALES")
print("=" * 70)
print(f"{'Animal':<14}{'Producto':<10}{'Ingreso':>12}{'Costo compra':>14}{'Ganancia neta':>16}")
animal_results = []
for animal, product in ANIMAL_PRODUCT.items():
    rev = revenue.get(product, 0)
    cst = cost.get(animal, 0)
    net = rev - cst
    animal_results.append((animal, product, rev, cst, net))

for animal, product, rev, cst, net in sorted(animal_results, key=lambda x: -x[4]):
    print(f"{animal:<14}{product:<10}{rev:>12.0f}{cst:>14.0f}{net:>16.0f}")

# --- Costos generales ---
print()
print("=" * 70)
print("COSTOS GENERALES (no atribuibles a un cultivo/animal en particular)")
print("=" * 70)
print(f"  Trigo comprado para alimentar animales: ${overhead_cost['WHEAT_FEED']:.0f}")
print(f"  Fertilizante comprado: ${overhead_cost['FERTILIZER']:.0f}")

# --- Totales ---
print()
print("=" * 70)
print("RESUMEN TOTAL")
print("=" * 70)
total_revenue = sum(revenue.values())
total_cost = sum(cost.values()) + sum(overhead_cost.values())
print(f"  Ingresos totales: ${total_revenue:.0f}")
print(f"  Costos totales: ${total_cost:.0f}")
print(f"  Ganancia neta: ${total_revenue - total_cost:.0f}")

# --- Grafico de barras ---
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [c for c, _, _, _ in crop_results] + [a for a, _, _, _, _ in animal_results]
    nets = [n for _, _, _, n in crop_results] + [n for _, _, _, _, n in animal_results]
    colors = ["#4CAF50" if n >= 0 else "#E53935" for n in nets]

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(labels, nets, color=colors)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylabel("Ganancia neta ($)")
    ax.set_title(f"Ganancia neta por tipo de cultivo/animal -- Archivo Analizado: {filename} -- {team_names[my_index] if len(team_names) > my_index else 'Jugador ' + str(my_index)}")
    ax.bar_label(bars, fmt="%.0f", padding=3)
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig("profit_by_type.png", dpi=150)
    print("\nGrafico guardado en: profit_by_type.png")
except ImportError:
    print("\nmatplotlib no esta instalado. Corre: pip install matplotlib")
except Exception as e:
    print(f"\nError al generar grafico: {e}")
