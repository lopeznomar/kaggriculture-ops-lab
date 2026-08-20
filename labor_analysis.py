"""
labor_analysis.py
--------------------
Analiza, turno a turno, el USO y COSTO REAL de la mano de obra, el
tamano de tierra, y como se correlacionan con la acumulacion de
maleza (WEED) y tiles vacias -- para responder concretamente: estamos
comprando mas tierra de la que podemos mantener con la mano de obra
que tenemos?

Por que el costo de HIRE se calcula como RESIDUO (no con la formula
Fibonacci directa): confirmado con partidas reales que el motor
rechaza en silencio ordenes HIRE de mas alla de cierto tope diario
(delta de dinero = $0 en esos casos) -- la formula sola sobreestima el
gasto real. Este script usa el mismo metodo ya validado en
profit_loss_statement.py: el costo de contratacion se infiere del
cambio real de dinero cada dia, descontando el resto de gastos
conocidos ese dia.

Uso:
    python labor_analysis.py <archivo>.json [nombre_o_indice]

Genera:
    - Tabla en consola: por dia, manos activas, costo de contratacion,
      tiles totales, tiles ocupadas realmente, WEED, vacias, y el
      ratio tiles-por-mano (cuanta tierra le toca cubrir a cada mano)
    - labor_analysis.png: 3 graficos -- manos vs tierra, WEED en el
      tiempo, y costo diario de contratacion
"""
import json
import sys
import unicodedata
from pathlib import Path

SEED_COST = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50, "STRAWBERRY": 100, "MELON": 80}
ANIMAL_COST = {"GOOSE": 300, "COW": 400, "SHEEP": 500}


def _normalizar(s):
    return "".join(
        c for c in unicodedata.normalize("NFD", s or "")
        if unicodedata.category(c) != "Mn"
    ).lower()


def detectar_indice(info, nombre_o_indice):
    team_names = info.get("TeamNames") or []
    if nombre_o_indice is not None:
        try:
            idx = int(nombre_o_indice)
            nombre = team_names[idx] if idx < len(team_names) else f"indice {idx}"
            return idx, nombre
        except (ValueError, TypeError):
            pass
    hint = _normalizar(nombre_o_indice or "RamónLópez")
    for i, name in enumerate(team_names):
        name_norm = _normalizar(name)
        if hint in name_norm or name_norm in hint:
            return i, name
    print("AVISO: no pude confirmar el indice por nombre de equipo -- asumiendo 0.")
    return 0, None


def contar_tablero(tiles):
    weed = vacias = plant = estructura = 0
    for fila in tiles:
        for c in fila:
            if c is None:
                vacias += 1
            elif isinstance(c, dict):
                k = c.get("kind")
                if k == "WEED":
                    weed += 1
                elif k == "PLANT":
                    plant += 1
                elif k in ("COOP", "PASTURE"):
                    estructura += 1
    return weed, vacias, plant, estructura


def max_tiles(unlocked_quadrants):
    base = 25
    for q in ("NE", "SW", "SE"):
        if q in unlocked_quadrants:
            base += 25
    return base


