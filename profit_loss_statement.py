"""
profit_loss_statement.py
--------------------------
Genera un ESTADO DE RESULTADOS (P&L) completo de una partida, con
formato de reporte financiero real -- no solo ganancia neta por rubro
(eso ya lo hace profit_by_type.py), sino la foto completa: de donde
vino cada peso de ingreso, en que se fue cada peso de costo (separando
categorias que profit_by_type.py no separa: contratacion, tierra,
fertilizante, trigo-alimento), y como evoluciono el dinero turno a
turno comparado con el rival.

Uso:
    python profit_loss_statement.py <archivo>.json [nombre_o_indice]

    Sin el segundo argumento: detecta "RamonLopez" automaticamente por
    nombre de equipo (con o sin tildes). Con un numero: fuerza ese indice.

Genera:
    - Estado de resultados completo en texto (consola)
    - estado_resultados.png: 2 graficos -- evolucion de dinero (nos vs
      rival) y desglose de gastos por categoria
"""
import json
import sys
import unicodedata
from pathlib import Path


def _normalizar(s):
    return "".join(
        c for c in unicodedata.normalize("NFD", s or "")
        if unicodedata.category(c) != "Mn"
    ).lower()


SEED_COST = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50, "STRAWBERRY": 100, "MELON": 80}
ANIMAL_COST = {"GOOSE": 300, "COW": 400, "SHEEP": 500}
ANIMAL_PRODUCT = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}
CROPS = list(SEED_COST.keys())


def _fib_hire_cost(n_already_hired_today):
    a, b = 1, 1
    for _ in range(n_already_hired_today):
        a, b = b, a + b
    return a


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


