"""
compare_early_game_tempo.py
------------------------------
A diferencia de compare_both_players.py (que mira 1 vez por dia), este
script mira TODOS los turnos de los primeros N dias -- para ver el
ritmo EXACTO de cuando cada jugador compra tierra, contrata manos, y
siembra, turno a turno. Sirve para confirmar si los rivales arrancan
mas agresivo desde el principio (turno 1-2) en vez de solo comparar
una foto de un dia completo.

Uso:
    python compare_early_game_tempo.py <archivo>.json 2
    (mira los primeros 2 dias, turno por turno)
"""

import json
import sys
from collections import Counter

filename = sys.argv[1] if len(sys.argv) > 1 else "replay.json"
max_day = int(sys.argv[2]) if len(sys.argv) > 2 else 2

with open(filename, "r", encoding="utf-8") as f:
    replay = json.load(f)

info = replay.get("info", {})
team_names = info.get("TeamNames", ["Player 0", "Player 1"])
print(f"Analizando {filename}")
print(f"Jugadores: {team_names[0]} vs {team_names[1]}\n")

steps = replay["steps"]
prev_state = {0: None, 1: None}

for step in steps:
    obs = step[0].get("observation", {})
    day = obs.get("day")
    hour = obs.get("hour")

    if day is None or day > max_day:
        continue

    farms = obs.get("farms", [])
    if len(farms) < 2:
        continue

    line_parts = [f"Dia {day} Turno {hour:>2}"]
    for idx, farm in enumerate(farms):
        name = team_names[idx] if idx < len(team_names) else f"P{idx}"
        money = farm.get("money", 0)
        quadrants = tuple(sorted(farm.get("unlocked_quadrants", [])))
        n_hands = len(farm.get("hands", []))
        tiles = farm.get("tiles", [])
        n_planted = sum(
            1 for row in tiles for t in row
            if isinstance(t, dict) and t.get("kind") in ("PLANT", "COOP", "PASTURE")
        )

        current = (money, quadrants, n_hands, n_planted)
        changed = current != prev_state[idx]
        prev_state[idx] = current

        marker = " *" if changed else "  "
        line_parts.append(
            f"{marker}[{name}] ${money:>5.0f} tierra={quadrants} manos={n_hands} plantado={n_planted}"
        )

    print("  ".join(line_parts))
