"""
market.py
---------
Decide las ordenes de mercado del turno (compra/venta/hire/tierra) y
arma el "plan" de nivel de granja que planner.py usa para cada unidad
(que plantar, que construir, que animal colocar, si hace falta ir por
trigo/fertilizante al shed).
"""

import math

import board as board_mod
from actions import MarketActions
from economy import (
    CROP_DATA, ANIMAL_DATA, ANIMAL_PRODUCT, FRAGILE_RESOURCES,
    ranked_crops, ranked_animals,
)

NON_SELLABLE_SHED_ITEMS = frozenset(ANIMAL_DATA.keys()) | {"FERTILIZER"}

SHED_SAFETY_MARGIN = 80     # a partir de aqui, forzamos venta para no perder producto (cap 100)
SELL_CHUNK_MIN = 3
TOP_N_CROPS = 3
TOP_N_ANIMAL_SPECIES = 1    # cuantas especies distintas mantenemos activas a la vez

LAND_COSTS_IN_ORDER = [1000, 2000, 4000]  # NE, SW, SE, en ese orden (segun AGENTS.md)
MONEY_SAFETY_BUFFER = 500   # no gastar hasta dejarnos sin margen de maniobra

HIRE_MAX_HANDS_PER_DAY = 3  # limite propio (el costo Fibonacci se dispara rapido)


def _fib_hire_cost(n_already_hired_today):
    """Costo del proximo hire: farmHandCostMult(=1) * fib(n), fib: 1,1,2,3,5,8,13..."""
    a, b = 1, 1
    for _ in range(n_already_hired_today):
        a, b = b, a + b
    return a


def _sell_chunk_fraction(product):
    return 0.20 if product in FRAGILE_RESOURCES else 0.40


def plan_sales(state, memory):
    orders = []
    force_sell = state.shed_total >= SHED_SAFETY_MARGIN

    for product, qty in state.shed.items():
        if qty <= 0 or product in NON_SELLABLE_SHED_ITEMS:
            continue
        price = state.market_prices.get(product, 0)
        should_sell = force_sell or price >= memory.sell_threshold(product)
        if not should_sell:
            continue
        fraction = _sell_chunk_fraction(product)
        chunk = max(int(qty * fraction), min(SELL_CHUNK_MIN, qty))
        chunk = min(chunk, qty)
        if chunk > 0:
            orders.append(MarketActions.sell(product, chunk))

    return orders


def _count_usable_tiles(state):
    usable = 0
    locked = 0
    for _x, _y, t in board_mod.iter_tiles(state.board):
        if t == "LOCKED":
            locked += 1
        else:
            usable += 1
    return usable, locked


def _tiles_in_use(state):
    used = 0
    for _x, _y, t in board_mod.iter_tiles(state.board):
        if isinstance(t, dict) and t.get("kind") in ("PLANT", "COOP", "PASTURE"):
            used += 1
    return used


def plan_seed_purchases(state, target_crops, money_left):
    orders = []
    for crop in target_crops:
        seed_cost = CROP_DATA[crop]["seed_cost"]
        if state.seeds.get(crop, 0) <= 0 and money_left >= seed_cost:
            orders.append(MarketActions.buy_seed(crop, 1))
            money_left -= seed_cost
    return orders, money_left


def plan_animal_purchase(state, target_species, money_left):
    """Compra un animal si aun no tenemos ninguno vivo/pendiente de esa
    especie en el shed ni ya colocado, y hay estructura vacia o planeamos
    construir una."""
    orders = []
    if target_species is None:
        return orders, money_left

    info = ANIMAL_DATA[target_species]
    already_have = state.shed.get(target_species, 0) > 0
    empty_structures = board_mod.find_empty_animal_structures(state.board)
    matching_empty = any(
        state.board[y][x].get("kind") == info["structure"]
        for x, y in empty_structures
    )

    if not already_have and (matching_empty) and money_left >= info["seed_cost"]:
        orders.append(MarketActions.buy_animal(target_species, 1))
        money_left -= info["seed_cost"]

    return orders, money_left


def plan_build_targets(state, target_species):
    """Si no hay ninguna estructura vacia del tipo correcto y no
    tenemos una ya construida, elige UNA tile vacia para construir."""
    if target_species is None:
        return []

    structure = ANIMAL_DATA[target_species]["structure"]
    has_matching_structure = any(
        isinstance(t, dict) and t.get("kind") == structure
        for _x, _y, t in board_mod.iter_tiles(state.board)
    )
    if has_matching_structure:
        return []

    empty_tiles = board_mod.find_empty_tiles(state.board, exclude=board_mod.shed_tiles(state.board_size))
    if not empty_tiles:
        return []

    x, y = board_mod.nearest(state.farmer_pos, [(ex, ey) for ex, ey in empty_tiles])
    return [(x, y, structure)]


def plan_hire(state, money_left):
    orders = []
    if state.hires_today >= HIRE_MAX_HANDS_PER_DAY:
        return orders, money_left

    next_cost = _fib_hire_cost(state.hires_today)
    tiles_used = _tiles_in_use(state)
    workers = 1 + len(state.hands_pos)

    # Solo contratamos si ya estamos usando bastante tierra por trabajador
    # (evita pagar por manos ociosas) y el costo sigue siendo razonable.
    if tiles_used >= workers * 6 and money_left - next_cost >= MONEY_SAFETY_BUFFER:
        orders.append(MarketActions.hire())
        money_left -= next_cost

    return orders, money_left


