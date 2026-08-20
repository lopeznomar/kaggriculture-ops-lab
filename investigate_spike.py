"""
investigate_spike.py
---------------------
Mira en detalle un rango de dias de un replay: que ordenes de venta se
mandaron, cuanto habia en el shed antes de vender, y a que precio.
Sirve para entender un salto de dinero puntual.

AJUSTE (bug real encontrado en la version anterior): este script asumia
"farm = farms[0]" fijo, sin importar el orden real de jugadores en esa
partida especifica. Ya confirmamos con datos reales (partida 93738139)
que el indice de RamonLopez CAMBIA de partida en partida (a veces es 0,
a veces 1) -- asi que en cualquier partida donde no fueramos el indice 0,
este script terminaba mostrando el dinero/shed/ventas DEL RIVAL,
etiquetado como si fueran nuestros. Ahora detecta el indice correcto por
nombre de equipo, igual que ya hacia investigate_stall.py, y lo imprime
bien claro al arrancar para que sea imposible confundirse.

Uso:
    python investigate_spike.py <archivo>.json RamonLopez 22 25
    (nuestro nombre de equipo, dia inicio, dia fin)
"""

import json
import sys
import unicodedata


def _normalizar(s):
    """Saca acentos/mayusculas para poder comparar 'RamonLopez' con
    'RamónLópez' sin que la tilde rompa la coincidencia."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s or "")
        if unicodedata.category(c) != "Mn"
    ).lower()


filename = sys.argv[1] if len(sys.argv) > 1 else "replay.json"
my_name_hint = sys.argv[2] if len(sys.argv) > 2 else "RamónLópez"
day_start = int(sys.argv[3]) if len(sys.argv) > 3 else 0
day_end = int(sys.argv[4]) if len(sys.argv) > 4 else 29

with open(filename, "r", encoding="utf-8") as f:
    replay = json.load(f)

info = replay.get("info", {})
team_names = info.get("TeamNames", ["Player 0", "Player 1"])

my_index = None
hint_norm = _normalizar(my_name_hint)
for i, name in enumerate(team_names):
    name_norm = _normalizar(name)
    if hint_norm in name_norm or name_norm in hint_norm:
        my_index = i
        break
if my_index is None:
    print(f"No pude identificar cual jugador sos vos entre {team_names}.")
    print("Ajusta el segundo argumento con parte de tu nombre de equipo.")
    sys.exit(1)

print(f"Jugadores: {team_names}")
print(f"Vos sos el indice {my_index} ({team_names[my_index]}) -- todo lo que sigue es TU lado.\n")

steps = replay["steps"]
print(f"Analizando {filename}, dias {day_start} a {day_end}\n")

prev_money = None
for step in steps:
    # AJUSTE: leer siempre desde step[my_index], no step[0] fijo -- la
    # observacion/accion de CADA jugador vive en su propio indice del
    # step, no solo en el primero.
    obs = step[my_index].get("observation", {})
    action = step[my_index].get("action", {})
    day = obs.get("day")
    hour = obs.get("hour")

    if day is None or day < day_start or day > day_end:
        continue

    farms = obs.get("farms", [])
    if len(farms) <= my_index:
        continue
    farm = farms[my_index]
    money = farm.get("money")
    shed = obs.get("private", {}).get("shed", {}) if "private" in obs else None
    prices = obs.get("market", {}).get("prices", {})

    # Mostrar cualquier orden de venta (SELL) que se haya mandado este turno
    market_orders = action.get("market", []) if isinstance(action, dict) else []
    sell_orders = [o for o in market_orders if o and o[0] == "SELL"]

    if sell_orders:
        print(f"Dia {day} Turno {hour}: dinero=${money}")
        for o in sell_orders:
            product = o[1]
            qty = o[2]
            price = prices.get(product, "?")
            disponible = shed.get(product) if shed else "?"
            nota = ""
            if isinstance(disponible, (int, float)) and disponible < qty:
                # AJUSTE: aclarar que "shed" es el valor de ANTES de que
                # se ejecute este turno (incluida la cosecha del propio
                # turno) -- si la orden pide mas de lo que el shed
                # mostraba al INICIO del turno, no es necesariamente un
                # bug: puede ser que la cosecha de este mismo turno haya
                # sumado unidades nuevas antes de que se ejecute la venta.
                nota = "  <-- shed(inicio de turno) < cantidad vendida: revisar si hubo cosecha este mismo turno"
            print(f"    SELL {product} x{qty} @ ${price}/u  (shed al inicio del turno tenia {disponible}){nota}")

    if prev_money is not None and money is not None and abs(money - prev_money) > 200:
        print(f"  >>> SALTO GRANDE: dia {day} turno {hour}: ${prev_money} -> ${money} (delta {money-prev_money:+.0f})")

    prev_money = money
