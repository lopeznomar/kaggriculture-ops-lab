"""
planner.py
----------
Decide la accion de UNA unidad (farmer o hand) parada en `pos`,
usando el "plan" del turno armado por market.py (que cultivos
plantar, que construir, que animal colocar, si hace falta trigo o
fertilizante del shed).

Orden de prioridad (de mas a menos urgente):
  cosechar planta/animal > recolectar fertilizante > quitar weed >
  regar > fertilizar > alimentar animal > cuidar animal >
  colocar animal > logistica de shed (drop/pickup) > construir >
  plantar > moverse hacia la mejor tarea pendiente.
"""

import board as board_mod
from actions import UnitActions
from search import gather_candidates, best_candidate


def _immediate_tile_action(tile, plan):
    """Que hacer si estamos parados ENCIMA de esta tile, sin movernos."""
    if isinstance(tile, dict):
        kind = tile.get("kind")

        if kind == "WEED":
            return UnitActions.dig()

        if kind == "PLANT":
            if tile.get("yield_units", 0) > 0:
                return UnitActions.harvest()
            if not tile.get("watered_today", False):
                return UnitActions.water()
            if tile.get("fertilized_until_day", -1) < 0 and plan.get("has_fertilizer_in_hand"):
                return UnitActions.fertilize()

        if kind in ("COOP", "PASTURE"):
            if tile.get("animal") is not None:
                if tile.get("yield_units", 0) > 0:
                    return UnitActions.harvest()
                if tile.get("fertilizer_available", False):
                    return UnitActions.collect_fertilizer()
                needs_feed = not tile.get("fed_today", False)
                needs_care = not tile.get("cared_today", False)
                if needs_feed and plan.get("has_wheat_in_hand"):
                    return UnitActions.feed()
                if needs_care:
                    return UnitActions.care()
            else:
                place_species = plan.get("place_species")
                if place_species and plan.get("has_species_in_hand") == place_species:
                    return UnitActions.place(place_species)

    return None


def _reserved_items(plan):
    """Que NO se debe soltar en el shed (se esta reservando a proposito)."""
    reserved = set()
    if plan.get("want_wheat"):
        reserved.add("WHEAT")
    if plan.get("want_fertilizer"):
        reserved.add("FERTILIZER")
    place_species = plan.get("place_species")
    if place_species:
        reserved.add(place_species)
    return reserved


def _needs_shed_trip(state, unit_inventory, plan):
    reserved = _reserved_items(plan)
    has_droppable = bool({k for k, v in unit_inventory.items() if v and k not in reserved})

    place_species = plan.get("place_species")
    needs_wheat = (plan.get("want_wheat") and not unit_inventory.get("WHEAT")
                   and state.shed.get("WHEAT", 0) > 0)
    needs_species = (place_species and not unit_inventory.get(place_species)
                      and state.shed.get(place_species, 0) > 0)
    needs_fertilizer = (plan.get("want_fertilizer") and not unit_inventory.get("FERTILIZER")
                         and state.shed.get("FERTILIZER", 0) > 0)

    return has_droppable or needs_wheat or needs_species or needs_fertilizer


def _shed_action(pos, state, unit_inventory, plan):
    """Que hacer si estamos junto al shed y hay pendientes de logistica."""
    if not board_mod.is_shed_adjacent(pos, state.board_size):
        return None

    reserved = _reserved_items(plan)
    droppable = {k for k, v in unit_inventory.items() if v and k not in reserved}
    if droppable:
        return UnitActions.drop()

    place_species = plan.get("place_species")

    if plan.get("want_wheat") and not unit_inventory.get("WHEAT") and state.shed.get("WHEAT", 0) > 0:
        qty = min(plan.get("wheat_pickup_qty", 3), state.shed["WHEAT"])
        return UnitActions.pickup("WHEAT", qty)

    if place_species and not unit_inventory.get(place_species) and state.shed.get(place_species, 0) > 0:
        return UnitActions.pickup(place_species, 1)

    if plan.get("want_fertilizer") and not unit_inventory.get("FERTILIZER") and state.shed.get("FERTILIZER", 0) > 0:
        qty = min(plan.get("fertilizer_pickup_qty", 1), state.shed["FERTILIZER"])
        return UnitActions.pickup("FERTILIZER", qty)

    return None


def decide_unit_action(pos, state, unit_index, plan):
    fx, fy = pos
    tile = state.board[fy][fx]
    unit_inventory = state.inventory_of(unit_index)

    # Contexto sobre lo que este unit especifico trae en su inventario,
    # para que _immediate_tile_action sepa si puede fertilizar/alimentar/colocar.
    per_unit_plan = dict(plan)
    per_unit_plan["has_fertilizer_in_hand"] = bool(unit_inventory.get("FERTILIZER"))
    per_unit_plan["has_wheat_in_hand"] = bool(unit_inventory.get("WHEAT"))
    place_species = plan.get("place_species")
    per_unit_plan["has_species_in_hand"] = place_species if place_species and unit_inventory.get(place_species) else None

    # 1. Actuar de inmediato sobre la tile actual, si aplica.
    immediate = _immediate_tile_action(tile, per_unit_plan)
    if immediate is not None:
        return immediate

    # 2. Construir aqui si esta tile vacia esta en el plan de construccion.
    if tile is None:
        for bx, by, structure in plan.get("build_targets", []):
            if (bx, by) == (fx, fy):
                return UnitActions.build_coop() if structure == "COOP" else UnitActions.build_pasture()

    # 3. Plantar si esta vacia, tenemos semilla, y NO es una tile del shed.
    if tile is None and plan.get("plantable_crops") and not board_mod.is_shed_adjacent(pos, state.board_size):
        return UnitActions.plant(plan["plantable_crops"][0])

    # 4. Logistica de shed (drop cosecha / pickup trigo, animal o fertilizante).
    shed_action = _shed_action(pos, state, unit_inventory, per_unit_plan)
    if shed_action is not None:
        return shed_action

    # 5. Sin nada que hacer aqui mismo: buscar la mejor tarea del tablero
    #    y caminar un paso hacia ella.
    candidates = gather_candidates(
        state,
        plan.get("plantable_crops"),
        build_targets=plan.get("build_targets"),
        animals_to_place=place_species,
    )
    target = best_candidate(pos, candidates)

    needs_shed_trip = _needs_shed_trip(state, unit_inventory, plan)

    if target is None:
        if needs_shed_trip:
            shed_target = board_mod.nearest_shed_tile(pos, state.board_size)
            step = board_mod.step_toward(fx, fy, shed_target[0], shed_target[1])
            return UnitActions.move(step) if step else UnitActions.pass_turn()
        return UnitActions.pass_turn()

    tx, ty, _task, _extra = target
    if (tx, ty) == (fx, fy):
        return UnitActions.pass_turn()

    step = board_mod.step_toward(fx, fy, tx, ty)
    return UnitActions.move(step) if step else UnitActions.pass_turn()
