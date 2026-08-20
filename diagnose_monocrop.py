"""
diagnose_monocrop.py
---------------------
Para un rango de dias de un replay, muestra:
  - Los precios de mercado de TODOS los cultivos/animales en ese momento
  - El puntaje de rentabilidad (crop_score) que main.py le habria dado
    a cada uno con ese precio
  - Que crop_plan (asignacion de tiles) hubiera calculado el optimizador

Esto sirve para confirmar si el agente se quedo pegado en un solo
cultivo porque los demas de verdad tienen rentabilidad negativa al
precio de ese momento, o si hay otro problema.

Requiere tener main.py en la misma carpeta (importa sus funciones).

Uso:
    python diagnose_monocrop.py replay_1.json 22 26
"""

import json
import sys

filename = sys.argv[1] if len(sys.argv) > 1 else "replay.json"
day_start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
day_end = int(sys.argv[3]) if len(sys.argv) > 3 else 29

sys.path.insert(0, ".")
from main import CROP_DATA, crop_score, ranked_crops, optimizar_cultivos_io, GameState, ANIMAL_DATA, animal_score, ranked_animals, tiene_animal_vivo

with open(filename, "r", encoding="utf-8") as f:
    replay = json.load(f)

steps = replay["steps"]
print(f"Analizando {filename}, dias {day_start} a {day_end}\n")

last_day_hour_shown = None
for step in steps:
    obs = step[0].get("observation", {})
    day = obs.get("day")
    hour = obs.get("hour")

    if day is None or day < day_start or day > day_end:
        continue

    # Solo mostrar una vez por dia (turno 0) para no saturar la salida
    if hour != 0:
        continue

    farms = obs.get("farms", [])
    if not farms:
        continue

    prices = obs.get("market", {}).get("prices", {})
    money = farms[0].get("money")

    print("=" * 60)
    print(f"DIA {day}  (dinero: ${money})")
    print("=" * 60)
    print("Precios de mercado y rentabilidad calculada por cultivo:")
    for crop in CROP_DATA:
        price = prices.get(crop, CROP_DATA[crop]["base_price"])
        score = crop_score(crop, price)
        marca = "  <-- rentable" if score > 0 else "  (excluido, score <= 0)"
        print(f"    {crop:<12} precio=${price:<6} score={score:>8.2f}{marca}")

    print("\nPrecios y rentabilidad por animal:")
    for animal in ANIMAL_DATA:
        product = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}[animal]
        price = prices.get(product, ANIMAL_DATA[animal]["base_price"])
        score = animal_score(animal, price)
        marca = "  <-- rentable" if score > 0 else "  (excluido, score <= 0)"
        print(f"    {animal:<12} precio {product}=${price:<6} score={score:>8.2f}{marca}")

    try:
        state = GameState(obs)
        allocation = optimizar_cultivos_io(state.get_game_phase(), state)
        print(f"\ncrop_plan calculado por el optimizador: {allocation}")
        print(f"tiene_animal_vivo: {tiene_animal_vivo(state)}")
    except Exception as e:
        print(f"\n(no se pudo recalcular el crop_plan: {e})")

    print()
