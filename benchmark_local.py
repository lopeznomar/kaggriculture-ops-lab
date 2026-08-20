"""
benchmark_local.py
-------------------
Corre N partidas de main.py vs un oponente y reporta el promedio, minimo,
maximo y cada resultado individual. Una sola partida tiene bastante
ruido (aleatoriedad del rival, spawn de weeds, etc.) -- esto da una
medida mas confiable para saber si un cambio realmente mejora las cosas.

Guarda el replay de CADA partida (replay_1.json, replay_2.json, ...)
para poder investigar despues que paso en la mejor o peor corrida.

Uso:
    python benchmark_local.py                  # 5 partidas contra random
    python benchmark_local.py 10                # 10 partidas contra random
    python benchmark_local.py 5 starter          # 5 partidas contra starter
"""

import sys
import json
from kaggle_environments import make

N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
OPPONENT = sys.argv[2] if len(sys.argv) > 2 else "random"

print(f"Corriendo {N} partidas de main.py vs {OPPONENT}...\n")

rewards = []
for i in range(N):
    env = make("kaggriculture", configuration={"episodeSteps": 720}, debug=False)
    env.run(["main.py", OPPONENT])
    final = env.steps[-1]
    r0 = final[0].reward or 0
    r1 = final[1].reward or 0
    rewards.append(r0)
    print(f"  Partida {i+1}/{N}: nuestro agente={r0:.0f}  |  {OPPONENT}={r1:.0f}")

    with open(f"replay_{i+1}.json", "w", encoding="utf-8") as f:
        json.dump(env.toJSON(), f)

print("\n" + "=" * 50)
print("RESUMEN")
print("=" * 50)
print(f"  Promedio: {sum(rewards)/len(rewards):.1f}")
print(f"  Minimo:   {min(rewards):.0f}")
print(f"  Maximo:   {max(rewards):.0f}")
print(f"  Todos:    {[f'{r:.0f}' for r in rewards]}")
print(f"\nReplays guardados: replay_1.json ... replay_{N}.json")
print("Usa analyze_replay.py apuntando al que quieras investigar (cambia el nombre del archivo que lee).")

