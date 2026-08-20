"""
track_land_and_crops.py
-------------------------
Recorre un replay completo y muestra, para cada dia:
  - Que quadrantes de tierra estan desbloqueados ese dia (y cuando
    cambia, para ver EXACTAMENTE que dia se compro cada uno)
  - Cuantas tiles hay de cada cultivo en el tablero ese dia (para ver
    si MELON/STRAWBERRY realmente escasean, y en que momento)

Uso:
    python track_land_and_crops.py replay.json
"""

import json
import sys
from collections import Counter

filename = sys.argv[1] if len(sys.argv) > 1 else "replay.json"

with open(filename, "r", encoding="utf-8") as f:
    replay = json.load(f)

steps = replay["steps"]
print(f"Analizando {filename}\n")

seen_days = set()
prev_quadrants = None

for step in steps:
    obs = step[0].get("observation", {})
    day = obs.get("day")
    hour = obs.get("hour")

    if day is None or hour != 0 or day in seen_days:
        continue
    seen_days.add(day)

    farms = obs.get("farms", [])
    if not farms:
        continue
    farm = farms[0]
    quadrants = tuple(sorted(farm.get("unlocked_quadrants", [])))
    money = farm.get("money")

    tiles = farm.get("tiles", [])
    crop_counts = Counter()
    for row in tiles:
        for tile in row:
            if isinstance(tile, dict) and tile.get("kind") == "PLANT":
                crop_counts[tile.get("crop")] += 1

    land_change = ""
    if quadrants != prev_quadrants:
        land_change = f"  <<< CAMBIO DE TIERRA: {prev_quadrants} -> {quadrants}"
        prev_quadrants = quadrants

    crops_str = ", ".join(f"{c}:{n}" for c, n in sorted(crop_counts.items())) or "(ninguno plantado)"
    print(f"Dia {day:>2} (${money:>6.0f}) tierra={quadrants}{land_change}")
    print(f"         cultivos en tablero: {crops_str}")
