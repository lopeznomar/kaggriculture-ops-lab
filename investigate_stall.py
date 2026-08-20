"""
investigate_stall.py
----------------------
Rastrea turno a turno TODAS nuestras unidades (farmer + manos): su
posicion, la tile donde estan, su inventario, y la accion que tomaron.
A diferencia de investigate_harvest.py (que asumia que somos el indice
0), este script identifica nuestro lado por NOMBRE DE EQUIPO, para no
equivocarnos de lado cuando el orden cambia entre partidas.

Uso:
    python investigate_stall.py <archivo>.json RamonLopez 1 2
    (nuestro nombre de equipo, dia inicio, dia fin)
"""

import json
import sys

filename = sys.argv[1] if len(sys.argv) > 1 else "replay.json"
my_name_hint = sys.argv[2] if len(sys.argv) > 2 else "RamónLópez"
day_start = int(sys.argv[3]) if len(sys.argv) > 3 else 0
day_end = int(sys.argv[4]) if len(sys.argv) > 4 else 2

with open(filename, "r", encoding="utf-8") as f:
    replay = json.load(f)

info = replay.get("info", {})
team_names = info.get("TeamNames", ["Player 0", "Player 1"])

my_index = None
for i, name in enumerate(team_names):
    if my_name_hint.lower() in name.lower() or name.lower() in my_name_hint.lower():
        my_index = i
        break
if my_index is None:
    print(f"No pude identificar cual jugador sos vos entre {team_names}.")
    print("Ajusta el segundo argumento con parte de tu nombre de equipo.")
    sys.exit(1)

print(f"Jugadores: {team_names}")
print(f"Vos sos el indice {my_index} ({team_names[my_index]})\n")

steps = replay["steps"]
count = 0
for step in steps:
    obs = step[0].get("observation", {})
    action = step[0].get("action", {})
    day = obs.get("day")
    hour = obs.get("hour")

    if day is None or day < day_start or day > day_end:
        continue

    farms = obs.get("farms", [])
    if len(farms) <= my_index:
        continue
    farm = farms[my_index]
    fx, fy = farm.get("farmer", [None, None])
    hands_pos = farm.get("hands", [])
    tiles = farm.get("tiles", [])
    money = farm.get("money")

    private = obs.get("private", {})
    inventories = private.get("inventories", [{}])
    shed = private.get("shed", {})
    seeds = private.get("seeds", {})

    farmer_action = action.get("farmer", [None]) if isinstance(action, dict) else [None]
    hands_actions = action.get("hands", []) if isinstance(action, dict) else []

    count += 1
    if count > 80:
        print("... (cortado a 80 turnos, ajusta el rango de dias para ver menos)")
        break

    farmer_tile = tiles[fy][fx] if fy is not None and fy < len(tiles) and fx < len(tiles[fy]) else None
    farmer_inv = inventories[0] if inventories else {}

    print(f"Dia {day} Turno {hour}: $ {money}  seeds={seeds}  shed={shed}")
    print(f"  FARMER pos=({fx},{fy}) accion={farmer_action} inv={farmer_inv}")
    print(f"    tile: {farmer_tile}")

    for i, hpos in enumerate(hands_pos):
        hx, hy = hpos
        h_tile = tiles[hy][hx] if hy < len(tiles) and hx < len(tiles[hy]) else None
        h_action = hands_actions[i] if i < len(hands_actions) else None
        h_inv = inventories[i + 1] if i + 1 < len(inventories) else {}
        print(f"  MANO{i} pos=({hx},{hy}) accion={h_action} inv={h_inv}")
        print(f"    tile: {h_tile}")
    print()