def main():
    if len(sys.argv) < 2:
        print("Uso: python profit_loss_statement.py archivo.json [nombre_o_indice]")
        sys.exit(1)

    path = sys.argv[1]
    arg2 = sys.argv[2] if len(sys.argv) > 2 else None

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    info = data.get("info", {}) if isinstance(data, dict) else {}
    steps = data.get("steps", []) if isinstance(data, dict) else data
    team_names = info.get("TeamNames", ["Player 0", "Player 1"])

    idx, nombre = detectar_indice(info, arg2)
    riv = 1 - idx if len(team_names) > 1 else None
    print(f"Jugador: indice {idx} = '{nombre or team_names[idx] if idx < len(team_names) else idx}'")
    if riv is not None and riv < len(team_names):
        print(f"Rival:   indice {riv} = '{team_names[riv]}'")
    print(f"Archivo: {path}\n")

    # --- acumuladores ---
    ingresos = {}          # producto -> $
    costo_semillas = {p: 0.0 for p in CROPS}
    costo_animales = {a: 0.0 for a in ANIMAL_COST}
    costo_fertilizante = 0.0
    costo_trigo_feed = 0.0
    costo_tierra = 0.0
    dinero_serie = []       # (day, hour, money_nos, money_riv)

    tierra_ya_comprada = 0
    land_costs = [1000, 2000, 4000]
    dinero_inicial = None
    dinero_final = None

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
        money_nos = farms[idx].get("money")
        money_riv = farms[riv].get("money") if riv is not None and riv < len(farms) else None
        if dinero_inicial is None:
            dinero_inicial = money_nos
        dinero_final = money_nos
        if hour == 0:
            dinero_serie.append((day, hour, money_nos, money_riv))

        precios = obs.get("market", {}).get("prices", {})

        for order in (action.get("market") or []):
            if not order:
                continue
            op = order[0]

            if op == "SELL":
                product, qty = order[1], order[2]
                ingresos[product] = ingresos.get(product, 0) + precios.get(product, 0) * qty

            elif op == "BUY_SEED":
                crop, qty = order[1], order[2]
                costo_semillas[crop] = costo_semillas.get(crop, 0) + SEED_COST.get(crop, 0) * qty

            elif op == "BUY_ANIMAL":
                animal, qty = order[1], order[2]
                costo_animales[animal] = costo_animales.get(animal, 0) + ANIMAL_COST.get(animal, 0) * qty

            elif op == "BUY_PRODUCT":
                item, qty = order[1], order[2]
                price = precios.get(item, 0)
                if item == "WHEAT":
                    costo_trigo_feed += price * qty
                elif item == "FERTILIZER":
                    costo_fertilizante += price * qty

            elif op == "BUY_LAND":
                if tierra_ya_comprada < len(land_costs):
                    costo_tierra += land_costs[tierra_ya_comprada]
                    tierra_ya_comprada += 1

            # AJUSTE (bug real encontrado probando este mismo script): el
            # costo de HIRE NO se calcula con la formula Fibonacci -- se
            # infiere como RESIDUO a partir del dinero real (ver mas
            # abajo). Motivo: confirmado con datos reales que el motor
            # real RECHAZA en silencio ordenes HIRE de mas (por ejemplo,
            # una vez que ya se llego a cierto tope de manos ese dia) --
            # esas ordenes rechazadas no cuestan nada, pero la formula
            # Fibonacci las contaba igual como si hubieran costado,
            # infastando el gasto de contratacion en miles de dolares en
            # partidas con mucho HIRE. Calcularlo como residuo hace que
            # el estado de resultados SIEMPRE cierre exacto contra el
            # dinero real, sin importar que ordenes se hayan rechazado.

    # --- separar ingresos de cultivos vs productos animales ---
    ingreso_cultivos = {c: ingresos.get(c, 0) for c in CROPS}
    ingreso_animales = {a: ingresos.get(p, 0) for a, p in ANIMAL_PRODUCT.items()}
    ingreso_fertilizante_venta = ingresos.get("FERTILIZER", 0)

    # AJUSTE: "money" en cada observacion refleja el dinero ANTES de que
    # se aplique la accion de ESE mismo paso -- el ultimo valor de la
    # serie queda desfasado 1 turno contra el resultado final real. El
    # campo "reward" del ULTIMO paso si refleja el dinero verdaderamente
    # final (confirmado contra el resultado que muestra Kaggle). Se usa
    # reward para cerrar el balance del P&L; el resto de la serie (para
    # el grafico de evolucion) no tiene este problema porque solo importa
    # la forma de la curva, no el ultimo punto exacto.
    if steps and len(steps[-1]) > idx:
        reward_final = steps[-1][idx].get("reward")
        if reward_final is not None:
            dinero_final = reward_final

    total_ingresos = sum(ingreso_cultivos.values()) + sum(ingreso_animales.values()) + ingreso_fertilizante_venta
    total_costo_semillas = sum(costo_semillas.values())
    total_costo_animales = sum(costo_animales.values())
    otros_gastos_conocidos = (total_costo_semillas + total_costo_animales + costo_fertilizante
                               + costo_trigo_feed + costo_tierra)

    # Contratacion = residuo real, para que el estado de resultados
    # SIEMPRE cierre exacto contra el dinero real observado (ver
    # comentario mas arriba de por que no se puede confiar en la formula
    # Fibonacci sola).
    cambio_real_dinero = (dinero_final - dinero_inicial) if (dinero_inicial is not None and dinero_final is not None) else None
    if cambio_real_dinero is not None:
        costo_contratacion = total_ingresos - otros_gastos_conocidos - cambio_real_dinero
        costo_contratacion = max(0.0, costo_contratacion)
    else:
        costo_contratacion = 0.0

    total_gastos = otros_gastos_conocidos + costo_contratacion

    # ===================================================================
    print("=" * 72)
    print("ESTADO DE RESULTADOS (P&L)".center(72))
    print("=" * 72)
    print()
    print("INGRESOS")
    print("-" * 72)
    for c in sorted(CROPS, key=lambda c: -ingreso_cultivos[c]):
        if ingreso_cultivos[c]:
            print(f"  Venta de {c:<14s} {ingreso_cultivos[c]:>15,.0f}")
    for a in sorted(ANIMAL_PRODUCT, key=lambda a: -ingreso_animales[a]):
        if ingreso_animales[a]:
            print(f"  Venta de {ANIMAL_PRODUCT[a]:<14s} {ingreso_animales[a]:>15,.0f}")
    if ingreso_fertilizante_venta:
        print(f"  Venta de {'FERTILIZER':<14s} {ingreso_fertilizante_venta:>15,.0f}")
    print("-" * 72)
    print(f"  {'TOTAL INGRESOS':<23s} {total_ingresos:>15,.0f}")
    print()

    print("GASTOS")
    print("-" * 72)
    print(f"  Semillas:")
    for c in sorted(CROPS, key=lambda c: -costo_semillas[c]):
        if costo_semillas[c]:
            print(f"    {c:<20s} {costo_semillas[c]:>13,.0f}")
    print(f"  {'  Subtotal semillas':<23s} {total_costo_semillas:>15,.0f}")
    print()
    print(f"  Animales comprados:")
    for a in sorted(ANIMAL_COST, key=lambda a: -costo_animales[a]):
        if costo_animales[a]:
            print(f"    {a:<20s} {costo_animales[a]:>13,.0f}")
    print(f"  {'  Subtotal animales':<23s} {total_costo_animales:>15,.0f}")
    print()
    print(f"  {'Fertilizante comprado':<23s} {costo_fertilizante:>15,.0f}")
    print(f"  {'Trigo (alimento animal)':<23s} {costo_trigo_feed:>15,.0f}")
    print(f"  {'Expansion de tierra':<23s} {costo_tierra:>15,.0f}")
    print(f"  {'Contratacion (manos)':<23s} {costo_contratacion:>15,.0f}")
    print("-" * 72)
    print(f"  {'TOTAL GASTOS':<23s} {total_gastos:>15,.0f}")
    print()

    utilidad_neta = total_ingresos - total_gastos
    print("=" * 72)
    print(f"  {'UTILIDAD NETA':<23s} {utilidad_neta:>15,.0f}")
    print("=" * 72)

    if dinero_serie:
        money_final_nos = dinero_final
        money_final_riv = steps[-1][idx].get("observation", {}).get("farms", [{}]*(riv+1))[riv].get("money") if riv is not None else None
        # el reward del propio agente rival no esta disponible desde
        # nuestro punto de vista en algunos formatos -- se usa el ultimo
        # "money" observado como mejor aproximacion si el reward directo
        # no esta accesible.
        try:
            reward_riv = steps[-1][riv].get("reward") if riv is not None and len(steps[-1]) > riv else None
            if reward_riv is not None:
                money_final_riv = reward_riv
        except Exception:
            pass
        print()
        print(f"Dinero final -- nosotros: {money_final_nos:,.0f}", end="")
        if money_final_riv is not None:
            resultado = "GANAMOS" if money_final_nos > money_final_riv else "PERDIMOS"
            print(f"   rival: {money_final_riv:,.0f}   --> {resultado}")
        else:
            print()

    # ===================================================================
    # graficos
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

        # grafico 1: evolucion de dinero
        dias = [d for d, h, m0, m1 in dinero_serie]
        m0s = [m0 for d, h, m0, m1 in dinero_serie]
        m1s = [m1 for d, h, m0, m1 in dinero_serie]
        ax1.plot(dias, m0s, label=nombre or "Nosotros", linewidth=2, color="#2E7D32")
        if any(v is not None for v in m1s):
            ax1.plot(dias, m1s, label=team_names[riv] if riv is not None else "Rival", linewidth=2, color="#C62828")
        ax1.set_xlabel("Dia")
        ax1.set_ylabel("Dinero ($)")
        ax1.set_title("Evolucion de dinero por dia")
        ax1.legend()
        ax1.grid(alpha=0.3)

        # grafico 2: desglose de gastos por categoria
        categorias = ["Semillas", "Animales", "Fertilizante", "Trigo\n(alimento)", "Tierra", "Contratacion"]
        valores = [total_costo_semillas, total_costo_animales, costo_fertilizante,
                   costo_trigo_feed, costo_tierra, costo_contratacion]
        colors = plt.cm.tab10.colors[:len(categorias)]
        bars = ax2.bar(categorias, valores, color=colors)
        ax2.set_ylabel("Gasto total ($)")
        ax2.set_title("Gastos por categoria")
        ax2.bar_label(bars, fmt="%.0f", padding=3)
        plt.setp(ax2.get_xticklabels(), rotation=20, ha="right")

        plt.tight_layout()
        out_path = Path(path).with_name("estado_resultados.png")
        plt.savefig(out_path, dpi=150)
        print(f"\nGrafico guardado en: {out_path}")
    except ImportError:
        print("\nmatplotlib no esta instalado. Corre: pip install matplotlib")
    except Exception as e:
        print(f"\nError al generar grafico: {e}")


if __name__ == "__main__":
    main()
