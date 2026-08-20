"""
analyze_replay.py
------------------
Lee un replay (por defecto replay.json, o el que le pases como
argumento) y muestra:
  - Curva de dinero por dia (para ver si crece parejo o hay tramos muertos)
  - Distribucion de acciones del farmer (para ver si se queda "PASS"-eando
    o moviendose sin sentido en vez de trabajar)
  - Cuantos turnos tuvo semillas/dinero pero no planto nada

Uso:
    python analyze_replay.py                # lee replay.json
    python analyze_replay.py replay_5.json   # lee un replay especifico
"""

import json
import sys
from collections import Counter

filename = sys.argv[1] if len(sys.argv) > 1 else "replay.json"
print(f"Analizando: {filename}\n")

with open(filename, "r", encoding="utf-8") as f:
    replay = json.load(f)

steps = replay["steps"]
print(f"Total de turnos en el replay: {len(steps)}")

# --- 1. Curva de dinero por dia (un punto cada 24 turnos = 1 dia) ---
print("\n" + "=" * 50)
print("DINERO POR DIA (Player 0 = nuestro agente)")
print("=" * 50)
seen_days = set()
for step in steps:
    obs = step[0].get("observation", {})
    day = obs.get("day")
    farms = obs.get("farms", [])
    if day is not None and day not in seen_days and farms:
        seen_days.add(day)
        money = farms[0].get("money", "?")
        print(f"  Dia {day:>2}: ${money}")

# --- 2. Distribucion de acciones que tomo el farmer ---
print("\n" + "=" * 50)
print("DISTRIBUCION DE ACCIONES DEL FARMER (Player 0)")
print("=" * 50)
action_counter = Counter()
for step in steps:
    action = step[0].get("action")
    if isinstance(action, dict):
        farmer_action = action.get("farmer", [None])
        action_counter[farmer_action[0]] += 1

total = sum(action_counter.values())
for action, count in action_counter.most_common():
    pct = 100 * count / total if total else 0
    print(f"  {action:<15} {count:>4} veces  ({pct:.1f}%)")

# --- 3. Ultimo estado: cuanta tierra/animales/dinero terminamos teniendo ---
print("\n" + "=" * 50)
print("ESTADO FINAL")
print("=" * 50)
last_obs = steps[-1][0].get("observation", {})
last_farm = last_obs.get("farms", [{}])[0]
print(f"  Dinero final: ${last_farm.get('money')}")
print(f"  Quadrantes desbloqueados: {last_farm.get('unlocked_quadrants')}")
print(f"  Manos contratadas hoy: {last_farm.get('hires_today')}")
