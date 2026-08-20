"""
board.py
--------
Helpers de solo-lectura sobre el grid de tiles y el shed. Nada aqui
decide que hacer, solo responde preguntas sobre el tablero.
"""

ANIMAL_STRUCTURES = ("COOP", "PASTURE")


def step_toward(fx, fy, tx, ty):
    """Un paso de movimiento hacia el objetivo. None si ya llegamos."""
    if fx > tx:
        return "WEST"
    if fx < tx:
        return "EAST"
    if fy > ty:
        return "NORTH"
    if fy < ty:
        return "SOUTH"
    return None


def manhattan(ax, ay, bx, by):
    return abs(ax - bx) + abs(ay - by)


def is_orthogonally_adjacent(pos, target):
    if target is None:
        return False
    return manhattan(pos[0], pos[1], target[0], target[1]) == 1


def shed_tiles(board_size):
    """Las 4 tiles centrales que cuentan como 'adyacente al shed'
    (confirmado en AGENTS.md: (4,4),(5,4),(4,5),(5,5) para boardSize=10).
    El shed en si no aparece en la grilla de tiles."""
    low = board_size // 2 - 1
    high = board_size // 2
    return [(low, low), (high, low), (low, high), (high, high)]


def is_shed_adjacent(pos, board_size):
    return pos in shed_tiles(board_size)


def nearest_shed_tile(pos, board_size):
    return nearest(pos, shed_tiles(board_size))


def iter_tiles(board):
    for y, row in enumerate(board):
        for x, tile in enumerate(row):
            yield x, y, tile


def find_weeds(board):
    return [(x, y) for x, y, t in iter_tiles(board)
            if isinstance(t, dict) and t.get("kind") == "WEED"]


def find_unwatered_plants(board):
    return [(x, y) for x, y, t in iter_tiles(board)
            if isinstance(t, dict) and t.get("kind") == "PLANT"
            and not t.get("watered_today", False)]


def find_ripe_plants(board):
    return [(x, y) for x, y, t in iter_tiles(board)
            if isinstance(t, dict) and t.get("kind") == "PLANT"
            and t.get("yield_units", 0) > 0]


def find_fertilizable_plants(board):
    """Plantas sin bonus de fertilizante activo (fertilized_until_day == -1
    o ya vencido), candidatas a recibir FERTILIZE."""
    result = []
    for x, y, t in iter_tiles(board):
        if isinstance(t, dict) and t.get("kind") == "PLANT":
            if t.get("fertilized_until_day", -1) < 0:
                result.append((x, y))
    return result


def find_empty_tiles(board, exclude=None):
    exclude = exclude or ()
    return [(x, y) for x, y, t in iter_tiles(board) if t is None and (x, y) not in exclude]


def find_empty_animal_structures(board):
    """COOP/PASTURE ya construidos pero sin animal asignado (animal is None)."""
    return [(x, y) for x, y, t in iter_tiles(board)
            if isinstance(t, dict) and t.get("kind") in ANIMAL_STRUCTURES
            and t.get("animal") is None]


def find_occupied_animal_structures(board):
    return [(x, y) for x, y, t in iter_tiles(board)
            if isinstance(t, dict) and t.get("kind") in ANIMAL_STRUCTURES
            and t.get("animal") is not None]


def find_ripe_animals(board):
    """Animales con produccion lista para HARVEST (egg/milk/wool)."""
    return [(x, y) for x, y, t in iter_tiles(board)
            if isinstance(t, dict) and t.get("kind") in ANIMAL_STRUCTURES
            and t.get("animal") is not None and t.get("yield_units", 0) > 0]


def find_fertilizer_ready_animals(board):
    """Animales con fertilizante listo para COLLECT_FERTILIZER."""
    return [(x, y) for x, y, t in iter_tiles(board)
            if isinstance(t, dict) and t.get("kind") in ANIMAL_STRUCTURES
            and t.get("animal") is not None and t.get("fertilizer_available", False)]


def find_needy_animals(board):
    """Animales que necesitan alimento y/o cuidado hoy. Devuelve
    (x, y, needs_feed, needs_care)."""
    result = []
    for x, y, t in iter_tiles(board):
        if isinstance(t, dict) and t.get("kind") in ANIMAL_STRUCTURES and t.get("animal") is not None:
            needs_feed = not t.get("fed_today", False)
            needs_care = not t.get("cared_today", False)
            if needs_feed or needs_care:
                result.append((x, y, needs_feed, needs_care))
    return result


def nearest(pos, candidates):
    if not candidates:
        return None
    fx, fy = pos
    return min(candidates, key=lambda c: manhattan(fx, fy, c[0], c[1]))