def plan_land_purchase(state, money_left):
    orders = []
    usable, locked = _count_usable_tiles(state)
    if locked == 0:
        return orders, money_left

    tiles_used = _tiles_in_use(state)
    # Compramos el siguiente quadrante si estamos usando casi toda la
    # tierra actual y nos sobra dinero de sobra tras el gasto.
    if tiles_used < usable * 0.8:
        return orders, money_left

    already_owned = len(state.unlocked_quadrants) - 1  # NW siempre esta incluido
    already_owned = max(already_owned, 0)
    if already_owned >= len(LAND_COSTS_IN_ORDER):
        return orders, money_left  # ya tenemos las 4 quadrantes

    next_cost = LAND_COSTS_IN_ORDER[already_owned]
    if money_left - next_cost >= MONEY_SAFETY_BUFFER:
        orders.append(MarketActions.buy_land())
        money_left -= next_cost

    return orders, money_left


def plan_fertilizer_purchase(state, money_left, want_fertilizer):
    orders = []
    if not want_fertilizer:
        return orders, money_left
    if state.shed.get("FERTILIZER", 0) > 0:
        return orders, money_left
    cost = 100  # PRICE_TABLE["FERTILIZER"]["base"], comprado via BUY_PRODUCT
    if money_left >= cost:
        orders.append(MarketActions.buy_product("FERTILIZER", 1))
        money_left -= cost
    return orders, money_left


def plan_wheat_purchase_for_feed(state, money_left, want_wheat):
    """Si tenemos animales pero poco/nada de trigo en el shed, compramos
    trigo del mercado en vez de esperar a cosecharlo nosotros mismos."""
    orders = []
    if not want_wheat:
        return orders, money_left
    if state.shed.get("WHEAT", 0) >= len(state.hands_pos) + 1:
        return orders, money_left
    price = state.market_prices.get("WHEAT", CROP_DATA["WHEAT"]["base_price"])
    qty = 3
    cost = price * qty
    if money_left >= cost:
        orders.append(MarketActions.buy_product("WHEAT", qty))
        money_left -= cost
    return orders, money_left


def plan_market_actions(state, memory):
    memory.update(state.market_prices)

    ranked_c = ranked_crops(state.market_prices)
    target_crops = ranked_c[:TOP_N_CROPS] if ranked_c else []
    plantable_crops = [c for c in target_crops if state.seeds.get(c, 0) > 0]

    ranked_a = ranked_animals(state.market_prices)
    has_any_animal_alive = any(
        state.shed.get(a, 0) > 0 or (x, y) in board_mod.find_occupied_animal_structures(state.board)
        for a in ANIMAL_DATA for x, y, t in board_mod.iter_tiles(state.board)
        if isinstance(t, dict) and t.get("animal") == a
    ) or any(
        isinstance(t, dict) and t.get("animal") is not None
        for _x, _y, t in board_mod.iter_tiles(state.board)
    )
    # Solo empezamos a criar UNA especie a la vez (la mas rentable) para
    # no dispersar recursos; si ya tenemos una viva, no cambiamos de plan.
    # Ademas, no nos comprometemos a construir/criar si el dinero actual
    # ni siquiera cubre una fraccion razonable del costo del animal --
    # evita gastar turnos construyendo una estructura que no podemos
    # llenar todavia (mejor seguir enfocados en cultivos mientras tanto).
    target_species = None
    if ranked_a and not has_any_animal_alive:
        candidate = ranked_a[0]
        if state.money >= ANIMAL_DATA[candidate]["seed_cost"] * 0.6:
            target_species = candidate

    want_wheat = has_any_animal_alive
    want_fertilizer = bool(board_mod.find_fertilizable_plants(state.board))

    money_left = state.money

    sell_orders = plan_sales(state, memory)

    seed_orders, money_left = plan_seed_purchases(state, target_crops, money_left)
    animal_orders, money_left = plan_animal_purchase(state, target_species, money_left)
    fert_orders, money_left = plan_fertilizer_purchase(state, money_left, want_fertilizer)
    wheat_orders, money_left = plan_wheat_purchase_for_feed(state, money_left, want_wheat)
    hire_orders, money_left = plan_hire(state, money_left)
    land_orders, money_left = plan_land_purchase(state, money_left)

    build_targets = plan_build_targets(state, target_species)

    market_orders = (
        sell_orders + seed_orders + animal_orders + fert_orders
        + wheat_orders + hire_orders + land_orders
    )

    plan = {
        "plantable_crops": plantable_crops,
        "build_targets": build_targets,
        "place_species": target_species,
        "want_wheat": want_wheat,
        "want_fertilizer": want_fertilizer,
        "animal_species": tuple(ANIMAL_DATA.keys()),
        "wheat_pickup_qty": 3,
        "fertilizer_pickup_qty": 1,
    }

    return market_orders, plan
