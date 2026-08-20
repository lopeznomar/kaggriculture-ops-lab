"""
compare_both_players.py
-------------------------
A diferencia de track_land_and_crops.py (que solo miraba a nuestro
jugador), este script muestra AMBAS granjas lado a lado, dia por dia:
tierra, dinero, y cultivos de cada uno. Sirve para comparar contra un
RIVAL REAL (de un episodio real de la competencia, no contra random o
starter) y ver que esta haciendo distinto -- mas tierra mas rapido, mas
animales, otro mix de cultivos, etc.

Uso:
    python compare_both_players.py 90804593.json
    (usa el nombre del archivo que te haya dejado kaggle competitions replay)
"""

import json
import sys
from collections import Counter

filename = sys.argv[1] if len(sys.argv) > 1 else "replay.json"

with open(filename, "r", encoding="utf-8") as f:
    replay = json.load(f)

info = replay.get("info", {})
team_names = info.get("TeamNames", ["Player 0", "Player 1"])
print(f"Analizando {filename}")
print(f"Jugadores: {team_names[0]} (nosotros, asumido) vs {team_names[1]}\n")

steps = replay["steps"]
seen_days = set()

for step in steps:
    obs = step[0].get("observation", {})
    day = obs.get("day")
    hour = obs.get("hour")

    if day is None or hour != 0 or day in seen_days:
        continue
    seen_days.add(day)

    farms = obs.get("farms", [])
    if len(farms) < 2:
        continue

    print(f"--- DIA {day} ---")
    for idx, farm in enumerate(farms):
        name = team_names[idx] if idx < len(team_names) else f"Player {idx}"
        money = farm.get("money")
        quadrants = sorted(farm.get("unlocked_quadrants", []))
        tiles = farm.get("tiles", [])
        crop_counts = Counter()
        animal_counts = Counter()
        for row in tiles:
            for tile in row:
                if isinstance(tile, dict):
                    if tile.get("kind") == "PLANT":
                        crop_counts[tile.get("crop")] += 1
                    elif tile.get("kind") in ("COOP", "PASTURE") and tile.get("animal"):
                        animal_counts[tile.get("animal")] += 1
        crops_str = ", ".join(f"{c}:{n}" for c, n in sorted(crop_counts.items())) or "sin cultivos"
        animals_str = ", ".join(f"{a}:{n}" for a, n in sorted(animal_counts.items())) or "sin animales"
        print(f"  [{name}] ${money:>6.0f}  tierra={quadrants}  cultivos: {crops_str}  animales: {animals_str}")
    print()
