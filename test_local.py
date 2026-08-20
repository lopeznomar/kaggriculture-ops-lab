"""
test_local.py
--------------
Corre una partida de Kaggriculture localmente (fuera de un notebook)
y guarda los resultados: reward final, y un HTML para ver la partida
en el navegador (env.render(mode="ipython") NO funciona fuera de
Jupyter -- por eso usamos mode="html" aqui).

Uso (en tu venv activado):
    python test_local.py
"""

import json
from kaggle_environments import make

print("Cargando el entorno...")
env = make("kaggriculture", configuration={"episodeSteps": 720}, debug=True)

print("Corriendo la partida: main.py vs random ...")
env.run(["main.py", "random"])

print("\n" + "=" * 50)
print("RESULTADO FINAL")
print("=" * 50)
final = env.steps[-1]
for i, s in enumerate(final):
    print(f"Player {i}: reward={s.reward}, status={s.status}")

# Guardar el replay como JSON (por si quieres analizarlo despues con pandas, etc.)
with open("replay.json", "w", encoding="utf-8") as f:
    json.dump(env.toJSON(), f)
print("\nReplay guardado en: replay.json")

# Guardar una visualizacion HTML que se abre en el navegador (doble click)
html = env.render(mode="html")
with open("replay.html", "w", encoding="utf-8") as f:
    f.write(html)
print("Visualizacion guardada en: replay.html  (abrela con doble click)")