def main():
    if len(sys.argv) < 2:
        print("Uso: python labor_analysis.py archivo.json [nombre_o_indice]")
        sys.exit(1)

    path = sys.argv[1]
    arg2 = sys.argv[2] if len(sys.argv) > 2 else None

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    info = data.get("info", {}) if isinstance(data, dict) else {}
    steps = data.get("steps", []) if isinstance(data, dict) else data
    team_names = info.get("TeamNames", ["Player 0", "Player 1"])

    idx, nombre = detectar_indice(info, arg2)
    print(f"Jugador: indice {idx} = '{nombre or (team_names[idx] if idx < len(team_names) else idx)}'")
    print(f"Archivo: {path}\n")

    # --- recorrer turno a turno, acumulando por dia ---
    por_dia = {}   # day -> {money_inicio, money_fin, gasto_conocido, n_hire_orders, manos_snapshot(hora12), tablero_snapshot(hora12)}

    for step in steps:
        if not isinstance(step, list) or len(step) <= idx:
            continue
        agente = step[idx]
        obs = agente.get("observation", {})
        action = agente.get("action", {})
        if not isinstance(action, dict):
            continue
        farms = obs.get("farms", [])
        if len(farms) <= idx:
            continue

        day = obs.get("day")
        hour = obs.get("hour")
        money = farms[idx].get("money")
        tiles = farms[idx].get("tiles", [])
        hands = farms[idx].get("hands", [])
        unlocked = farms[idx].get("unlocked_quadrants", [])
        precios = obs.get("market", {}).get("prices", {})

        d = por_dia.setdefault(day, {
            "money_inicio": None, "money_fin": None, "gasto_conocido": 0.0,
            "ingreso": 0.0, "n_hire_orders": 0,
            "manos_h12": None, "tablero_h12": None, "max_tiles_h12": None,
        })
        if d["money_inicio"] is None:
            d["money_inicio"] = money
        d["money_fin"] = money

        if hour == 12:
            d["manos_h12"] = len(hands)
            d["tablero_h12"] = contar_tablero(tiles)
            d["max_tiles_h12"] = max_tiles(unlocked)

        for order in (action.get("market") or []):
            if not order:
                continue
            op = order[0]
            if op == "HIRE":
                d["n_hire_orders"] += 1
            elif op == "SELL":
                d["ingreso"] += precios.get(order[1], 0) * order[2]
            elif op == "BUY_SEED":
                d["gasto_conocido"] += SEED_COST.get(order[1], 0) * order[2]
            elif op == "BUY_ANIMAL":
                d["gasto_conocido"] += ANIMAL_COST.get(order[1], 0) * order[2]
            elif op == "BUY_PRODUCT":
                d["gasto_conocido"] += precios.get(order[1], 0) * order[2]
            elif op == "BUY_LAND":
                # costo real depende de cuantos cuadrantes ya se tenian --
                # aproximamos con el primero disponible en la secuencia
                # 1000/2000/4000 (suficiente para este diagnostico).
                ya = len(unlocked) - 1  # NW no cuenta como "comprado"
                land_costs = [1000, 2000, 4000]
                if 0 <= ya < len(land_costs):
                    d["gasto_conocido"] += land_costs[ya]

    dias = sorted(por_dia.keys())
    print(f"{'dia':4s}{'manos':>7s}{'gasto_hire':>12s}{'tierra_max':>11s}{'ocupado':>9s}{'WEED':>6s}{'vacias':>8s}{'tiles/mano':>11s}")
    resultados = []
    for day in dias:
        d = por_dia[day]
        if d["manos_h12"] is None:
            continue
        gasto_dia = d["money_fin"] is not None and d["money_inicio"] is not None
        cambio_real = (d["money_fin"] - d["money_inicio"]) if gasto_dia else 0
        costo_hire_residuo = max(0.0, d["ingreso"] - d["gasto_conocido"] - cambio_real)

        weed, vacias, plant, estructura = d["tablero_h12"]
        ocupado = plant + estructura
        manos = d["manos_h12"]
        tiles_por_mano = (d["max_tiles_h12"] / manos) if manos > 0 else float("inf")

        resultados.append(dict(day=day, manos=manos, costo_hire=costo_hire_residuo,
                                max_tiles=d["max_tiles_h12"], ocupado=ocupado, weed=weed,
                                vacias=vacias, tiles_por_mano=tiles_por_mano))
        if day % 2 == 0:
            print(f"{day:<4d}{manos:7d}{costo_hire_residuo:12,.0f}{d['max_tiles_h12']:11d}{ocupado:9d}{weed:6d}{vacias:8d}{tiles_por_mano:11.1f}")

    # --- resumen / diagnostico ---
    print()
    print("=" * 78)
    print("DIAGNOSTICO")
    print("=" * 78)
    total_hire = sum(r["costo_hire"] for r in resultados)
    print(f"Costo total de contratacion (mano de obra) en toda la partida: ${total_hire:,.0f}")

    # correlacion simple: dias donde tiles_por_mano es alto Y weed tambien es alto
    umbral_tiles_mano = 10
    dias_sobrecargados = [r for r in resultados if r["tiles_por_mano"] > umbral_tiles_mano and r["weed"] > 5]
    if dias_sobrecargados:
        print(f"\nDias con >={umbral_tiles_mano} tiles por mano Y >5 de maleza (posible sobre-expansion de tierra):")
        for r in dias_sobrecargados:
            print(f"  dia {r['day']}: {r['tiles_por_mano']:.1f} tiles/mano, {r['weed']} WEED, {r['manos']} manos, {r['max_tiles']} tiles totales")
    else:
        print(f"\nNo se encontraron dias con >={umbral_tiles_mano} tiles/mano Y maleza significativa --")
        print("la maleza podria no estar relacionada con la proporcion tierra/mano de obra.")

    if resultados:
        weed_final = resultados[-1]["weed"]
        vacias_final = resultados[-1]["vacias"]
        max_tiles_final = resultados[-1]["max_tiles"]
        print(f"\nAl final de la partida: {weed_final} tiles con maleza + {vacias_final} vacias")
        print(f"  de {max_tiles_final} tiles totales ({100*(weed_final+vacias_final)/max_tiles_final:.0f}% sin uso productivo)")

    # ===================================================================
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))

        d_ = [r["day"] for r in resultados]
        ax = axes[0]
        ax.plot(d_, [r["manos"] for r in resultados], label="Manos activas", color="#1976D2", linewidth=2)
        ax2 = ax.twinx()
        ax2.plot(d_, [r["max_tiles"] for r in resultados], label="Tierra maxima (tiles)", color="#8D6E63", linewidth=2, linestyle="--")
        ax.set_xlabel("Dia")
        ax.set_ylabel("Manos activas", color="#1976D2")
        ax2.set_ylabel("Tiles totales", color="#8D6E63")
        ax.set_title("Manos vs. tierra en el tiempo")
        ax.grid(alpha=0.3)

        ax = axes[1]
        ax.plot(d_, [r["weed"] for r in resultados], label="Maleza (WEED)", color="#6D4C41", linewidth=2)
        ax.plot(d_, [r["vacias"] for r in resultados], label="Tiles vacias", color="#BDBDBD", linewidth=2)
        ax.set_xlabel("Dia")
        ax.set_ylabel("Cantidad de tiles")
        ax.set_title("Maleza y tiles vacias en el tiempo")
        ax.legend()
        ax.grid(alpha=0.3)

        ax = axes[2]
        ax.bar(d_, [r["costo_hire"] for r in resultados], color="#7B5544")
        ax.set_xlabel("Dia")
        ax.set_ylabel("Costo de contratacion ($)")
        ax.set_title("Costo diario de mano de obra")
        ax.grid(alpha=0.3)

        plt.tight_layout()
        out_path = Path(path).with_name("labor_analysis.png")
        plt.savefig(out_path, dpi=150)
        print(f"\nGrafico guardado en: {out_path}")
    except ImportError:
        print("\nmatplotlib no esta instalado. Corre: pip install matplotlib")
    except Exception as e:
        print(f"\nError al generar grafico: {e}")


if __name__ == "__main__":
    main()
