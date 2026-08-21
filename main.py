# ==========================================================
# MAIN.PY - VERSIÓN V7.2 "EL AGRÓNOMO"
# (IO + Mano de Obra + Expansión + Validación de Agua)
# ==========================================================

from dataclasses import dataclass, field
import math

# ==========================================================
# state.py
# ==========================================================

class GameState:
    __slots__ = (
        "player", "day", "hour", "money", "board", "farmer_pos",
        "hands_pos", "unlocked_quadrants", "hires_today",
        "seeds", "shed", "inventories",
        "market_prices", "market_inventory", "unlocked_shops",
        "opponent_farm",
    )

    def __init__(self, obs):
        farms = obs.get("farms", []) or []
        player = obs.get("player", 0)
        private = obs.get("private", {}) or {}
        market = obs.get("market", {}) or {}
        town = obs.get("town", {}) or {}

        farm = farms[player] if farms and player < len(farms) else {
            "money": 0, "tiles": [[]], "farmer": [0, 0],
            "hands": [], "unlocked_quadrants": [], "hires_today": 0,
        }

        self.player = player
        self.day = obs.get("day", 0)
        self.hour = obs.get("hour", 0)

        self.money = farm.get("money", 0)
        self.board = farm.get("tiles", [[]])
        self.farmer_pos = tuple(farm.get("farmer", [0, 0]))
        self.hands_pos = [tuple(p) for p in farm.get("hands", [])]
        self.unlocked_quadrants = farm.get("unlocked_quadrants", [])
        self.hires_today = farm.get("hires_today", 0)

        self.seeds = private.get("seeds", {}) or {}
        self.shed = private.get("shed", {}) or {}
        self.inventories = private.get("inventories", [{}])

        self.market_prices = market.get("prices", {}) or {}
        self.market_inventory = market.get("inventory", {}) or {}
        self.unlocked_shops = town.get("unlocked_shops", [])

        self.opponent_farm = [f for i, f in enumerate(farms) if i != player]

    def inventory_of(self, unit_index):
        if unit_index < len(self.inventories):
            return self.inventories[unit_index] or {}
        return {}

    @property
    def board_size(self):
        return len(self.board)

    @property
    def shed_total(self):
        return sum(self.shed.values()) if self.shed else 0

    def get_game_phase(self):
        if self.day < 7:
            return "early"
        elif self.day < 16:
            return "mid"
        else:
            return "late"

    def get_max_tiles(self):
        """Calcula el máximo de tiles disponibles según los cuadrantes comprados."""
        unlocked = self.unlocked_quadrants
        base = 25
        if "NE" in unlocked:
            base += 25
        if "SW" in unlocked:
            base += 25
        if "SE" in unlocked:
            base += 25
        return base

    def get_watering_capacity(self):
        """Calcula la capacidad de riego total (TURNS_PER_DAY turnos/dia por unidad)."""
        total_units = 1 + len(self.hands_pos)
        return total_units * TURNS_PER_DAY

# ==========================================================
# board.py
# ==========================================================

ANIMAL_STRUCTURES = ("COOP", "PASTURE")

def step_toward(fx, fy, tx, ty):
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
    """AJUSTE V24 -- BUG REAL: antes devolvia solo (x,y), sin ninguna nocion
    de cuan urgente es regar cada planta. best_candidate desempataba
    puramente por DISTANCIA dentro del bucket 'water' -- con varios
    cultivos plantados en tiles distintas, la unidad siempre terminaba
    regando el cluster de plantas MAS CERCANO (tipicamente WHEAT, porque
    el crop_plan lo prioriza y hay mas tiles) mientras CARROT/TOMATO/
    STRAWBERRY/MELON, plantados en otro sector del tablero, se quedaban
    2 dias seguidos sin regar y se convertian en WEED -- semilla pagada,
    cero cosecha. Coincide exactamente con los datos de la ultima partida
    (WHEAT +1113, el resto todo en perdida ~= costo de semilla, ingreso
    0). Ahora se devuelve tambien consecutive_unwatered para que las
    plantas a un dia de morir se puedan priorizar por sobre las recien
    regadas, sin importar la distancia."""
    return [
        (x, y, t.get("consecutive_unwatered", 0))
        for x, y, t in iter_tiles(board)
        if isinstance(t, dict) and t.get("kind") == "PLANT"
        and not t.get("watered_today", False)
    ]

def _is_plant_mature(tile, current_day):
    """
    BUG REAL ENCONTRADO CON DATOS DE PARTIDAS: yield_units puede aparecer
    en 1 desde el mismo turno en que se planta (parece representar el
    bono potencial de riego, no "listo para cosechar YA"). Si intentamos
    HARVEST antes de que pase el tiempo minimo de maduracion, el juego lo
    rechaza en silencio -- la planta se queda sin regar para siempre
    (porque WATER nunca se intenta, HARVEST "gana" la prioridad) y termina
    muriendo como weed. Confirmado viendo la misma tile identica, sin
    cambios, durante 14+ turnos seguidos de HARVEST fallido.
    """
    info = CROP_DATA.get(tile.get("crop"))
    if not info:
        return True  # cultivo desconocido -- no bloquear, dejar intentar
    planted_day = tile.get("planted_day", current_day)
    age = current_day - planted_day
    if info["yield_type"] == "onetime":
        return age >= info["time_max_yield"]
    return age >= info["time_first_yield"]

def _is_animal_mature(tile, current_day):
    """Mismo problema que con las plantas, pero para animales (usa placed_day)."""
    info = ANIMAL_DATA.get(tile.get("animal"))
    if not info:
        return True
    placed_day = tile.get("placed_day", current_day)
    age = current_day - placed_day
    return age >= info["time_first_yield"]

def find_ripe_plants(board, current_day):
    return [(x, y) for x, y, t in iter_tiles(board)
            if isinstance(t, dict) and t.get("kind") == "PLANT"
            and t.get("yield_units", 0) > 0
            and _is_plant_mature(t, current_day)]

def find_fertilizable_plants(board):
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
    return [(x, y) for x, y, t in iter_tiles(board)
            if isinstance(t, dict) and t.get("kind") in ANIMAL_STRUCTURES
            and t.get("animal") is None]

def find_occupied_animal_structures(board):
    return [(x, y) for x, y, t in iter_tiles(board)
            if isinstance(t, dict) and t.get("kind") in ANIMAL_STRUCTURES
            and t.get("animal") is not None]

def find_ripe_animals(board, current_day):
    return [(x, y) for x, y, t in iter_tiles(board)
            if isinstance(t, dict) and t.get("kind") in ANIMAL_STRUCTURES
            and t.get("animal") is not None and t.get("yield_units", 0) > 0
            and _is_animal_mature(t, current_day)]

def find_fertilizer_ready_animals(board):
    return [(x, y) for x, y, t in iter_tiles(board)
            if isinstance(t, dict) and t.get("kind") in ANIMAL_STRUCTURES
            and t.get("animal") is not None and t.get("fertilizer_available", False)]

def find_needy_animals(board):
    """AJUSTE V28 -- mismo bug que ya se arreglo para el riego (find_
    unwatered_plants), pero nunca se aplico a los animales: antes no se
    traia consecutive_unfed, asi que con 2+ animales necesitando comida
    el mismo dia y pocas manos disponibles, el desempate era solo por
    distancia -- pudiendo dejar SIEMPRE al animal mas lejano sin comer,
    2 dias seguidos, hasta que se escapa. Ahora se expone la urgencia
    real para poder priorizar al animal que esta a punto de escaparse
    por sobre uno recien alimentado, sin importar la distancia."""
    result = []
    for x, y, t in iter_tiles(board):
        if isinstance(t, dict) and t.get("kind") in ANIMAL_STRUCTURES and t.get("animal") is not None:
            needs_feed = not t.get("fed_today", False)
            needs_care = not t.get("cared_today", False)
            if needs_feed or needs_care:
                result.append((x, y, needs_feed, needs_care, t.get("consecutive_unfed", 0)))
    return result

def nearest(pos, candidates):
    if not candidates:
        return None
    fx, fy = pos
    return min(candidates, key=lambda c: manhattan(fx, fy, c[0], c[1]))

def count_empty_tiles(board):
    count = 0
    for _x, _y, t in iter_tiles(board):
        if t is None:
            count += 1
    return count

def count_crop_on_board(board, crop):
    """Cuenta cuantas tiles ya tienen este cultivo plantado (crezca o no),
    para poder respetar un tope de asignacion por cultivo."""
    count = 0
    for _x, _y, t in iter_tiles(board):
        if isinstance(t, dict) and t.get("kind") == "PLANT" and t.get("crop") == crop:
            count += 1
    return count

# ==========================================================
# actions.py
# ==========================================================

@dataclass(slots=True)
class Decision:
    farmer: list = field(default_factory=lambda: ["PASS"])
    hands: list = field(default_factory=list)
    market: list = field(default_factory=list)

    def to_dict(self):
        return {"farmer": self.farmer, "hands": self.hands, "market": self.market}

class UnitActions:
    @staticmethod
    def pass_turn():
        return ["PASS"]

    @staticmethod
    def move(direction):
        return [direction]

    @staticmethod
    def water():
        return ["WATER"]

    @staticmethod
    def harvest():
        return ["HARVEST"]

    @staticmethod
    def dig():
        return ["DIG"]

    @staticmethod
    def plant(crop):
        return ["PLANT", crop]

    @staticmethod
    def fertilize():
        return ["FERTILIZE"]

    @staticmethod
    def pickup(item, n=1):
        return ["PICKUP", item, n]

    @staticmethod
    def drop():
        return ["DROP"]

    @staticmethod
    def place(item, n=1):
        return ["PLACE", item, n]

    @staticmethod
    def feed():
        return ["FEED"]

    @staticmethod
    def care():
        return ["CARE"]

    @staticmethod
    def collect_fertilizer():
        return ["COLLECT_FERTILIZER"]

    @staticmethod
    def build_coop():
        return ["BUILD_COOP"]

    @staticmethod
    def build_pasture():
        return ["BUILD_PASTURE"]

class MarketActions:
    @staticmethod
    def sell(product, qty):
        return ["SELL", product, qty]

    @staticmethod
    def buy_seed(crop, qty=1):
        return ["BUY_SEED", crop, qty]

    @staticmethod
    def buy_animal(species, qty=1):
        return ["BUY_ANIMAL", species, qty]

    @staticmethod
    def buy_product(item, qty=1):
        return ["BUY_PRODUCT", item, qty]

    @staticmethod
    def hire():
        return ["HIRE"]

    @staticmethod
    def buy_land():
        return ["BUY_LAND"]

# ==========================================================
# economy.py
# ==========================================================

# AJUSTE V7.3 (con tabla oficial confirmada por el usuario):
# 1) MELON["time_max_yield"] estaba en 12, pero el oficial es 10 -- la
#    ventana de bonus por riego es edad 6-12, pero el yield YA toco el
#    tope de 6 en el dia 10 (regando desde el dia 6, +1/dia = 4 unidades
#    sobre la base de 1 se satura en el dia 10; los dias 11-12 no suman
#    nada, y de hecho en el dia 11 la planta YA empieza a decaer hacia
#    weed). Con el valor viejo (12), _is_plant_mature bloqueaba el
#    HARVEST dos dias despues de que el rendimiento ya habia arrancado a
#    caer -- MELON, el cultivo de mayor payout ($250 base), quedaba
#    perjudicado en la practica y also subvalorado en crop_score (cycle
#    mas largo = score mas bajo de lo que realmente es).
# 2) WHEAT/CARROT: max_yield=6/4 SOLO se alcanza fertilizando la planta.
#    FERTILIZER_PRIORITY_CROPS (mas abajo) nunca fertiliza WHEAT ni
#    CARROT -- solo MELON/STRAWBERRY -- asi que en la practica el techo
#    real que este bot logra es el SIN fertilizar: 4 y 3. Con los valores
#    viejos, crop_score sobreestimaba el revenue real de WHEAT/CARROT y
#    los rankeaba mejor de lo que en verdad rinden, sesgando el
#    optimizador hacia ellos y lejos de MELON/TOMATO/STRAWBERRY.
CROP_DATA = {
    "WHEAT":      {"yield_type": "onetime", "seed_cost": 10,  "base_price": 25,  "time_first_yield": 2,  "time_max_yield": 4,  "subsequent_every": None, "max_yield": 4},
    "CARROT":     {"yield_type": "onetime", "seed_cost": 20,  "base_price": 35,  "time_first_yield": 2,  "time_max_yield": 3,  "subsequent_every": None, "max_yield": 3},
    "TOMATO":     {"yield_type": "ongoing", "seed_cost": 50,  "base_price": 60,  "time_first_yield": 8,  "time_max_yield": None, "subsequent_every": 1,  "max_yield": 4},
    "STRAWBERRY": {"yield_type": "ongoing", "seed_cost": 100, "base_price": 120, "time_first_yield": 10, "time_max_yield": None, "subsequent_every": 2,  "max_yield": 4},
    "MELON":      {"yield_type": "onetime", "seed_cost": 80,  "base_price": 250, "time_first_yield": 10, "time_max_yield": 10, "subsequent_every": None, "max_yield": 6},
}

ANIMAL_PRODUCT = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}

ANIMAL_DATA = {
    "GOOSE": {"structure": "COOP",    "seed_cost": 300, "base_price": 50,  "time_first_yield": 4, "subsequent_every": 1, "max_yield": 4},
    "COW":   {"structure": "PASTURE", "seed_cost": 400, "base_price": 160, "time_first_yield": 8, "subsequent_every": 2, "max_yield": 6},
    "SHEEP": {"structure": "PASTURE", "seed_cost": 500, "base_price": 200, "time_first_yield": 6, "subsequent_every": 3, "max_yield": 6},
}

# AJUSTE (decision explicita del usuario, con permiso expreso -- NO es un
# hardcode encontrado por auditoria, es una exclusion pedida a proposito):
# GOOSE queda fuera de toda compra/ranking. Justificacion con datos: a
# precio base, animal_score(GOOSE)=-39.3 -- el UNICO rubro (de 5 cultivos
# + 3 animales) negativo por defecto, porque el costo de alimentarlo
# supera el ingreso del huevo. En la practica el sistema dinamico casi
# nunca lo elegia solo; esto formaliza esa exclusion en vez de dejarla
# librada al ranking turno a turno. TOMATO se evaluo para la misma
# exclusion pero se descarto: a diferencia de GOOSE, TOMATO nunca dio
# negativo en ninguna partida real analizada (+$1099 neto en la ultima),
# asi que se lo dejo adentro del ranking dinamico normal.
EXCLUDED_ANIMALS = frozenset({"GOOSE"})

PRICE_TABLE = {
    "WHEAT":      {"base": 25,  "I0": 10000, "T": 400, "below_func": "sqrt",  "below_target": 0.80, "above_func": "log",  "above_target": 0.20},
    "CARROT":     {"base": 35,  "I0": 10000, "T": 450, "below_func": "log",   "below_target": 0.20, "above_func": "sqrt", "above_target": 0.70},
    "TOMATO":     {"base": 60,  "I0": 10000, "T": 200, "below_func": "linear","below_target": 0.40, "above_func": "sqrt", "above_target": 0.60},
    "STRAWBERRY": {"base": 120, "I0": 10000, "T": 100, "below_func": "sqrt",  "below_target": 0.70, "above_func": "linear","above_target": 1.60},
    "MELON":      {"base": 250, "I0": 10000, "T": 300, "below_func": "log",   "below_target": 0.20, "above_func": "sq",   "above_target": 3.60},
    "EGG":        {"base": 50,  "I0": 10000, "T": 332, "below_func": "linear","below_target": 0.40, "above_func": "log",  "above_target": 0.20},
    "MILK":       {"base": 160, "I0": 10000, "T": 122, "below_func": "sqrt",  "below_target": 0.60, "above_func": "linear","above_target": 1.60},
    "WOOL":       {"base": 200, "I0": 10000, "T": 105, "below_func": "log",   "below_target": 0.20, "above_func": "sq",   "above_target": 3.20},
    "FERTILIZER": {"base": 100, "I0": 10000, "T": 200, "below_func": "linear","below_target": 0.40, "above_func": "linear","above_target": 0.40},
}

FRAGILE_RESOURCES = {r for r, p in PRICE_TABLE.items() if p["above_target"] >= 1.5}

def _shape(kind, x):
    if kind == "linear":
        return x
    if kind == "sq":
        return x ** 2
    if kind == "sqrt":
        return math.sqrt(x)
    if kind == "log":
        return math.log(1 + x)
    if kind == "log10":
        return math.log10(1 + x)
    raise ValueError(f"forma de precio desconocida: {kind}")

def price_at_inventory(resource, inventory):
    p = PRICE_TABLE.get(resource)
    if p is None:
        return None

    base, i0, t = p["base"], p["I0"], p["T"]
    if inventory < i0:
        func, target, sign = p["below_func"], p["below_target"], 1
    elif inventory > i0:
        func, target, sign = p["above_func"], p["above_target"], -1
    else:
        return base

    amp = target * base / _shape(func, t)
    price = base + sign * amp * _shape(func, abs(inventory - i0))
    return max(1, round(price))

# AJUSTE V24: estos ya NO son constantes fijas -- se actualizan en cada
# llamada a agent() leyendo el objeto `config` real cuando esta disponible
# (ver _apply_config mas abajo). El problema real: `agent(obs, config)`
# recibia `config` como parametro y JAMAS lo usaba -- todo el codigo
# asumia a ciegas los defaults documentados (30 dias, 24 turnos/dia, tope
# de 10 ordenes/turno). Si la competencia corre con un config no-default
# en algun momento, el bot rompia sus supuestos en silencio. Los valores
# de aca abajo son solo el FALLBACK si no llega config.
TOTAL_SEASON_DAYS = 30       # fallback: episodeSteps(720) / turnsPerDay(24)
TURNS_PER_DAY = 24           # fallback: turnsPerDay
MAX_MARKET_ORDERS_PER_TURN = 10  # fallback: maxMarketOrdersPerTurn

def _apply_config(config):
    """Lee el config real del juego (si esta disponible) y ajusta las
    constantes globales de las que depende toda la planificacion. Nunca
    debe tirar excepcion -- si config viene vacio, mal formado, o con
    claves faltantes, simplemente se conservan los defaults ya seteados."""
    global TOTAL_SEASON_DAYS, TURNS_PER_DAY, MAX_MARKET_ORDERS_PER_TURN
    if not config:
        return
    try:
        turns_per_day = config.get("turnsPerDay", TURNS_PER_DAY)
        episode_steps = config.get("episodeSteps", TURNS_PER_DAY * TOTAL_SEASON_DAYS)
        if turns_per_day and episode_steps:
            TURNS_PER_DAY = int(turns_per_day)
            TOTAL_SEASON_DAYS = max(1, int(episode_steps) // TURNS_PER_DAY)
        MAX_MARKET_ORDERS_PER_TURN = int(config.get("maxMarketOrdersPerTurn", MAX_MARKET_ORDERS_PER_TURN))
    except Exception:
        pass  # ante cualquier formato inesperado, nos quedamos con los defaults

def optimal_sell_quantity(product, available_qty, current_market_inventory, min_acceptable_price):
    """
    Simula vender de a 1 unidad usando la formula REAL de precio (la misma
    que ya validamos contra los ejemplos del documento oficial), avanzando
    el inventario de mercado en cada paso (vender aumenta la oferta, lo
    que baja el precio segun la curva de cada recurso). Devuelve cuantas
    unidades vender antes de que el precio caiga por debajo del minimo
    aceptable -- en vez de adivinar una fraccion fija del stock.
    """
    qty = 0
    inv = current_market_inventory
    for _ in range(available_qty):
        price = price_at_inventory(product, inv)
        if price is None or price < min_acceptable_price:
            break
        qty += 1
        inv += 1  # vender agrega oferta al mercado
    return qty

def _crop_cycle_length(crop):
    info = CROP_DATA[crop]
    if info["yield_type"] == "onetime":
        return max(info["time_max_yield"], 1)
    return max(info["time_first_yield"] + (info["max_yield"] - 1) * info["subsequent_every"], 1)

def _saturation_adjusted_price(product, current_price, already_committed_units):
    """
    AJUSTE V31 -- GAP REAL ENCONTRADO comparando contra la partida del
    jugador #1 del ranking (カワシギ): crop_score/animal_score usan el
    precio ACTUAL como si fuera constante para siempre, sin importar
    cuanto YA estemos produciendo de lo mismo. Eso ignora un punto clave
    confirmado con datos reales: WOOL y MELON usan una curva de precio
    "sq" (cuadratica) que se mantiene cerca del precio base con oferta
    chica, pero se DESPLOMA a ~$1 con oferta moderada (confirmado
    numericamente: WOOL cae a $1 con apenas +80 unidades de inventario
    sobre el equilibrio). El jugador #1 gano $45302 netos con solo 4
    SHEEP (vs nosotros/otros jugadores con mas cabezas y mucho menos
    retorno por unidad) -- consistente con mantener la oferta baja a
    proposito para no reventar el precio de WOOL. Nuestro modelo de score
    no tenia forma de "saber" esto: evaluaba cada animal/cultivo nuevo
    como si fuera a vender siempre al precio de HOY, sin descontar que
    el rebano/cultivo que YA tenemos va a inundar el mismo mercado antes
    de que la unidad nueva llegue a vender algo.
    AHORA: se usa la MISMA curva de precio real (price_at_inventory, ya
    validada 100% contra la tabla oficial) para estimar el precio
    esperado de la SIGUIENTE unidad, asumiendo que lo que ya tenemos
    comprometido (already_committed_units) ya esta empujando el
    inventario de mercado hacia arriba. No es una heuristica inventada --
    es la formula oficial aplicada de forma prospectiva en vez de solo
    reactiva (que es como ya se usa en optimal_sell_quantity).
    NOTA DE INCERTIDUMBRE: el punto de partida (I0, el inventario de
    equilibrio) es una aproximacion -- no sabemos el inventario de
    mercado REAL en el futuro (depende tambien del oponente y del pueblo).
    Esto es una senal direccional (penaliza saturarse de lo mismo), no un
    numero exacto garantizado.
    """
    p = PRICE_TABLE.get(product)
    if p is None or already_committed_units <= 0:
        return current_price
    projected_inventory = p["I0"] + already_committed_units
    adjusted = price_at_inventory(product, projected_inventory)
    if adjusted is None:
        return current_price
    # nunca dejar que la proyeccion futura suba el precio por encima del
    # actual -- esto es solo un techo de precaucion, no una prediccion
    # optimista del mercado.
    return min(current_price, adjusted)

def crop_score(crop, current_price, days_remaining=None):
    """
    days_remaining: cuantos dias quedan en la temporada desde HOY. Si el
    cultivo no alcanza a completar (ni siquiera la primera cosecha en
    cultivos "ongoing", o la cosecha completa en cultivos "onetime")
    antes de que se acabe la temporada, se excluye del todo -- plantarlo
    seria tirar la semilla y la tile a la basura sin cobrar nunca nada.
    Para "ongoing" que alcanzan a dar ALGUNAS cosechas pero no todas, se
    calcula con las unidades REALMENTE alcanzables, no con el maximo.

    NOTA DEL USUARIO (pendiente de confirmar con datos, NO aplicada
    todavia como exclusion -- requiere permiso expreso antes de
    hardcodear nada): en partidas jugadas manualmente, excluir TOMATO
    de los rubros comercializados y concentrarse en menos cultivos dio
    mejor resultado que diversificar. Desde que se elimino el atajo
    hardcodeado de turno 0 (AJUSTE V43), TOMATO vuelve a poder aparecer
    en la rotacion si el scoring dinamico lo considera rentable ese dia
    -- ya no hay ningun filtro manual que lo excluya. Dos hipotesis
    posibles, pendientes de verificar con logs completos de partida
    antes de decidir el ajuste:
      1) TOMATO es objetivamente poco rentable con la curva de precio
         real (base_price=60, ciclo largo) -- si es asi, crop_score/
         _crop_price_for_planning YA deberia dejarlo afuera solo, sin
         exclusion manual; si sigue entrando y perjudicando, hay un bug
         real ahi que corregir.
      2) El problema no es TOMATO en si, sino que diversification_cap/
         n_viable (ver optimizar_cultivos_io) reparte tierra entre
         demasiados cultivos viables en vez de concentrar en los 2-3
         mejores -- en ese caso el ajuste va en esa funcion, no aca.
    """
    info = CROP_DATA[crop]
    seed_cost = info["seed_cost"]

    if info["yield_type"] == "onetime":
        cycle = max(info["time_max_yield"], 1)
        if days_remaining is not None and days_remaining < cycle:
            return float("-inf")  # no alcanza a madurar -- semilla perdida
        units = info["max_yield"]
    else:
        first = info["time_first_yield"]
        # AJUSTE V41b -- mismo problema raiz que en animal_score (ver
        # comentario largo ahi): el motor real del juego usa un chequeo
        # MODULAR exacto para decidir cuando un cultivo "ongoing" da
        # cosecha (dias_desde_first % subsequent_every == 0), no "cualquier
        # dia despues de madurar". Exigir solo days_remaining >= first
        # alcanza para madurar pero no deja margen para viajar, cosechar
        # y vender antes de que termine la temporada -- coincide con el
        # patron real de TOMATO/STRAWBERRY plantados tarde que maduran
        # pero se quedan sin cosechar. Se agrega el mismo colchon.
        HARVEST_SALE_BUFFER = 3
        if days_remaining is not None and days_remaining < first + HARVEST_SALE_BUFFER:
            return float("-inf")  # no alcanza ni la primera cosecha (con margen real de venta)
        if days_remaining is None:
            units = info["max_yield"]
            cycle = _crop_cycle_length(crop)
        else:
            # cuantas cosechas entran en el tiempo que queda
            possible = 1 + max(0, (days_remaining - first) // info["subsequent_every"])
            units = min(info["max_yield"], possible)
            cycle = max(first + (units - 1) * info["subsequent_every"], 1)

    revenue = current_price * units
    return (revenue - seed_cost) / cycle

def ranked_crops(prices, days_remaining=None):
    scored = [(c, crop_score(c, prices.get(c, CROP_DATA[c]["base_price"]), days_remaining)) for c in CROP_DATA]
    scored = [(c, s) for c, s in scored if s > float("-inf")]
    scored.sort(key=lambda c: c[1], reverse=True)
    return [c for c, _ in scored]

def _animal_cycle_length(animal):
    info = ANIMAL_DATA[animal]
    return max(info["time_first_yield"] + (info["max_yield"] - 1) * info["subsequent_every"], 1)

FERTILIZER_BONUS_PER_DAY = 25  # aproximacion del valor extra de COW/SHEEP por producir fertilizante

def animal_score(animal, current_price, days_remaining=None, wheat_price=None):
    """Misma logica que crop_score: los animales son todos 'ongoing',
    asi que si no alcanza ni la primera cosecha antes de fin de temporada,
    se excluye; si alcanza parcialmente, se usa lo realmente alcanzable.

    AJUSTE V31 -- BUG REAL ENCONTRADO CON DATOS DE PARTIDA: esta funcion
    NUNCA restaba el costo de ALIMENTAR al animal -- solo el costo de
    compra unico (seed_cost). Cada animal vivo necesita 1 trigo/dia
    TODOS los dias que este vivo, indefinidamente -- un gasto recurrente
    que en la practica pesa mucho mas que el costo de compra a lo largo
    de la temporada. Confirmado en una partida real: 11 GOOSE vivos
    simultaneos, $17940 gastados en trigo para alimentar en toda la
    partida (contra apenas $8700 de costo de compra) -- el ranking nunca
    tuvo forma de saber que sumar el 8vo/9no/10mo/11vo ganso podia ya no
    valer la pena, porque el costo de alimentarlos JAMAS entraba en la
    cuenta. Resultado: la granja se quedo sin cultivos NI animales 8 dias
    seguidos al final de la partida (dia 22 a 29), fundida en gastos de
    alimentacion que superaban lo que esos animales devolvian.
    AHORA se resta el costo estimado de alimentar todo el ciclo (precio
    actual del trigo x 1 unidad/dia x duracion del ciclo), asi un animal
    deja de rankear bien en cuanto alimentarlo deja de valer la pena.
    """
    info = ANIMAL_DATA[animal]
    seed_cost = info["seed_cost"]
    first = info["time_first_yield"]

    # AJUSTE V41 -- BUG CRITICO REAL, CAUSA RAIZ DEL FRACASO SISTEMATICO
    # DE SHEEP EN PARTIDAS REALES: este chequeo solo exigia llegar a
    # MADURAR (days_remaining >= first_yield_day), sin dejar ni un dia de
    # margen para viajar hasta el animal, cosecharlo, cargarlo y venderlo
    # despues. Ademas, la produccion real del motor del juego NO es "a
    # partir de ahi, cualquier dia" -- es un chequeo MODULAR exacto
    # (dias_desde_first % subsequent_every == 0): si esa ventana puntual
    # se pierde por cualquier motivo (la unidad llega un dia tarde, esta
    # ocupada con otra tarea, etc.), la siguiente oportunidad es recien
    # subsequent_every dias despues -- y para entonces la temporada ya
    # termino. Confirmado con trazas reales del motor: SHEEP comprado
    # dia20-22 madura dia26-28 (yield_units SI sube a 4-5 unidades reales
    # -- la produccion funciona), pero se queda sin cosechar el resto de
    # la partida por falta de tiempo. Coincide EXACTO con 2 partidas
    # reales seguidas mostrando SHEEP en -$1500 (3 comprados, $0 de
    # ingreso, siempre el mismo patron). Ahora se exige un colchon extra
    # (HARVEST_SALE_BUFFER dias) despues de la primera cosecha esperada,
    # para dejar margen real de viaje + cosecha + venta.
    HARVEST_SALE_BUFFER = 3
    if days_remaining is not None and days_remaining < first + HARVEST_SALE_BUFFER:
        return float("-inf")

    if days_remaining is None:
        units = info["max_yield"]
        cycle = _animal_cycle_length(animal)
    else:
        possible = 1 + max(0, (days_remaining - first) // info["subsequent_every"])
        units = min(info["max_yield"], possible)
        cycle = max(first + (units - 1) * info["subsequent_every"], 1)

    revenue = current_price * units

    wheat_price = wheat_price if wheat_price is not None else CROP_DATA["WHEAT"]["base_price"]
    feed_cost = wheat_price * cycle  # 1 trigo/dia todo el ciclo, al precio actual

    score = (revenue - seed_cost - feed_cost) / cycle

    # COW y SHEEP son "doble proposito": ademas de MILK/WOOL, con CARE
    # tambien producen FERTILIZER (COLLECT_FERTILIZER). GOOSE no. Esto es
    # una aproximacion conservadora (no tenemos la probabilidad exacta
    # documentada), pero refleja que estos dos valen mas de lo que dice
    # su producto principal solo.
    if animal in ("COW", "SHEEP"):
        score += FERTILIZER_BONUS_PER_DAY

    return score

def ranked_animals(prices, days_remaining=None):
    wheat_price = prices.get("WHEAT", CROP_DATA["WHEAT"]["base_price"])
    scored = [
        (a, animal_score(a, prices.get(ANIMAL_PRODUCT[a], ANIMAL_DATA[a]["base_price"]), days_remaining, wheat_price))
        for a in ANIMAL_DATA
        if a not in EXCLUDED_ANIMALS
    ]
    scored = [(a, s) for a, s in scored if s > float("-inf")]
    scored.sort(key=lambda a: a[1], reverse=True)
    return [a for a, _ in scored]

PRICE_MEMORY_DECAY = 0.98
SELL_THRESHOLD_RATIO = 0.75

class MarketMemory:
    def __init__(self):
        self._high_water = {}

    def update(self, prices):
        for product, price in prices.items():
            prev = self._high_water.get(product, price)
            self._high_water[product] = max(price, prev * PRICE_MEMORY_DECAY)

    def sell_threshold(self, product):
        return self._high_water.get(product, 0) * SELL_THRESHOLD_RATIO

# ==========================================================
# market.py - VERSIÓN V7.2 (CON VALIDACIÓN DE AGUA)
# ==========================================================

# AJUSTE (pedido explicito del usuario, con datos que lo respaldan): ANTES
# FERTILIZER estaba aca adentro (nunca se vendia). Partida real
# (93654566): el rival junto $22,022 -- ~44% de su dinero final -- solo
# vendiendo FERTILIZER que recolecto gratis como subproducto de sus
# animales (0 unidades COMPRADAS, 181 vendidas). Nosotros, con la misma
# mecanica disponible, terminamos esa partida con 24 unidades sin vender
# y ademas habiamos COMPRADO 37 unidades (gasto que el rival ni necesito).
# Ahora se vende igual que WHEAT: se reserva lo que hace falta para
# fertilizar los cultivos propios (ver fertilizer_reserved en
# plan_sales_intelligent) y el resto se ofrece al mercado.
NON_SELLABLE_SHED_ITEMS = frozenset(ANIMAL_DATA.keys())
SHED_SAFETY_MARGIN = 50
SELL_CHUNK_MIN = 2
LAND_COSTS_IN_ORDER = [1000, 2000, 4000]
MONEY_SAFETY_BUFFER = 100
SELL_PRICE_BOOST_THRESHOLD = 1.2
FERTILIZER_PRIORITY_CROPS = ["MELON", "STRAWBERRY"]

# ==========================================================
# 1. VALIDACIÓN DE CAPACIDAD DE AGUA
# ==========================================================

def validate_water_availability(crops_dict, state):
    """
    Verifica si hay suficiente capacidad de riego para los cultivos.
    Si no, reduce los cultivos hasta que sea viable.
    """
    capacity = state.get_watering_capacity()
    requirement = sum(crops_dict.values())

    if requirement <= capacity:
        return crops_dict

    # Reducir cultivos empezando por los menos rentables
    priority = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"]
    adjusted = crops_dict.copy()

    while sum(adjusted.values()) > capacity * 0.95:
        # Reducir el cultivo de menor prioridad que tenga > 0
        for crop in priority:
            if adjusted.get(crop, 0) > 0:
                adjusted[crop] -= 1
                break

    return adjusted

# ==========================================================
# 2. OPTIMIZACIÓN CON AGUA
# ==========================================================

def optimizar_cultivos_io(phase, state):
    """
    Optimizacion GREEDY real: ordena los cultivos por rentabilidad usando
    el precio de mercado ACTUAL (no numeros fijos por fase), y les va
    asignando tiles hasta agotar la capacidad de agua/tierra/dinero.
    Esto es un knapsack greedy -- no una LP exacta, pero SI reacciona al
    mercado en tiempo real (si MELON se desploma, deja de priorizarlo).
    """
    tiles_disponibles = state.get_max_tiles()
    capacity = state.get_watering_capacity()
    max_water_tiles = min(capacity, tiles_disponibles)

    days_remaining = max(TOTAL_SEASON_DAYS - state.day, 0)

    # AJUSTE V7.3: ANTES esta reserva era un fijo de $200. Con datos de una
    # partida real, la caja se quedo casi toda la temporada por debajo o muy
    # cerca de $200 (ganancia neta total de la partida: $880 en 30 dias) --
    # eso significaba budget=0 en la enorme mayoria de los turnos, lo que
    # forzaba el fallback duro de mas abajo (get_target_crops_by_phase:
    # "if not optimizacion: return {WHEAT:5}") y dejaba a CARROT, TOMATO,
    # STRAWBERRY, MELON y los animales en CERO produccion durante TODA la
    # temporada -- una trampa de pobreza autoreforzada (sin diversificar no
    # crece la caja, y sin caja no se puede diversificar). AHORA la reserva
    # escala con el dinero disponible (nunca mas de $200, pero mucho menos
    # cuando la caja es chica), para que siempre quede algo de presupuesto
    # real con el que el greedy pueda operar.
    OPERATING_RESERVE = min(200, state.money * 0.35)
    budget = max(0, state.money - OPERATING_RESERVE)

    ranked = ranked_crops(state.market_prices, days_remaining)  # ya ordenados por crop_score actual, excluyendo lo que no alcanza a madurar

    # Tope de diversificacion: reparte la capacidad entre TODOS los
    # cultivos viables (rentables y que alcanzan a madurar), no solo los
    # primeros 3. ANTES dividia siempre por 3 fijo -- eso dejaba a los
    # cultivos 4to y 5to mejor rankeados (tipicamente STRAWBERRY/TOMATO)
    # sin NINGUNA tile, porque los primeros 3 ya consumian toda la
    # capacidad antes de que el loop llegara a ellos. Confirmado con un
    # replay real: un rival mantuvo 5 cultivos simultaneos toda la
    # partida; nosotros nunca superamos 3 tipos en la misma partida.
    # AJUSTE V31: para cultivos "fragiles" (MELON/STRAWBERRY, curva de
    # precio muy sensible a la oferta -- ver _saturation_adjusted_price),
    # el score de PLANTAR MAS usa el precio descontado por lo que ya
    # tenemos plantado, no el precio de mercado de hoy. Evita repetir la
    # trampa de sobreproducir un producto premium hasta que su precio se
    # desploma (ver punto 2 de la guia del usuario, confirmado numerico:
    # MELON/WOOL/MILK caen a ~$1 con oferta moderada).
    def _crop_price_for_planning(c):
        raw = state.market_prices.get(c, CROP_DATA[c]["base_price"])
        if c not in FRAGILE_RESOURCES:
            return raw
        already = count_crop_on_board(state.board, c) * CROP_DATA[c]["max_yield"]
        return _saturation_adjusted_price(c, raw, already)

    viable_crops = [
        c for c in ranked
        if crop_score(c, _crop_price_for_planning(c), days_remaining) > 0
    ]

    # AJUSTE (pedido del usuario: concentrar en menos rubros a la vez para
    # no diluir recursos, PERO sin fijar por nombre cual gana -- eso le
    # sacaria al sistema la capacidad de reaccionar al precio real, que es
    # todo el punto de rankear por crop_score en vez de una lista fija.
    # Confirmado el riesgo con datos reales: MELON paso de $250 a $4 en 10
    # dias en una partida -- una prioridad fija por nombre habria seguido
    # invirtiendo ahi en la caida). En vez de eso, se recorta la lista de
    # viables a los MAX_CONCURRENT_CROPS mejor rankeados por score DE HOY
    # -- quien entra a ese grupo puede cambiar de partida en partida, o
    # incluso de un dia a otro dentro de la misma partida, segun el
    # precio real.
    viable_crops = viable_crops[:MAX_CONCURRENT_CROPS]
    n_viable = max(1, min(len(viable_crops), 5))

    # AJUSTE V31 -- BUG REAL: el contexto de este proyecto (bug #21) decia
    # que esto YA se habia corregido a reparto proporcional por 1/duracion
    # de ciclo, pero revisando el codigo real esa correccion NUNCA se
    # aplico -- seguia siendo el reparto equitativo viejo
    # (max_water_tiles // n_viable), que le da el MISMO tope de tiles a
    # WHEAT (ciclo 4 dias, puede rotar 5-7 veces en la temporada) que a
    # STRAWBERRY (ciclo 16 dias, apenas 1-2 rotaciones posibles) o TOMATO
    # (ciclo largo tipo "ongoing"). Esto coincide EXACTAMENTE con los datos
    # reales del grafico de ganancia por cultivo: STRAWBERRY -879 (11
    # semillas compradas, casi nada cosechado) y TOMATO -500 (10 semillas,
    # CERO ingreso) -- la tierra asignada a estos cultivos lentos nunca
    # alcanza a "pagarse" dentro del tope parejo, mientras WHEAT/CARROT
    # (rapidos) sobre-rinden con el mismo tope. Ahora el tope SI se reparte
    # proporcional a 1/duracion_del_ciclo (los cultivos rapidos se llevan
    # mucha mas tierra, los lentos mucha menos), con un piso minimo para
    # mantener diversificacion real de precios en vez de monocultivo total.
    cycle_lengths = {c: _crop_cycle_length(c) for c in viable_crops}
    inv_cycle = {c: 1.0 / cycle_lengths[c] for c in viable_crops}
    total_inv_cycle = sum(inv_cycle.values()) or 1.0
    piso_minimo = max(1, max_water_tiles // (n_viable * 4))
    diversification_cap = {
        c: max(piso_minimo, int(max_water_tiles * inv_cycle[c] / total_inv_cycle))
        for c in viable_crops
    }

    allocation = {}
    remaining_tiles = max_water_tiles
    remaining_budget = budget

    # AJUSTE (fix de mi propio cambio anterior, encontrado en la prueba):
    # este loop recorria "ranked" completo, no "viable_crops" ya recortado
    # a MAX_CONCURRENT_CROPS -- como diversification_cap.get(crop,
    # piso_minimo) cae a piso_minimo para lo que no esta en el diccionario,
    # el cultivo recortado se colaba igual con el piso minimo. Ahora
    # itera sobre viable_crops (ya limitado), para que el tope de
    # concurrencia se respete de verdad.
    for crop in viable_crops:
        if remaining_tiles <= 0 or remaining_budget <= 0:
            break

        price = _crop_price_for_planning(crop)
        seed_cost = CROP_DATA[crop]["seed_cost"]
        max_by_money = remaining_budget // seed_cost if seed_cost > 0 else remaining_tiles
        cap_crop = diversification_cap.get(crop, piso_minimo)
        qty = int(min(remaining_tiles, max_by_money, cap_crop))
        if qty <= 0:
            continue

        allocation[crop] = qty
        remaining_tiles -= qty
        remaining_budget -= qty * seed_cost

    return allocation

# ==========================================================
# 3. EXPANSIÓN DE TIERRA
# ==========================================================

# AJUSTE V7.3: bajado de 300 a 150. Con la reserva vieja, sumada a la de
# OPERATING_RESERVE, se necesitaba tener bastante mas de $500 en caja
# recien para animarse a construir/comprar un animal o avanzar tierra --
# algo que, con una sola granjera y solo WHEAT dando ganancia, la partida
# real nunca alcanzo. Sigue siendo un colchon real (no cero), solo menos
# paralizante.
GLOBAL_MONEY_RESERVE = 150  # nunca gastar en items no-esenciales si eso nos deja por debajo de esto

# AJUSTE (pedido del usuario): cuantos cultivos distintos pueden competir
# por presupuesto/tierra AL MISMO TIEMPO. Bajarlo concentra capital en
# menos rubros (menos dilucion); subirlo diversifica mas. Se aplica DESPUES
# de rankear por crop_score real -- no fija CUALES 4, decide cuantos
# entran, y el ranking dinamico sigue decidiendo quienes son esos 4 cada
# vez que se recalcula.
MAX_CONCURRENT_CROPS = 4
EARLY_INVESTMENT_MIN_DAY = 3  # WHEAT/CARROT recien dan su primera cosecha en el dia 2

# AJUSTE V31b -- CORRECCION DE UN SOBRE-AJUSTE PROPIO: la version anterior
# empujo esto a 5 y subio el colchon de tierra a 50%+$500 pensando que la
# tierra era la causa del pozo de dia 3-4. Con una partida real de por
# medio, quedo claro que fue una sobre-correccion: la tierra CASI NUNCA
# se llegaba a comprar (quedabamos en 1 solo cuadrante toda la partida)
# mientras el rival activaba las 4 y escalaba produccion en serio. La
# causa real del pozo no era la tierra -- era el costo de ALIMENTAR
# animales sin tope (ver animal_score mas abajo), ya corregido. Con esa
# fuga tapada, no hace falta frenar tanto la expansion de tierra.
#
# AJUSTE V51 -- BUG CONFIRMADO CON PARTIDA REAL (93886953): el rival
# expandio a NE el DIA 3; nosotros recien el dia 11 (8 dias de atraso).
# Causa exacta: este gate bloqueaba CUALQUIER compra de tierra antes del
# dia 4, sin importar la plata disponible -- y para cuando se abria, la
# plata ya se habia gastado en semillas/contrataciones de los dias 1-3
# (de $2088 el dia 3 a $442 el dia 4), sin volver a juntar los ~$1300
# necesarios hasta el dia 10-11. Se baja el gate a 2 -- un paso moderado,
# no al extremo de dia 0/1, justamente porque este mismo parametro ya se
# sobre-corrigio dos veces antes (ver historial arriba: una vez fue tan
# agresivo que dejo 6 dias sin plata ni para 1 semilla de WHEAT, otra vez
# tan conservador que nos quedamos en 1 cuadrante toda la partida). El
# colchon real (land_reserve, mas abajo) sigue intacto y sin tocar -- es
# la proteccion real contra comprar tierra y quedarse sin aire.
LAND_EXPANSION_MIN_DAY = 2  # ANTES: 4. Evidencia real: el rival expandio el dia 3.

def plan_land_expansion(state, money_left):
    orders = []

    # No comprometer capital grande en tierra antes de que haya entrado
    # ALGO de ingreso por cosecha -- comprar todo el dia 0 deja la caja en
    # cero durante semanas mientras el primer cultivo aun no produce nada.
    if state.day < LAND_EXPANSION_MIN_DAY:
        return orders, money_left

    # Tampoco en el otro extremo: si quedan menos dias que lo que tarda
    # el cultivo mas rapido (WHEAT) en madurar, la tierra nueva no alcanza
    # a producir nada -- seria plata tirada.
    days_remaining = max(TOTAL_SEASON_DAYS - state.day, 0)
    if days_remaining < CROP_DATA["WHEAT"]["time_max_yield"]:
        return orders, money_left

    # ANTES: cada fase solo intentaba comprar SU quadrante especifico, con
    # una dependencia dura del anterior (ej. "mid" exigia ya tener NE antes
    # de poder comprar SW). Si la ventana temprana se perdia por falta de
    # dinero, quedaba bloqueado el resto de la partida.
    # AHORA: simplemente compra el SIGUIENTE quadrante mas barato que aun
    # no tengamos, en cuanto el dinero lo permita, sin importar la fase.
    already_owned = max(len(state.unlocked_quadrants) - 1, 0)  # NW siempre esta incluido

    # AJUSTE V56 (revertido en V57, RE-APLICADO EN V58 POR DECISION EXPLICITA
    # DEL USUARIO): se probo un tope de 3 cuadrantes (nunca comprar el
    # 4to/SE), se revirtio por una partida donde el resultado general
    # empeoro, y se debatio de nuevo. Decision final del usuario, con
    # datos propios (costeo por centro de costos, 4 de 4 partidas reales
    # con el Cuarto 4 en neto NEGATIVO: -$2261, -$1994, -$4672, -$2385) y
    # confirmacion visual (tablero real mostrando el Cuarto 4 comprado y
    # sin uso productivo): NO comprar mas el 4to cuadrante (SE). Este
    # limite queda FIJO -- no volver a revertir sin instruccion expresa
    # nueva del usuario.
    LIMITE_CUADRANTES_PAGOS = 2  # NE + SW. SE (el 3er pago, 4to cuadrante total) deliberadamente excluido.
    if already_owned >= LIMITE_CUADRANTES_PAGOS:
        return orders, money_left  # ya tenemos NE + SW, que es hasta donde vamos a llegar

    next_cost = LAND_COSTS_IN_ORDER[already_owned]

    # ANTES: exigia la misma reserva fija ($300) sin importar si la
    # compra era de $1000 (NE) o $4000 (SE). Confirmado con datos reales:
    # comprar SW dejo la caja en casi $0 justo cuando hacia falta seguir
    # sembrando MELON ($80 la semilla) -- para cuando el dinero se
    # recupero, ya habian pasado demasiados dias y MELON ya no alcanzaba
    # a madurar antes de fin de temporada. La ventana se cerro por
    # partida doble (plata primero, tiempo despues).
    # AHORA: la reserva escala con el tamano de la compra (30% del costo,
    # con el piso de siempre como minimo), para no quedar tan expuestos
    # justo despues de una compra grande.
    # AJUSTE V30 -- BUG CONFIRMADO CON 2 PARTIDAS REALES: el colchon de
    # 20-30% del costo de la tierra sonaba razonable en abstracto, pero en
    # la practica la caja se desplomaba de ~$1730 a ~$180 justo el dia que
    # se compraba NE (dia 3-4) y JAMAS se recuperaba -- se paso el resto
    # de la temporada en modo subsistencia (entre $0 y $250), sin margen
    # para ningun imprevisto. En una de las 2 partidas esto fue tan grave
    # que para el dia 24 nos quedamos sin plata para comprar ni siquiera
    # 1 semilla de WHEAT ($10) -- 6 dias enteros sin poder replantar NADA.
    # Mientras tanto, un rival que literalmente NO HIZO NADA despues del
    # dia 1 (nunca expandio tierra, nunca diversifico) termino con MAS
    # plata que nosotros -- prueba dura de que gastar de mas sin colchon
    # es peor que no gastar. AHORA el colchon exige mucho mas margen real
    # (50% del costo de la tierra, con un piso absoluto de $500) antes de
    # comprometerse a una expansion grande -- mejor esperar unos dias mas
    # y comprarla con la caja ya probada, que comprarla temprano y quedar
    # sin aire para sostener lo que ya se planto.
    # AJUSTE V31b: bajado de 50%+$500 (que en la practica casi nunca
    # dejaba comprar tierra -- confirmado con una partida real donde nos
    # quedamos en 1 solo cuadrante los 30 dias mientras el rival activaba
    # las 4) a un intermedio mas sano ahora que el drenaje real (comida de
    # animales sin tope, ver animal_score) ya esta tapado.
    land_reserve = max(GLOBAL_MONEY_RESERVE, next_cost * 0.3, 300)
    if money_left - next_cost >= land_reserve:
        orders.append(MarketActions.buy_land())
        money_left -= next_cost

    return orders, money_left

# ==========================================================
# 4. MANO DE OBRA
# ==========================================================

# AJUSTE V50 -- ANALISIS DE ESCALA CON 3 PARTIDAS REALES (93823540,
# 93824423, 93825311): con el fix de animales (V49) ya funcionando --
# empatados o mejor que el rival en COW/SHEEP en las 2 derrotas -- la
# ventaja del rival paso a venir de otro lado: manos contratadas desde
# el arranque. Confirmado con datos publicos del tablero (visibles para
# ambos jugadores): el rival tenia 6 y 10 manos el DIA 0, contra
# nuestras 3. Costo real de contratar agresivo verificado con
# _fib_hire_cost: 10 manos en un solo dia cuestan apenas $143 (4.8% de
# los $3000 iniciales) -- el limite real no era de plata, era este
# numero fijo. La proteccion de presupuesto diario (15% de la caja,
# ver mas abajo) sigue intacta y sin tocar -- sigue siendo la red de
# seguridad real contra sobre-contratar.
EARLY_HIRE_TARGET = 8  # ANTES: 3. Evidencia real: rivales llegaron a 6-10 manos el dia 0.

def desired_hand_count(state, money_left=None):
    """
    ANTES: el tope escalaba solo con la carga de trabajo ACTUAL (tiles
    ocupadas + animales). El dia 0, con 0 tiles ocupadas, esto calculaba
    "solo necesito 1 mano" -- una trampa de huevo-gallina: no contratamos
    porque no hay trabajo, pero nunca hay trabajo porque no contratamos
    suficientes manos para plantarlo. Confirmado con un replay real: un
    rival tenia 3 manos contratadas desde el turno 1 del dia 0, y termino
    el dia con 18 tiles plantadas -- nosotros con 2 manos (llegamos tarde)
    y solo 3 tiles.
    AHORA: en los primeros dias se contrata agresivo de entrada
    (anticipando el trabajo, no reaccionando a el). Despues se pasa al
    calculo dinamico segun la carga real, para seguir escalando con
    mas tierra/animales.
    """
    if state.day <= 2:
        return EARLY_HIRE_TARGET

    # AJUSTE V7.3: ANTES el calculo post-dia-2 usaba solo "tiles_used"
    # (tiles YA plantadas). Eso es circular: cuantas tiles se pueden tener
    # plantadas depende de la capacidad de riego actual (24 turnos por
    # unidad), que a su vez depende de cuantas manos ya se contrataron --
    # con pocas manos, tiles_used se queda bajo, workers_needed calcula
    # "bajo" tambien, y nunca se contrata mas para poder trabajar la
    # tierra ya comprada. AHORA se usa el maximo entre tiles ya en uso y
    # la tierra realmente disponible (get_max_tiles), para que comprar
    # cuadrantes nuevos empuje la contratacion en vez de quedar sin
    # gente que los trabaje.
    #
    # AJUSTE V29 -- BUG CRITICO REPRODUCIDO EN SIMULACION LOCAL: usar
    # tiles_potential SIN NINGUN limite de costo hacia que, apenas se
    # compraba la 2da tierra (dia 3-4), el objetivo saltara a 7+ manos de
    # UNA -- y como las manos hay que RE-contratarlas TODOS los dias
    # (costo Fibonacci, resetea cada dia), eso es un sueldo recurrente de
    # $33/dia (7 manos) a $376/dia (12 manos, el tope) para SIEMPRE, sin
    # importar si la produccion actual ya generaba esa plata. En una
    # simulacion local (agente contra si mismo, 720 turnos) esto vacio la
    # caja de $1728 a $180 en un solo dia y la dejo en los subsuelos
    # (menos de $50) el resto de la temporada: pagabamos manos para
    # trabajar tierra que ni siquiera estaba plantada todavia, mientras
    # la plata para semilla/fertilizante desaparecia. Contratar de mas
    # NO es gratis solo porque "hay tierra" -- cuesta plata TODOS LOS
    # DIAS. Ahora el objetivo se recorta hasta que el sueldo diario de
    # sostenerlo entre dentro de una fraccion razonable de la caja actual.
    tiles_used = _tiles_in_use(state)
    tiles_potential = state.get_max_tiles()
    n_animales = count_animals_alive(state)
    workload = max(tiles_used, tiles_potential) + n_animales * 2
    workers_needed = 1 + workload // 8  # cada trabajador cubre ~8 unidades de carga/dia
    workers_needed = min(max(workers_needed, 2), 12)

    # AJUSTE V29b: el chequeo de presupuesto usaba state.money (el dinero
    # BRUTO del turno), sin enterarse de que ESE MISMO turno ya se estaba
    # por gastar plata en semilla/tierra/fertilizante -- podia autorizar
    # una planilla de sueldos que, sumada al resto de las compras del
    # turno, superaba lo que realmente habia. Ahora usa money_left (lo
    # que efectivamente queda disponible en este punto de la planificacion
    # del turno) cuando esta disponible. Tambien se bajo el tope de 25% a
    # 15% de la caja -- el sueldo se paga TODOS los dias, asi que 1/4 de
    # la caja por dia, todos los dias, es insostenible incluso si un solo
    # dia parece "afordable".
    dinero_de_referencia = money_left if money_left is not None else state.money
    presupuesto_diario_manos = max(0, dinero_de_referencia * 0.15)
    while workers_needed > 2 and _daily_hire_cost(workers_needed) > presupuesto_diario_manos:
        workers_needed -= 1

    return workers_needed

def _daily_hire_cost(n_hands):
    """Costo total de contratar n_hands manos en UN dia (Fibonacci
    creciente, resetea cada dia -- ver _fib_hire_cost)."""
    return sum(_fib_hire_cost(i) for i in range(n_hands))

MAX_HIRES_PER_TURN = 4  # deja espacio para el resto de ordenes (venta, semillas, etc.) dentro del limite real de 10/turno

def plan_hire_optimizado(state, money_left):
    """
    ANTES: contrataba como maximo 1 mano por turno, aunque estuvieramos
    muy por debajo del objetivo y sobrara dinero -- eso hacia que
    tardaramos varios turnos en alcanzar el numero de manos que un rival
    conseguia en un solo turno (varias ordenes HIRE en la misma lista de
    mercado). AHORA: si estamos por debajo del objetivo, contrata varias
    manos en ESTE mismo turno (respetando el costo Fibonacci creciente de
    cada una) -- pero acotado a un maximo por turno para no consumir todo
    el cupo de 10 ordenes de mercado que compartimos con venta/semillas.
    """
    orders = []
    max_hands = desired_hand_count(state, money_left)
    to_hire = min(max_hands - len(state.hands_pos), MAX_HIRES_PER_TURN)
    if to_hire <= 0:
        return orders, money_left

    for i in range(to_hire):
        cost = _fib_hire_cost(state.hires_today + i)
        if money_left < cost:
            break
        orders.append(MarketActions.hire())
        money_left -= cost

    return orders, money_left

def _fib_hire_cost(n_already_hired_today):
    a, b = 1, 1
    for _ in range(n_already_hired_today):
        a, b = b, a + b
    return a

# ==========================================================
# 5. VENTAS INTELIGENTES
# ==========================================================

def _sell_chunk_fraction(product):
    return 0.15 if product in FRAGILE_RESOURCES else 0.25

def _is_endgame_day(day):
    """AJUSTE V24: ANTES esto era una constante de modulo
    (ENDGAME_LIQUIDATION_DAY = TOTAL_SEASON_DAYS - 2) calculada UNA sola
    vez al importar el archivo. Si TOTAL_SEASON_DAYS se actualiza despues
    via _apply_config (config real de la partida), esa constante queda
    vieja/incorrecta para siempre. Ahora se recalcula en cada llamada
    contra el valor actual de TOTAL_SEASON_DAYS."""
    return day >= (TOTAL_SEASON_DAYS - 2)

def plan_sales_intelligent(state, memory):
    """
    HALLAZGO CRITICO (con datos de una partida real): el puntaje final es
    "dinero en el banco", NO valor de cultivos creciendo ni inventario sin
    vender. Si el dia 30 llega con MELON sin cosechar o WHEAT guardado
    "esperando mejor precio", ese valor vale $0 para el resultado -- es
    como si nunca hubiera existido. Confirmado viendo una partida donde
    terminamos con MENOS dinero que un rival que no hizo absolutamente
    nada en toda la partida (se quedo sentado con su capital inicial).
    AHORA: en los ultimos dias de la temporada, se vende TODO sin ninguna
    condicion (precio minimo=1, sin esperar al pueblo, sin umbral de
    "conviene o no") -- cualquier cosa no vendida a esta altura es plata
    perdida de forma segura, así que no hay ninguna razon para esperar.
    """
    orders = []
    is_endgame = _is_endgame_day(state.day)
    force_sell = state.shed_total >= SHED_SAFETY_MARGIN or is_endgame
    # margen bajo el limite real de ordenes/turno (deja espacio a compras)
    max_orders_per_turn = max(1, MAX_MARKET_ORDERS_PER_TURN - 2)

    turn_in_day = state.hour
    is_town_consumption_soon = (turn_in_day % 12) > 9 and not is_endgame

    # AJUSTE V28 -- BUG REAL ENCONTRADO CON DATOS DE PARTIDA: NON_SELLABLE_
    # SHED_ITEMS protege a los animales y al fertilizante de la venta
    # automatica, pero NUNCA protegio al WHEAT -- y el trigo que
    # plan_wheat_purchase_for_feed compra especificamente para alimentar
    # animales se queda en el MISMO shed que el trigo-cosecha para vender.
    # Resultado confirmado: $6257 gastados en trigo para alimentar en una
    # sola partida, con $0 de ingreso animal -- consistente con que ese
    # trigo se vendia de vuelta antes de que alguna unidad lo levantara y
    # lo llevara a FEED, y plan_wheat_purchase_for_feed volvia a comprar
    # mas al ver el shed vacio otra vez: un circulo de compra-venta que
    # quema plata sin que el animal llegue a comer nunca. Ahora se reserva
    # el trigo que hace falta para alimentar (mismo colchon que usa
    # plan_wheat_purchase_for_feed) ANTES de ofrecer el resto en venta.
    #
    # AJUSTE V55 -- BUG REAL CONFIRMADO CON 2 PARTIDAS DISTINTAS
    # (94086794 y 94172352): la version anterior de este mismo fix ponia
    # la reserva en 0 durante la liquidacion final, con el razonamiento de
    # "ya no hay mas dias por delante para que ese trigo alimente a
    # nadie" -- ese razonamiento estaba MAL: is_endgame empieza 2 dias
    # antes del final (TOTAL_SEASON_DAYS-2), y en esos ultimos 1-2 dias
    # los animales siguen VIVOS y siguen necesitando comer. Confirmado
    # con datos reales: en ambas partidas, el ciclo de compra-venta de
    # WHEAT se disparaba EXACTO al entrar en endgame y no paraba mas --
    # la venta liquidaba todo el trigo a 0 (pensando que ya no hacia
    # falta), la compra de emergencia lo reponia para no perder a los
    # animales (bypasea el chequeo de endgame a proposito, ver
    # plan_wheat_purchase_for_feed), y la venta lo volvia a vaciar el
    # turno siguiente -- decenas de ciclos seguidos hasta el final del
    # juego. Ahora la reserva se mantiene EXACTAMENTE IGUAL este en
    # endgame o no, mientras sigan quedando animales vivos -- la
    # liquidacion final debe aplicar a dejar de invertir en cultivos
    # NUEVOS, no a dejar de alimentar lo que ya esta vivo y produciendo.
    wheat_reserved_for_feed = 0
    n_animales = count_animals_alive(state)
    if n_animales > 0:
        wheat_reserved_for_feed = n_animales + 2  # mismo colchon que plan_wheat_purchase_for_feed

    # AJUSTE V52 (mismo cambio que plan_fertilizer_purchase, alineado para
    # no vender de vuelta lo que ahora reservamos de mas): el piso fijo de
    # 3 paso a escalar con la cantidad real de tiles de MELON+STRAWBERRY,
    # asi que la reserva del lado de venta tiene que usar el MISMO calculo
    # -- si no, con mas escala terminariamos vendiendo fertilizante que
    # plan_fertilizer_purchase recien tuvo que volver a comprar.
    n_melon = sum(
        1 for _x, _y, t in iter_tiles(state.board)
        if isinstance(t, dict) and t.get("kind") == "PLANT" and t.get("crop") == "MELON"
    )
    n_strawberry = sum(
        1 for _x, _y, t in iter_tiles(state.board)
        if isinstance(t, dict) and t.get("kind") == "PLANT" and t.get("crop") == "STRAWBERRY"
    )
    fertilizer_reserved = 0 if is_endgame else max(3, min(15, n_melon + n_strawberry))

    for product, qty in state.shed.items():
        if qty <= 0 or product in NON_SELLABLE_SHED_ITEMS:
            continue
        if len(orders) >= max_orders_per_turn:
            break

        if product == "WHEAT" and wheat_reserved_for_feed > 0:
            qty = qty - wheat_reserved_for_feed
            if qty <= 0:
                continue

        if product == "FERTILIZER" and fertilizer_reserved > 0:
            qty = qty - fertilizer_reserved
            if qty <= 0:
                continue

        if is_town_consumption_soon and product != "WHEAT" and not force_sell:
            continue

        if is_endgame:
            # Sin condiciones: vender todo lo que haya, al precio que sea.
            chunk = qty
        else:
            current_inv = state.market_inventory.get(product)

            if product in PRICE_TABLE and current_inv is not None:
                # ANTES: vendiamos una fraccion heuristica adivinada (15-25%
                # del stock) segun un umbral de precio aproximado.
                # AHORA: usamos la formula REAL de precio del juego + el
                # inventario de mercado real para calcular exactamente cuanto
                # podemos vender antes de que el precio caiga por debajo de
                # un minimo aceptable -- no una aproximacion, el numero exacto.
                base = PRICE_TABLE[product]["base"]
                # AJUSTE V28: FRAGILE_RESOURCES ya existia pero solo se
                # usaba en el camino heuristico muerto (el que casi nunca
                # se ejecuta porque casi siempre tenemos current_inv). Los
                # recursos con above_target alto (STRAWBERRY, MELON, WOOL,
                # MILK) se desploman con gluts modestos y les cuesta mucho
                # volver a subir mientras sigamos produciendo/vendiendo --
                # exigirles el mismo 60% del precio base que a WHEAT/
                # CARROT los deja acumulados en el shed esperando una
                # recuperacion que puede no llegar a tiempo. Bajamos el
                # piso para estos, priorizando convertir en efectivo real
                # antes que aguantar por un precio que quiza no vuelva.
                if force_sell:
                    min_price = 1
                elif product in FRAGILE_RESOURCES:
                    min_price = base * 0.35
                else:
                    min_price = base * 0.6
                chunk = optimal_sell_quantity(product, qty, current_inv, min_price)
            else:
                # Respaldo heuristico si no tenemos el inventario de mercado
                # para este producto (no deberia pasar en la practica, pero
                # por si acaso).
                price = state.market_prices.get(product, 0)
                threshold = memory.sell_threshold(product)
                should_sell = force_sell or price >= threshold * SELL_PRICE_BOOST_THRESHOLD
                if not should_sell:
                    continue
                fraction = _sell_chunk_fraction(product)
                chunk = max(int(qty * fraction), min(SELL_CHUNK_MIN, qty))
            chunk = min(chunk, qty)

        if chunk > 0:
            orders.append(MarketActions.sell(product, chunk))

    return orders

# ==========================================================
# 6. OTRAS FUNCIONES
# ==========================================================

def _count_usable_tiles(state):
    usable = 0
    locked = 0
    for _x, _y, t in iter_tiles(state.board):
        if t == "LOCKED":
            locked += 1
        else:
            usable += 1
    return usable, locked

def _tiles_in_use(state):
    used = 0
    for _x, _y, t in iter_tiles(state.board):
        if isinstance(t, dict) and t.get("kind") in ("PLANT", "COOP", "PASTURE"):
            used += 1
    return used

def get_target_crops_by_phase(phase, prices, state):
    """Devuelve {crop: tope_de_tiles} segun el greedy real (rentabilidad
    actual + restricciones de agua/tierra/dinero)."""
    optimizacion = optimizar_cultivos_io(phase, state)

    # AJUSTE V7.3: ANTES, budget=0 en el optimizador (frecuente con la
    # reserva vieja) devolvia {} y esto caia directo a un fallback de
    # "solo WHEAT, 5 tiles", ignorando por completo CARROT -- que en la
    # mayoria de los precios de mercado tiene MEJOR crop_score que WHEAT
    # (semilla mas cara pero madura mas rapido y vende mas caro). Ese
    # fallback nunca diversificaba aunque hubiera dinero de sobra unos
    # turnos despues, porque el problema real (poca caja) rara vez se
    # resolvia solo con WHEAT. AHORA el piso de emergencia SIEMPRE incluye
    # CARROT ademas de WHEAT (mismo piso barato que ya se usaba para
    # mid/late), y esos mismos casos de "money bajo" ya NO dependen de que
    # optimizacion haya quedado vacia -- se evaluan siempre.
    if not optimizacion:
        return {"WHEAT": 5, "CARROT": 3}

    if state.money < 500:
        # Piso minimo garantizado (barato, rapido) fusionado CON lo que el
        # greedy si encontro -- nunca lo reemplaza, solo asegura que WHEAT
        # y CARROT nunca queden en 0 tiles mientras la caja es chica.
        floor = {"WHEAT": 5, "CARROT": 3}
        merged = dict(optimizacion)
        for crop, cap in floor.items():
            merged[crop] = max(merged.get(crop, 0), cap)
        return merged

    return optimizacion

def plan_seed_purchases(state, target_crops, money_left):
    """
    target_crops es el dict {crop: tope_de_tiles} del optimizador.
    ANTES: solo reponia 1 semilla cada vez que el stock llegaba a 0 -- con
    varias manos queriendo plantar el mismo cultivo el mismo turno, solo
    una podia plantar (las demas se quedaban sin semilla disponible),
    desperdiciando el paralelismo de tener multiples manos.
    AHORA: compra lo suficiente para que varias unidades (farmer + hands)
    puedan plantar en paralelo, sin pasarse del tope de tiles restante.
    """
    orders = []
    n_unidades = 1 + len(state.hands_pos)

    for crop, cap in target_crops.items():
        tope_restante = cap - count_crop_on_board(state.board, crop)
        if tope_restante <= 0:
            continue

        seed_cost = CROP_DATA[crop]["seed_cost"]
        current_seed = state.seeds.get(crop, 0)
        target_seed = min(n_unidades, tope_restante)
        if current_seed >= target_seed:
            continue

        need = target_seed - current_seed
        cost = need * seed_cost
        if money_left >= cost:
            orders.append(MarketActions.buy_seed(crop, need))
            money_left -= cost
        elif money_left >= seed_cost:
            affordable = int(money_left // seed_cost)
            if affordable > 0:
                orders.append(MarketActions.buy_seed(crop, affordable))
                money_left -= affordable * seed_cost

    return orders, money_left

# AJUSTE V49 -- ANALISIS DE ESCALA CON PARTIDA REAL (93788570): perdimos
# por casi el doble de dinero pese a que TODOS los rubros (cultivos y
# animales) dieron positivo -- el problema no era rentabilidad, era
# escala. Comparando tablero a tablero (dato PUBLICO, visible para ambos
# jugadores): el rival ya tenia 4 COW + 2 SHEEP establecidos el DIA 1,
# mientras nosotros recien colocamos el primer COW el dia 10 -- 9 dias de
# ventaja compuesta que nunca se recupera en una temporada de 30 dias,
# porque los animales generan ingreso recurrente por el resto del
# juego. Ademas, con menos animales generamos menos FERTILIZER gratis
# como subproducto: confirmado que solo el 36% de nuestro fertilizante
# vino gratis (110 recolectados vs 194 comprados) contra el 100% gratis
# que logramos ver en otra partida donde si escalamos bien -- asi que
# arreglar esto tambien mejora el margen de FERTILIZER en cascada, sin
# necesidad de tocar esa logica por separado.
# Se cambian LOS DOS valores juntos a proposito: bajar solo
# ANIMAL_START_DAY no alcanza, porque con ANIMAL_RAMP_PER_DAY=0.5 el
# primer animal (ramp_target=1) recien se habilita 2 dias despues del
# start_day (int(2*0.5)=1) -- osea que ANIMAL_START_DAY=1 solo, sin subir
# el ramp, seguiria dejando el primer animal para el dia 3. Con los dos
# cambios juntos, el primer animal se habilita el dia 2.
# LA SEGURIDAD REAL sigue intacta y sin tocar: capacity_ceiling (mas
# abajo) ya limita el target a lo que la mano de obra disponible puede
# atender de verdad (FEED+CARE), independientemente de este ramp -- asi
# que apurar el arranque no reintroduce el bug historico de animales
# comprados que se mueren de hambre por falta de manos.
ANIMAL_START_DAY = 1       # ANTES: 5. Evidencia real: el rival establecio 4 COW+2 SHEEP el dia 1.
# AJUSTE V59 -- BUG DE FONDO ENCONTRADO AL INVESTIGAR POR QUE EL GASTO EN
# FERTILIZER NO BAJABA (pedido del usuario): ANIMAL_CAP=40 nunca era el
# freno real -- confirmado con 3 partidas, el rebano se estancaba en 11-12
# animales desde el dia ~20, con capacity_ceiling y cantidad de PASTURE de
# sobra (100+ y 18-20 respectivamente) y plata de sobra ($30k+). La causa
# real: animal_score cae a -inf correctamente a partir del dia 20, porque
# ya no queda runway de temporada para que un animal COMPRADO ESE DIA
# alcance a pagarse (COW necesita 8 dias solo para la primera produccion).
# Esa exclusion esta BIEN, no se toca -- el problema es que tardabamos
# hasta el dia 20 en llegar a esos 11-12, dejando muy poca ventana real
# para seguir sumando antes de que se cierre sola. La unica forma real de
# tener MAS animales (y por lo tanto mas FERTILIZER gratis en cascada) es
# establecerlos mas rapido en la PRIMERA MITAD del juego, no subir un tope
# que ya sobra. Se duplica el ritmo de la rampa para llegar antes a un
# rebano mas grande, dentro de la ventana de tiempo que todavia rinde.
ANIMAL_RAMP_PER_DAY = 2.0  # ANTES: 1.0.
# AJUSTE V53 -- EVIDENCIA COMPETITIVA REAL: el jugador #1 del ranking
# completo llega a $0 de FERTILIZER comprado (confirmado con su propio
# P&L real, comparado contra el #2). Ya habiamos confirmado que nuestra
# mano de obra real permite sostener 130+ animales en los momentos
# analizados -- muy por encima de este tope de 10. Como capacity_ceiling
# (la proteccion real basada en mano de obra disponible, ver mas abajo)
# sigue exactamente igual, subir este numero no reintroduce el bug
# historico de animales sin atender -- solo deja de ser un freno
# artificial cuando la mano de obra de sobra lo permite.
ANIMAL_CAP = 40             # ANTES: 10. Evidencia real: el #1 del ranking llega a $0 de fertilizante comprado.

def total_animal_target(state):
    """Cuantos animales DEBERIAMOS tener para este dia, segun la rampa.

    AJUSTE V25 -- BUG REAL: ANTES esto era una rampa PURAMENTE temporal
    (0.5 animales nuevos por dia desde el dia 5), totalmente ciega a si
    hay manos de sobra para atenderlos. Confirmado con una partida real:
    se compraron 2 SHEEP ($1000) que terminaron con ganancia neta -1000 --
    perdida total, ingreso $0 -- consistente con que se escaparon por
    falta de alimentacion 2 dias seguidos (cada animal necesita FEED+CARE
    todos los dias, compitiendo por las mismas manos que ya estan
    regando cultivos). Comprar un animal mas alla de la capacidad real
    disponible no es diversificacion, es tirar la plata: un animal
    descuidado no rinde nada y el costo de compra se pierde entero.
    AHORA el objetivo tambien se topa por la capacidad de sobra real
    (turnos de riego disponibles menos lo que ya consumen los cultivos
    plantados), asi nunca se compra un animal que sabemos de antemano
    que no vamos a poder atender.
    """
    dias_desde_inicio = max(state.day - ANIMAL_START_DAY, 0)
    ramp_target = int(dias_desde_inicio * ANIMAL_RAMP_PER_DAY)

    capacity = state.get_watering_capacity()
    tiles_used = _tiles_in_use(state)
    # Cada animal necesita ~2 acciones/dia (FEED + CARE) para rendir bien
    # y no arriesgarse a escapar. Lo que sobra despues de lo que ya
    # consumen los cultivos es lo maximo de animales que tiene sentido
    # sostener hoy.
    capacity_ceiling = max(0, (capacity - tiles_used) // 2)

    return min(ramp_target, ANIMAL_CAP, capacity_ceiling)

def count_animal_structures(state, structure_kind):
    return sum(
        1 for _x, _y, t in iter_tiles(state.board)
        if isinstance(t, dict) and t.get("kind") == structure_kind
    )

def plan_animal_purchase(state, phase, money_left):
    """
    ANTES (v7.2): compraba como maximo 2 GOOSE y 1 COW en TODA la partida.
    ANTES (v24): ya escalaba con una rampa, pero dentro de cada tipo de
    estructura compartida (PASTURE la comparten COW y SHEEP) siempre
    elegia la especie #1 del ranking para CUALQUIER cupo libre -- "el
    ganador se lleva todo". Con datos de una partida real esto se
    confirmo: COW gano la carrera de ranking apenas quedaban pocos dias
    (SHEEP necesita 21 dias para alcanzar su yield maximo vs 18 de COW,
    asi que a partir de mitad de temporada COW SIEMPRE punteaba) y se
    quedo con el 100% de los pasture, terminando en 0 SHEEP / 0 WOOL en
    toda la temporada -- pese a que WOOL es el segundo producto animal
    mas caro y diversificar entre MILK y WOOL evita que vender mucha
    leche crashee el propio precio sin ninguna alternativa.
    AHORA: dentro de cada grupo de especies que comparten estructura, el
    proximo cupo se lo lleva la que menos unidades tiene todavia (no la
    de mejor score a secas) -- mismo principio de diversification_cap
    que ya se usa para cultivos, aplicado a animales.
    """
    orders = []

    if state.day < EARLY_INVESTMENT_MIN_DAY:
        return orders, money_left

    days_remaining = max(TOTAL_SEASON_DAYS - state.day, 0)
    ranked = ranked_animals(state.market_prices, days_remaining)
    if not ranked:
        return orders, money_left

    target_total = total_animal_target(state)
    # AJUSTE V37b: usar el conteo de "pipeline" (colocados + esperando en
    # el shed), no solo colocados -- si no, el codigo cree que faltan
    # animales cuando en realidad ya hay varios comprados sin colocar
    # todavia, y sigue comprando mas sin necesidad (ver comentario largo
    # en count_animals_in_pipeline).
    if count_animals_in_pipeline(state) >= target_total:
        return orders, money_left

    empty_structures = find_empty_animal_structures(state.board)
    if not empty_structures:
        return orders, money_left  # no hay donde colocarlo todavia -- primero hay que construir

    # AJUSTE V37b: una estructura vacia no significa que haya CUPO real
    # si ya hay un animal de esa especie esperando en el shed para
    # ocuparla -- sin este descuento, el codigo seguia comprando mas
    # aunque ya hubiera 4-6 animales amontonados sin colocar (confirmado
    # en simulacion: racha de 16.7 dias con COW/SHEEP sin colocar).
    shed_pendientes_por_especie = {
        a: state.shed.get(a, 0) for a in ANIMAL_DATA
    }
    cupos_libres_reales = max(0, len(empty_structures) - sum(shed_pendientes_por_especie.values()))
    if cupos_libres_reales <= 0:
        return orders, money_left

    wheat_price = state.market_prices.get("WHEAT", CROP_DATA["WHEAT"]["base_price"])

    # AJUSTE V31: mismo principio que en optimizar_cultivos_io -- el score
    # de comprar UN ANIMAL MAS usa el precio descontado por lo que YA
    # tenemos vivo de esa especie (todos los productos animales son
    # "fragiles": WOOL/MILK con above_target 3.2/1.6, EGG con 0.20 es
    # mucho mas tolerante). Confirmado con la partida del jugador #1 del
    # ranking: gano $45302 con solo 4 SHEEP -- consistente con mantener
    # la oferta de WOOL baja a proposito para no reventar su precio.
    def _animal_price_for_planning(a):
        raw = state.market_prices.get(ANIMAL_PRODUCT[a], ANIMAL_DATA[a]["base_price"])
        product = ANIMAL_PRODUCT[a]
        if product not in FRAGILE_RESOURCES:
            return raw
        already = count_species_alive(state, a) * ANIMAL_DATA[a]["max_yield"]
        return _saturation_adjusted_price(product, raw, already)

    scores_por_especie = {
        a: animal_score(a, _animal_price_for_planning(a), days_remaining, wheat_price)
        for a in ranked
    }

    for species in ranked:
        # AJUSTE V31: ranked_animals solo descarta score==-inf (imposible
        # llegar ni a la primera cosecha). Pero un score NEGATIVO-Y-FINITO
        # significa "alimentarlo cuesta mas de lo que devuelve" -- y antes
        # se compraba igual con tal de que hubiera estructura libre. Ahora
        # se exige score > 0 antes de sumar una unidad mas.
        if scores_por_especie[species] <= 0:
            continue

        structure_needed = ANIMAL_DATA[species]["structure"]
        hay_estructura_libre = any(
            state.board[y][x].get("kind") == structure_needed for x, y in empty_structures
        )
        if not hay_estructura_libre:
            continue

        # Especies viables (score > -inf) que compiten por el MISMO tipo
        # de estructura: si hay mas de una, el cupo se lo lleva la que
        # menos tiene, no automaticamente la de mejor score.
        # AJUSTE V31: ANTES esto forzaba alternancia ciega (la especie con
        # MENOS unidades siempre se lleva el proximo cupo), sin importar
        # cuanto peor rindiera. Ahora que scores_por_especie YA descuenta
        # la saturacion de mercado (ver _animal_price_for_planning), el
        # score de cada especie refleja tanto su rentabilidad base como
        # cuanto ya tenemos de ella -- alcanza con elegir directamente la
        # de mejor score entre las viables, sin un mecanismo aparte de
        # alternancia forzada (que antes podia empujar a comprar la
        # especie mas debil solo por "tener menos").
        rivales = [a for a in ranked if ANIMAL_DATA[a]["structure"] == structure_needed
                   and scores_por_especie.get(a, float("-inf")) > 0]
        # AJUSTE V40 -- BUG REAL CONFIRMADO CON PARTIDA REAL: COW gana la
        # PRIMERA compra casi siempre (su ciclo mas corto amortiza el
        # costo de semilla mas rapido en el score temprano de la
        # temporada), y la diversificacion por saturacion (V31) solo
        # corrige DESPUES de que COW ya acumulo varias unidades -- para
        # cuando SHEEP por fin gana la comparacion de score, puede que ya
        # sea tarde para establecerse (necesita 6 dias solo para la
        # primera cosecha). Confirmado con partida real: 3 COW y 3 SHEEP
        # comprados (mismo costo cada uno), COW gano $3845 de ganancia
        # neta, SHEEP perdio los $1500 completos -- consistente con que
        # SHEEP se establecio demasiado tarde para aprovechar el resto de
        # la temporada. Ahora, si algun rival TODAVIA no tiene ni una
        # unidad establecida (ni colocada ni esperando en el shed) y su
        # score es viable, se prioriza ANTES que seguir apilando en la
        # especie que ya tiene ventaja -- diversificar a tiempo importa
        # mas que maximizar el score puntual de la compra de hoy.
        sin_establecer = [a for a in rivales if count_species_alive(state, a) == 0]
        if sin_establecer:
            especie_elegida = max(sin_establecer, key=lambda a: scores_por_especie[a])
        elif rivales:
            especie_elegida = max(rivales, key=lambda a: scores_por_especie[a])
        else:
            especie_elegida = species

        cost = ANIMAL_DATA[especie_elegida]["seed_cost"]
        if money_left - cost >= GLOBAL_MONEY_RESERVE:
            orders.append(MarketActions.buy_animal(especie_elegida, 1))
            money_left -= cost
        break  # una compra por turno, para no arriesgar la reserva

    return orders, money_left

def plan_build_targets(state, phase):
    """
    ANTES: construia UNA sola estructura por especie fija segun la fase,
    y una vez que existiera CUALQUIER estructura de ese tipo, dejaba de
    construir mas -- imposible escalar mas alla de 1 corral por especie.
    AHORA: sigue construyendo estructuras nuevas mientras haya menos
    estructuras totales que el objetivo de la rampa (total_animal_target).
    """
    if state.day < EARLY_INVESTMENT_MIN_DAY:
        return []

    days_remaining = max(TOTAL_SEASON_DAYS - state.day, 0)
    ranked = ranked_animals(state.market_prices, days_remaining)
    if not ranked:
        return []

    target_total = total_animal_target(state)
    estructuras_existentes = count_animal_structures(state, "COOP") + count_animal_structures(state, "PASTURE")
    if estructuras_existentes >= target_total:
        return []

    # AJUSTE V31 -- BUG REAL ENCONTRADO (mismo patron que bug #10, pero
    # nunca se aplico aca): ANTES, "especie_prioritaria = ranked[0]" tomaba
    # SIEMPRE el animal #1 del ranking GLOBAL para decidir que estructura
    # construir. COW/SHEEP (PASTURE) casi siempre superan a GOOSE (COOP) en
    # score porque su producto base es mucho mas caro (MILK=160, WOOL=200
    # vs EGG=50) -- asi que NUNCA se construia un COOP, y GOOSE quedaba
    # excluido de la partida entera por mas que su score individual fuera
    # positivo. Esto es "el ganador se lleva todo" aplicado al paso PREVIO
    # a la compra (construir la estructura), y coincide EXACTO con los
    # datos reales: GOOSE con $0 de ingreso Y $0 de costo de compra en
    # toda la partida -- ni siquiera se intento comprar uno, porque nunca
    # hubo donde colocarlo. Ahora se prioriza construir el TIPO de
    # estructura (COOP o PASTURE) que menos representacion tiene todavia,
    # no automaticamente la del mejor score puntual.
    tipos_necesarios = sorted({ANIMAL_DATA[a]["structure"] for a in ranked})
    tipo_elegido = min(tipos_necesarios, key=lambda t: count_animal_structures(state, t))
    especie_prioritaria = next(a for a in ranked if ANIMAL_DATA[a]["structure"] == tipo_elegido)

    info = ANIMAL_DATA[especie_prioritaria]
    if state.money < info["seed_cost"] * 0.6:
        return []  # no comprometerse a construir si no alcanza para el animal despues

    structure = tipo_elegido
    empty_tiles = find_empty_tiles(state.board, exclude=shed_tiles(state.board_size))
    if not empty_tiles:
        return []

    x, y = nearest(state.farmer_pos, [(ex, ey) for ex, ey in empty_tiles])
    return [(x, y, structure)]

def plan_fertilizer_purchase(state, money_left):
    orders = []

    if state.day < EARLY_INVESTMENT_MIN_DAY:
        return orders, money_left

    # AJUSTE (pedido del usuario: no comprar recursos que no nos vamos a
    # alcanzar a usar en lo que queda de partida). Antes esto compraba
    # sin mirar cuantos dias quedaban -- ahora que FERTILIZER se puede
    # vender (ver NON_SELLABLE_SHED_ITEMS) ya no es plata directamente
    # perdida, pero sigue siendo un viaje de ida y vuelta innecesario
    # (comprar a un precio, revender a otro, con el spread perdido en el
    # medio) si ya no hay tiempo real de usarlo en un cultivo propio. En
    # la liquidacion final no tiene sentido seguir comprando.
    if _is_endgame_day(state.day):
        return orders, money_left

    n_melon = sum(
        1 for _x, _y, t in iter_tiles(state.board)
        if isinstance(t, dict) and t.get("kind") == "PLANT" and t.get("crop") == "MELON"
    )
    n_strawberry = sum(
        1 for _x, _y, t in iter_tiles(state.board)
        if isinstance(t, dict) and t.get("kind") == "PLANT" and t.get("crop") == "STRAWBERRY"
    )
    n_fertilizable = n_melon + n_strawberry

    if n_fertilizable == 0:
        return orders, money_left

    current_fertilizer = state.shed.get("FERTILIZER", 0)

    # AJUSTE V52 -- BUG REAL CONFIRMADO CON PARTIDA REAL (93891428): el
    # piso fijo de 3 unidades quedo chico para la escala que empezamos a
    # manejar despues de V49/V50/V51 (mas tierra, mas manos, mas
    # MELON/STRAWBERRY plantados). Con mas tiles fertilizables el consumo
    # de FERTILIZER es mas rapido, asi que un piso de 3 se vaciaba y
    # disparaba esta funcion una y otra vez EN EL MISMO DIA -- confirmado
    # con datos reales: 9 compras separadas en un solo dia (~$909 en
    # total), justo el mismo dia que tambien se compraba un animal por
    # primera vez ($1000) -- la combinacion vacio la caja de $2088 a
    # $336. Cada compra individual se veia "seria" en el momento (paso el
    # chequeo de presupuesto), pero repetida muchas veces en el dia el
    # efecto acumulado fue grande. Ahora el piso escala con la cantidad
    # real de tiles de MELON+STRAWBERRY (con un tope para no comprometer
    # de mas en una sola vez) -- asi se compra en lotes mas grandes con
    # MENOS frecuencia en vez de recomprar de a poquito muchas veces.
    piso = max(3, min(15, n_fertilizable))
    if current_fertilizer >= piso:
        return orders, money_left

    # AJUSTE (auditoria de hardcodeo): ANTES "cost = 100" asumia el precio
    # BASE fijo del fertilizante (PRICE_TABLE["FERTILIZER"]["base"]=100),
    # ignorando el precio REAL de mercado -- que puede subir si ya
    # compramos antes (la curva de precio de FERTILIZER tambien reacciona
    # a la oferta/demanda, igual que cualquier otro producto). Con precio
    # base fijo, el chequeo de presupuesto podia ser optimista de mas si
    # el precio real ya habia subido. Ahora se lee el precio real.
    cost = state.market_prices.get("FERTILIZER", PRICE_TABLE["FERTILIZER"]["base"])
    faltante = piso - current_fertilizer
    # tope por llamada (no vaciar todo el presupuesto en una sola orden
    # aunque el piso este alto) -- balance entre "menos compras
    # separadas" (el objetivo de este fix) y "no arriesgar de mas en un
    # solo turno".
    qty = min(faltante, 5)
    if money_left - cost * qty >= GLOBAL_MONEY_RESERVE:
        orders.append(MarketActions.buy_product("FERTILIZER", qty))
        money_left -= cost * qty

    return orders, money_left

def count_animals_alive(state):
    """AJUSTE V37 -- BUG REAL: ANTES contaba tambien animales comprados
    pero SIN COLOCAR (esperando en el shed), como si ya necesitaran
    comer -- pero FEED solo funciona sobre animales YA COLOCADOS en el
    tablero (un animal en el shed no tiene tile propia donde alguien lo
    alimente). Si por cualquier motivo un animal queda atascado en el
    shed sin colocarse (coordinacion de pickup, pathing, etc.), el
    codigo seguia comprando trigo para el turno tras turno sin que ese
    trigo se usara jamas -- coincide con una partida real donde se
    gastaron $9369 en trigo de alimentacion mientras el costo de compra
    de TODOS los animales (COW/SHEEP/GOOSE) figura en $0. Ahora solo se
    cuentan los animales YA COLOCADOS (los que de verdad consumen trigo
    via FEED) para dimensionar la compra."""
    count = 0
    for _x, _y, t in iter_tiles(state.board):
        if isinstance(t, dict) and t.get("kind") in ("COOP", "PASTURE") and t.get("animal") is not None:
            count += 1
    return count

def count_animals_in_pipeline(state):
    """AJUSTE V37b -- distinto de count_animals_alive (que ahora solo
    cuenta colocados, para dimensionar trigo). Esta version SI incluye
    los que estan comprados pero todavia esperando en el shed, porque
    para decidir si conviene COMPRAR UNO MAS necesitamos saber cuantos
    ya estan "en camino", no solo cuantos ya estan produciendo. Sin esto
    (bug real encontrado en simulacion): el codigo seguia comprando mas
    animales creyendo que hacia falta, mientras varios ya comprados se
    amontonaban sin colocar en el shed -- confirmado con una racha real
    de 16.7 dias seguidos con hasta 6 animales (4 COW + 2 SHEEP) sentados
    en el shed sin colocarse nunca hasta el final de la partida."""
    count = state.shed.get("GOOSE", 0) + state.shed.get("COW", 0) + state.shed.get("SHEEP", 0)
    for _x, _y, t in iter_tiles(state.board):
        if isinstance(t, dict) and t.get("kind") in ("COOP", "PASTURE") and t.get("animal") is not None:
            count += 1
    return count

def count_species_alive(state, species):
    """AJUSTE V25: version por especie de count_animals_alive. Necesaria
    para diversificar entre especies que comparten el mismo tipo de
    estructura (COW y SHEEP ambas usan PASTURE) -- sin esto no hay forma
    de saber cual de las dos esta 'atrasada' y merece el proximo cupo.
    Cuenta shed + tablero A PROPOSITO: para decidir QUE COMPRAR, importa
    tanto lo ya colocado como lo ya pagado-y-esperando (V31/V40 mas
    abajo) -- no tiene sentido seguir comprando mas de una especie que ya
    tiene unidades sin colocar en el shed.
    NO USAR esto para decidir a quien darle el PROXIMO PICKUP -- para eso
    esta count_species_on_board (ver mas abajo)."""
    count = state.shed.get(species, 0)
    for _x, _y, t in iter_tiles(state.board):
        if isinstance(t, dict) and t.get("animal") == species:
            count += 1
    return count

def count_species_on_board(state, species):
    """AJUSTE V46 -- BUG REAL EN MI PROPIO FIX (V42), CONFIRMADO CON
    PARTIDA REAL: la eleccion de que especie levantar del shed
    (place_species) usaba count_species_alive, que suma shed + tablero.
    Eso genera una paradoja: cuanto MAS se acumula una especie SIN
    colocar en el shed, mas ALTO aparenta su conteo, y MENOS prioridad de
    pickup recibe -- exactamente al reves de lo que hace falta. Confirmado
    viendo el replay real turno a turno: SHEEP entro al shed el dia 13,
    y por asumir mal la comparacion, `place_species` siguio favoreciendo
    a COW (con menor cantidad en el shed en ese momento) turno tras turno
    mientras SHEEP se quedaba pegado sin ni un solo PICKUP -- 10 dias de
    demora, y para cuando por fin se coloco (dia 23) ya no le alcanzo el
    resto de la temporada para completar ni una cosecha (ver SHEEP con
    $0 de ingreso pese al costo pagado). Esta version SOLO cuenta lo que
    ya esta fisicamente establecido en el tablero, ignorando el backlog
    del shed -- asi el pickup prioriza a la especie que de verdad esta
    mas atrasada en establecerse, sin que su propio backlog jueje en
    contra."""
    count = 0
    for _x, _y, t in iter_tiles(state.board):
        if isinstance(t, dict) and t.get("animal") == species:
            count += 1
    return count

def tiene_animal_vivo(state):
    return count_animals_alive(state) > 0

SEED_FLOOR = 25  # nunca vaciar la caja mas alla de esto, salvo emergencia real de hambre

def plan_wheat_purchase_for_feed(state, money_left):
    """
    ANTES: esta compra no respetaba ningun piso de dinero (a proposito,
    para nunca dejar un animal sin comer). El problema real: si esto
    vaciaba la caja a $0 y en ese momento no habia NADA plantado, la
    granja quedaba completamente parada -- ni para la semilla mas barata
    ($10 de WHEAT) alcanzaba. Confirmado con datos reales: 12 dias
    seguidos (18-29) sin un solo cultivo en el tablero.
    AHORA: se protege un piso minimo (SEED_FLOOR) para poder seguir
    plantando algo, EXCEPTO cuando el trigo en el shed esta en CERO --
    ahi si es una emergencia real (el animal se puede escapar por hambre
    en 2 dias) y se sigue priorizando por sobre cualquier otra cosa.
    """
    orders = []
    n_animales = count_animals_alive(state)
    if n_animales == 0:
        return orders, money_left  # nadie que alimentar todavia

    # AJUSTE (pedido del usuario: no comprar recursos que no nos vamos a
    # alcanzar a usar). El colchon de "2 dias" no tiene sentido si a la
    # partida le quedan MENOS de 2 dias reales -- comprar de mas ahi es
    # plata inmovilizada en algo que ya no va a llegar a alimentar a
    # nadie antes de que termine la temporada. Se limita el colchon al
    # minimo entre el estandar (2) y los dias que realmente quedan.
    dias_restantes = max(TOTAL_SEASON_DAYS - state.day, 0)
    colchon = min(2, dias_restantes)
    target_stock = n_animales + colchon
    current = state.shed.get("WHEAT", 0)
    if current >= target_stock:
        return orders, money_left

    needed = target_stock - current
    price = state.market_prices.get("WHEAT", CROP_DATA["WHEAT"]["base_price"])
    if price <= 0:
        return orders, money_left

    es_emergencia = current == 0  # sin nada de trigo -- riesgo real de perder el animal

    if es_emergencia:
        # La emergencia real (animal en riesgo de escaparse por hambre)
        # se atiende SIEMPRE, incluso en la liquidacion final -- perder el
        # animal es peor que gastar en trigo que capaz no se termine de
        # usar del todo.
        affordable = int(money_left // price)
        qty = min(needed, affordable)
        if qty > 0:
            orders.append(MarketActions.buy_product("WHEAT", qty))
            money_left -= qty * price
        return orders, money_left

    if _is_endgame_day(state.day):
        return orders, money_left

    # No es emergencia (ya tenemos algo de colchon) -- respetar el piso
    # minimo para que la granja nunca se quede sin poder plantar nada.
    usable = max(0, money_left - SEED_FLOOR)
    cost = needed * price
    if usable >= cost:
        orders.append(MarketActions.buy_product("WHEAT", needed))
        money_left -= cost
    else:
        affordable = int(usable // price)
        if affordable > 0:
            orders.append(MarketActions.buy_product("WHEAT", affordable))
            money_left -= affordable * price

    return orders, money_left

def plan_market_actions(state, memory):
    memory.update(state.market_prices)

    # AJUSTE V43 -- AUDITORIA DE HARDCODEO REAL: este turno especial
    # "day==0 and hour==0" compraba una lista FIJA de semillas
    # (WHEAT 3, CARROT 2, MELON 1, STRAWBERRY 1) con umbrales de plata
    # fijos, totalmente ciega al precio REAL de mercado de ese cultivo en
    # ESA partida especifica y a si crop_score realmente lo justificaba
    # ese dia. Confirmado con una partida real: STRAWBERRY quedo en $0 de
    # costo de semilla Y $0 de ingreso en toda la temporada -- consistente
    # con que esta compra fija (que no pasa por ranked_crops/crop_score)
    # puede intentar comprar un cultivo que el motor de mercado rechaza o
    # que crop_score ya sabe que no conviene con los precios reales de esa
    # partida, sin que el resto del codigo (que SI es dinamico) tenga
    # forma de anticiparlo o corregirlo. Ademas el "plan" que devolvia
    # este atajo forzaba plantable_crops/crop_plan a un piso fijo
    # {WHEAT:5, CARROT:3}, dejando afuera MELON/STRAWBERRY del sembrado
    # aunque se hubieran comprado sus semillas -- plata pagada sin usar.
    # AHORA el turno day==0/hour==0 ya NO tiene atajo propio: cae
    # directo al camino normal de aqui abajo (get_target_crops_by_phase +
    # plan_seed_purchases + plan_hire_optimizado, etc.), que ya calcula
    # que sembrar y cuanto usando el precio de mercado REAL de esa
    # partida (via ranked_crops/crop_score) en vez de una lista fija. En
    # el primerisimo turno esto compra menos semilla que antes (todavia
    # no hay manos contratadas, asi que plan_seed_purchases dimensiona
    # para 1 sola unidad) -- pero se autoescala solo en los turnos
    # siguientes del mismo dia 0 a medida que las manos contratadas se
    # reflejan en el estado, sin necesitar ningun numero fijo aparte.

    phase = state.get_game_phase()

    # AJUSTE V24 -- CAMBIO CRITICO: ANTES, un error en CUALQUIERA de estas
    # funciones (target_crops, sell_orders, wheat/seed/hire/animal/fert/
    # land) hacia que la excepcion se propagara hasta el try/except de
    # agent(), tirando abajo el turno ENTERO: cero acciones de las unidades
    # (todo PASS) y CERO ordenes de mercado, sin importar que el resto de
    # la logica funcionara perfecto. Con $3000 de plata inicial (dato de
    # config real que antes no teniamos) el bot NO deberia haber tenido
    # problema de presupuesto para diversificar mas alla de WHEAT -- el
    # hecho de que la partida real termino sembrando SOLO WHEAT durante
    # toda la temporada, con semillas de MELON/CARROT/STRAWBERRY ya
    # compradas el turno 0 y sin usar NUNCA, es la firma de una excepcion
    # silenciosa en alguna de estas funciones (probablemente relacionada a
    # MELON/CARROT/STRAWBERRY, ya que WHEAT siguio funcionando) que
    # nukeaba el turno completo apenas se intentaba usar esos cultivos.
    # AHORA cada sub-calculo esta aislado: si UNO falla, se degrada solo
    # ESA parte (orders=[] y money_left sin tocar) y el resto del turno
    # sigue funcionando con normalidad -- ademas cada fallo se imprime con
    # su nombre para poder diagnosticarlo en la proxima partida en vez de
    # quedar completamente a ciegas.
    def _safe(label, fn, *args):
        try:
            return fn(*args)
        except Exception as e:
            print(f"ERROR aislado en {label}: {e}")
            return None

    target_crops = _safe("get_target_crops_by_phase", get_target_crops_by_phase, phase, state.market_prices, state)
    if target_crops is None:
        target_crops = {"WHEAT": 5, "CARROT": 3}  # degradacion segura, nunca WHEAT-only puro
    plantable_crops = [c for c in target_crops if state.seeds.get(c, 0) > 0]

    money_left = state.money

    sell_result = _safe("plan_sales_intelligent", plan_sales_intelligent, state, memory)
    sell_orders = sell_result if sell_result is not None else []

    # Orden de prioridad: primero lo que evita perder lo que ya invertimos
    # (alimentar animales vivos) y lo esencial para seguir produciendo
    # (semillas, mano de obra barata). Las compras grandes (animal nuevo,
    # fertilizante, tierra) van al final y exigen dejar una RESERVA minima
    # despues de pagar -- asi nunca se vacia la caja de un solo golpe.
    # Cada llamada aislada con _safe: si una falla, esa categoria queda
    # vacia (money_left intacto) pero las demas siguen procesandose.
    def _safe_orders(label, fn, *args):
        result = _safe(label, fn, *args)
        if result is None:
            return [], money_left
        return result

    wheat_orders, money_left = _safe_orders("plan_wheat_purchase_for_feed", plan_wheat_purchase_for_feed, state, money_left)
    land_orders, money_left = _safe_orders("plan_land_expansion", plan_land_expansion, state, money_left)
    seed_orders, money_left = _safe_orders("plan_seed_purchases", plan_seed_purchases, state, target_crops, money_left)
    hire_orders, money_left = _safe_orders("plan_hire_optimizado", plan_hire_optimizado, state, money_left)
    animal_orders, money_left = _safe_orders("plan_animal_purchase", plan_animal_purchase, state, phase, money_left)
    fert_orders, money_left = _safe_orders("plan_fertilizer_purchase", plan_fertilizer_purchase, state, money_left)

    build_targets = _safe("plan_build_targets", plan_build_targets, state, phase) or []

    days_remaining = max(TOTAL_SEASON_DAYS - state.day, 0)
    ranked_species = ranked_animals(state.market_prices, days_remaining)

    # Que especie priorizar para PICKUP/PLACE este turno: si ya hay algun
    # animal esperando en el shed (recien comprado), ese primero; si no,
    # el mejor rankeado (para saber que estructura construir a continuacion).
    #
    # AJUSTE V42 -- BUG REAL, CAUSA RAIZ DE SHEEP EN $0 DE INGRESO PESE A
    # COMPRARSE Y APARECER EN EL SHED: ANTES esto recorria ANIMAL_DATA en
    # su orden de DEFINICION (GOOSE, COW, SHEEP) y se quedaba con la
    # PRIMERA especie que tuviera stock en el shed. Como COW entra al
    # shed constantemente (se compra seguido y su ciclo es corto) y
    # aparece ANTES que SHEEP en el diccionario, "place_species" resultaba
    # casi siempre "COW" mientras hubiera CUALQUIER COW esperando --sin
    # importar cuanto tiempo llevara SHEEP ahi parado. Esto es DISTINTO
    # de los bugs de "el ganador se lleva todo" ya resueltos para decidir
    # que especie COMPRAR (V40) y que estructura CONSTRUIR (V31): esta
    # variable es la que de verdad controla el PICKUP fisico del shed
    # (ver _shed_action), asi que aunque V40 compre SHEEP correctamente y
    # V31 construya su PASTURE correctamente, ninguna unidad lo llegaba a
    # levantar del shed para colocarlo -- se quedaba pagado ($500/u) y
    # nunca colocado, nunca alimentado, nunca cosechado.
    #
    # AJUSTE V46 -- ESTE MISMO FIX TENIA UN BUG PROPIO, CONFIRMADO CON
    # PARTIDA REAL: la primera version comparaba con count_species_alive
    # (shed + tablero), lo que crea una paradoja -- cuanto MAS se acumula
    # una especie sin colocar, mas ALTO aparenta su conteo, y MENOS
    # prioridad de pickup recibe (justo al reves de lo que hace falta).
    # Confirmado turno a turno: SHEEP entro al shed dia 13 con 3 unidades
    # esperando: al superar en cantidad a COW (que tenia menos en el shed
    # en ese momento), "perdia" la comparacion y quedaba sin ni un solo
    # PICKUP durante dias. Recien se coloco el dia 23 -- demasiado tarde
    # para completar una cosecha antes de que termine la temporada.
    # AHORA se compara solo lo YA ESTABLECIDO EN EL TABLERO
    # (count_species_on_board), ignorando el backlog del shed -- asi el
    # propio atraso en colocarse no juega en contra de la especie que
    # justamente necesita colocarse.
    place_species = None
    candidatos_en_shed = [sp for sp in ANIMAL_DATA if state.shed.get(sp, 0) > 0]
    if candidatos_en_shed:
        place_species = min(candidatos_en_shed, key=lambda sp: count_species_on_board(state, sp))
    if place_species is None and ranked_species:
        place_species = ranked_species[0]

    # AJUSTE V7.3: ANTES se concatenaba en el orden
    # sell+wheat+seed+hire+animal+fert+land y se cortaba a los primeros 10.
    # sell_orders puede llegar a 8 (uno por producto distinto en el shed) y
    # seed_orders hasta 5 mas -- eso solo ya son 13, MAS que el limite real
    # de 10. Resultado: en cuanto la granja empezaba a vender varios
    # productos a la vez, hire_orders/animal_orders/land_orders quedaban
    # SIEMPRE afuera de la lista (nunca se ejecutaban), justo las compras
    # de mayor apalancamiento (mas manos = mas agua = mas tierra usable =
    # mas plata). AHORA se acota cuanto puede ocupar cada categoria ANTES
    # de concatenar, dejando espacio reservado para mano de obra, tierra y
    # animales en cada turno, en vez de que la venta se los coma enteros.
    # AJUSTE V25 -- BUG REAL ENCONTRADO CON DATOS DE PARTIDA: el fix
    # anterior (V7.3) le puso topes fijos a sell/seed para no comerse
    # todo el cupo, pero la suma de topes de las categorias restantes
    # (sell<=5 + wheat<=1 + hire<=4 + land<=1 + animal<=1 + seed<=3 = 15)
    # SIGUE superando el limite real de 10 -- y fert_orders, al quedar
    # ULTIMA en la concatenacion, se descartaba PRACTICAMENTE SIEMPRE en
    # el corte final. Confirmado con una partida real: $0 de fertilizante
    # comprado en TODA la temporada pese a tener MELON y STRAWBERRY (los
    # dos cultivos que mas se benefician de fertilizar) en juego casi
    # todo el tiempo -- plan_fertilizer_purchase generaba la orden cada
    # vez, pero jamas sobrevivia al recorte. Un simple "cortar a los
    # primeros N" siempre termina castigando a quien quede ULTIMO en la
    # lista, sea cual sea -- ya paso con hire/land/animal antes, y ahora
    # le toco a fertilizante. En vez de seguir jugando a las sillas con
    # el orden, ahora se reparte tipo round-robin: cada categoria con
    # ordenes pendientes cede una orden por vuelta, garantizando que
    # NINGUNA categoria activa quede en cero de forma sistematica.
    def _interleave_orders(category_lists, limit):
        result = []
        queues = [list(c) for c in category_lists if c]
        while queues and len(result) < limit:
            next_queues = []
            for q in queues:
                if len(result) >= limit:
                    next_queues.append(q)
                    continue
                result.append(q.pop(0))
                if q:
                    next_queues.append(q)
            queues = next_queues
        return result

    market_orders = _interleave_orders(
        [hire_orders, land_orders, animal_orders, fert_orders, wheat_orders, seed_orders, sell_orders],
        MAX_MARKET_ORDERS_PER_TURN,
    )

    plan = {
        "plantable_crops": plantable_crops,
        "crop_plan": list(target_crops.items()),  # [(crop, tope_de_tiles), ...] en orden de rentabilidad
        "build_targets": build_targets,
        "place_species": place_species,
        "want_wheat": tiene_animal_vivo(state),
        "want_fertilizer": True,
        "animal_species": tuple(ANIMAL_DATA.keys()),
        "wheat_pickup_qty": 3,
        "fertilizer_pickup_qty": 1,
        "is_endgame": _is_endgame_day(state.day),
    }

    return market_orders, plan

# ==========================================================
# search.py
# ==========================================================

TASK_PRIORITY = {
    "harvest": 0,
    "harvest_animal": 0,
    "shed_drop": 0,     # MISMA prioridad que cosechar -- antes competia en desventaja
                        # y el farmer podia quedarse cosechando para siempre sin nunca
                        # ir a vender (bug real encontrado con datos de partidas)
    "collect_fertilizer": 1,
    "dig": 2,
    # AJUSTE V25 -- BUG REAL: "plant" era la prioridad MAS BAJA de todas
    # (por debajo incluso de "build"/"fertilize"), asi que cada dia que
    # crecia el trabajo de mantenimiento (mas cultivos = mas riego, mas
    # animales = mas feed/care) quedaba MENOS lugar para plantar semilla
    # NUEVA -- justo lo opuesto a lo que conviene: no plantar cuesta un
    # dia entero de la ventana de maduracion de esa semilla, mientras que
    # construir o fertilizar solo mejora algo que YA esta produciendo.
    # Confirmado visualmente con el screenshot de una partida real: para
    # el dia 10/30 nuestra granja tenia un punado de tiles sembradas
    # mientras el rival ya cubria casi todo el terreno -- consistente con
    # que plantar quedaba sistematicamente pospuesto. Ahora compite al
    # mismo nivel que regar/alimentar (la urgencia real es comparable:
    # cada turno sin plantar es tiempo de temporada que esa semilla nunca
    # recupera).
    "water": 3,
    "feed": 3,
    "plant": 3,
    "care": 4,
    "place_animal": 5,
    "build": 6,
    "fertilize": 6,
}

def best_candidate(pos, candidates):
    if not candidates:
        return None

    fx, fy = pos

    def key(c):
        x, y, task, extra = c
        priority = TASK_PRIORITY.get(task, 99)
        # AJUSTE V35 -- BUG CRITICO REAL: "feed" (prioridad 3) nunca podia
        # ganarle a "harvest" (prioridad 0) en la seleccion global de
        # tarea, y en un campo grande de WHEAT SIEMPRE hay algo listo
        # para cosechar cerca -- asi que un animal podia quedarse sin
        # comer indefinidamente, sin importar cuan urgente estuviera.
        # Confirmado con trazas reales: el farmer llego a UN tile de
        # distancia de una vaca hambrienta sin alimentarla nunca, porque
        # siempre "ganaba" una cosecha mas cercana. Ahora, si el animal
        # YA fallo un dia de comida (consecutive_unfed >= 1 -- la ULTIMA
        # oportunidad antes de escaparse), "feed" sube a la MISMA
        # prioridad que cosechar: perder el animal entero (compra + toda
        # su produccion futura) es mucho mas caro que demorar una
        # cosecha, que simplemente espera a que alguien la levante.
        if task == "feed" and isinstance(extra, int) and extra >= 1:
            priority = TASK_PRIORITY["harvest"]
        # AJUSTE V54 -- BUG REAL CONFIRMADO CON PARTIDA REAL (94086794):
        # exactamente el mismo problema que V35 encontro y arreglo para
        # "feed", pero nunca se aplico a "water". Con TASK_PRIORITY["water"]=3,
        # por debajo de harvest/collect_fertilizer/dig, en una granja
        # grande y activa (100 tiles) casi SIEMPRE hay algo para cosechar,
        # fertilizar o cavar en algun lado -- asi que regar practicamente
        # nunca ganaba el turno de una unidad, sin importar cuan urgente
        # fuera. Confirmado mapeando el tablero final: una zona muerta
        # permanente y predecible (la mas lejana del shed, columna y fila
        # del borde) con 64% del terreno entre maleza y vacio -- porque el
        # desempate por distancia SIEMPRE favorece lo cercano, y lo lejano
        # pierde la puja una y otra vez, partida tras partida. Ahora,
        # igual que con "feed": si una planta ya esta a un riego de
        # convertirse en maleza permanente (consecutive_unwatered >= 1 --
        # la ULTIMA oportunidad), su prioridad sube a la MISMA que
        # cosechar -- perder el cultivo entero (semilla + toda la cosecha
        # futura de esa tile) es mas caro que demorar una cosecha que
        # simplemente espera a que alguien la levante.
        if task == "water" and isinstance(extra, int) and extra >= 1:
            priority = TASK_PRIORITY["harvest"]
        # AJUSTE V24: dentro del bucket "water", una planta con
        # consecutive_unwatered==1 esta a UN riego de convertirse en weed
        # esta noche -- eso pesa mas que la distancia. Se resta la
        # urgencia (0 o 1+) antes de la distancia en la clave de orden,
        # asi una planta urgente lejos le gana a una planta sana cerca.
        # AJUSTE V28: la misma logica de urgencia que ya se aplicaba solo a
        # "water" ahora tambien cubre "feed" -- un animal a punto de
        # escaparse por hambre (consecutive_unfed alto) le gana a uno
        # recien alimentado, sin importar la distancia.
        urgency = extra if (task in ("water", "feed") and isinstance(extra, int)) else 0
        distance = manhattan(fx, fy, x, y)
        return (priority, -urgency, distance)

    return min(candidates, key=key)

def gather_candidates(state, crop_to_plant, build_targets=None, animals_to_place=None, needs_shed_trip=False, exclude_tiles=None):
    exclude_tiles = exclude_tiles or set()
    candidates = []
    candidates += [(x, y, "harvest", None) for x, y in find_ripe_plants(state.board, state.day)]
    candidates += [(x, y, "harvest_animal", None) for x, y in find_ripe_animals(state.board, state.day)]
    candidates += [(x, y, "collect_fertilizer", None) for x, y in find_fertilizer_ready_animals(state.board)]
    candidates += [(x, y, "dig", None) for x, y in find_weeds(state.board)]
    candidates += [(x, y, "water", urgency) for x, y, urgency in find_unwatered_plants(state.board)]

    # ANTES: la unica forma de ir al shed era como ultimo recurso, cuando
    # NO HABIA absolutamente ningun otro candidato en todo el tablero. Con
    # muchos cultivos "ongoing" plantados en paralelo (ver plan_seed_purchases),
    # casi siempre habia ALGO para cosechar en algun lado, asi que el shed
    # nunca se visitaba y lo cosechado se acumulaba sin venderse jamas.
    # AHORA: las 4 tiles del shed son candidatas de verdad, con la MISMA
    # prioridad que cosechar -- compiten por distancia real, no quedan
    # descartadas de entrada.
    if needs_shed_trip:
        candidates += [(x, y, "shed_drop", None) for x, y in shed_tiles(state.board_size)]

    for x, y, needs_feed, _needs_care, urgencia_hambre in find_needy_animals(state.board):
        if needs_feed:
            candidates.append((x, y, "feed", urgencia_hambre))
        else:
            candidates.append((x, y, "care", None))

    if animals_to_place:
        # AJUSTE V38 -- BUG CRITICO REAL ENCONTRADO EN SIMULACION:
        # find_empty_animal_structures devuelve TODAS las estructuras
        # vacias (COOP y PASTURE mezcladas), sin filtrar por el tipo que
        # la especie realmente necesita (GOOSE->COOP, COW/SHEEP->PASTURE).
        # Una unidad cargando COW podia terminar guiada hacia un COOP
        # vacio -- el PLACE ahi no hace nada util (estructura equivocada),
        # asi que la unidad se quedaba "atendida" segun nuestra propia
        # logica pero el animal nunca se colocaba de verdad. Confirmado
        # con trazas reales: 8 animales (4 COW + 4 SHEEP) se quedaron
        # pudriendose en el shed 14+ dias seguidos pese a 5 estructuras
        # vacias disponibles -- sin colocar NINGUNO. Ahora se filtra por
        # el tipo de estructura correcto para la especie que se esta
        # cargando.
        estructura_necesaria = ANIMAL_DATA.get(animals_to_place, {}).get("structure")
        for x, y in find_empty_animal_structures(state.board):
            if state.board[y][x].get("kind") == estructura_necesaria:
                candidates.append((x, y, "place_animal", None))

    if build_targets:
        for x, y, structure in build_targets:
            candidates.append((x, y, "build", structure))

    if crop_to_plant:
        candidates += [
            (x, y, "plant", crop_to_plant)
            for x, y in find_empty_tiles(state.board, exclude=shed_tiles(state.board_size))
        ]

    # AJUSTE V36 -- ver comentario largo arriba: si hay candidatos de
    # sobra, se descartan los que otra unidad de ESTE MISMO turno ya
    # reclamo como destino, para que se dispersen en vez de amontonarse.
    # Si filtrar deja la lista vacia (pocos candidatos totales, varias
    # unidades compitiendo), es mejor permitir que se repita un destino a
    # que una unidad se quede sin nada que hacer -- por eso el fallback.
    if exclude_tiles:
        filtered = [c for c in candidates if (c[0], c[1]) not in exclude_tiles]
        if filtered:
            candidates = filtered

    return candidates

# ==========================================================
# planner.py
# ==========================================================

def _pick_crop_to_plant(state, crop_plan, reserved_seeds=None):
    """Recorre crop_plan (ya ordenado por rentabilidad actual) y devuelve
    el primer cultivo para el que tenemos semilla Y que todavia no llego
    a su tope de tiles asignado. Asi el reparto de tierra SI refleja los
    numeros calculados por el optimizador, en vez de que un solo cultivo
    domine todas las tiles vacias.

    RED DE SEGURIDAD (agregada tras ver datos reales de una partida
    donde 24 semillas de WHEAT quedaron sin usar toda la partida
    mientras las unidades se quedaban en PASS): si el crop_plan no
    elige nada -- por la razon que sea, tope alcanzado, cultivo excluido,
    etc. -- pero hay CUALQUIER semilla ya comprada sin usar, se plania
    esa igual. Nunca tiene sentido dejar semilla pagada sin usar.

    AJUSTE V27 -- BUG REAL ENCONTRADO: esta funcion se llama por
    SEPARADO para el farmer y para CADA mano, todas usando la MISMA foto
    de state.seeds (no se actualiza hasta el proximo turno). Las reglas
    del juego son explicitas: "If you try to plant too many in a
    specific turn, none are planted -- ie if you have 1 melon seed, but
    two units do the PLANT MELON command". Sin coordinacion, si el
    farmer Y una mano llegan al mismo turno con solo 1 semilla de WHEAT
    disponible, AMBOS eligen WHEAT independientemente (mismo crop_plan,
    mismo estado) y las DOS plantaciones fallan -- turno perdido para
    las dos unidades, semilla pagada sin usar. Con varias manos
    contratadas y trabajando cerca (como en el screenshot real de una
    partida, donde el rival tenia 3 unidades juntas sembrando mucho mas
    rapido que nosotros), esto puede repetirse turno tras turno. AHORA
    recibe `reserved_seeds`: un contador de cuanta semilla de cada
    cultivo ya "aparto" alguna unidad anterior en ESTE MISMO turno, y
    resta eso de la semilla disponible antes de elegir -- si no alcanza,
    pasa al siguiente cultivo candidato en vez de chocar."""
    reserved_seeds = reserved_seeds or {}
    crop_plan = crop_plan or []

    # AJUSTE V48 -- BUG REAL CONFIRMADO CON PARTIDA REAL (93738139): la
    # red de seguridad de mas abajo (plantar cualquier semilla si el
    # crop_plan no elige nada) practicamente NUNCA se activaba, porque
    # con MAX_CONCURRENT_CROPS funcionando bien casi siempre hay alguno
    # de los 4 rubros del crop_plan con capacidad libre. Confirmado: 8
    # semillas de TOMATO ($400) se compraron el dia 19 (mientras
    # calificaba para el top-4 ese turno) y se quedaron sin plantar los
    # 11 dias restantes de la partida -- con 18 a 27 tiles VACIAS todo
    # ese tiempo -- porque WHEAT/CARROT/MELON/STRAWBERRY siempre tenian
    # algo que hacer primero una vez que TOMATO salio del top-4 (el
    # precio de mercado cambio). Ya gastamos esa plata: no tiene sentido
    # esperar a que el resto del crop_plan se quede sin nada que hacer
    # para recuperarla. Ahora se drena PRIMERO cualquier semilla
    # comprada de un cultivo que YA NO figura en el crop_plan actual --
    # antes de seguir sumando mas tierra a los que si estan en el top-4.
    en_plan = {crop for crop, _ in crop_plan}
    for crop, count in (state.seeds or {}).items():
        if crop in en_plan:
            continue
        disponible = count - reserved_seeds.get(crop, 0)
        if disponible > 0:
            return crop

    for crop, cap in crop_plan:
        disponible = state.seeds.get(crop, 0) - reserved_seeds.get(crop, 0)
        if disponible <= 0:
            continue
        if count_crop_on_board(state.board, crop) < cap:
            return crop

    for crop, count in (state.seeds or {}).items():
        if count - reserved_seeds.get(crop, 0) > 0:
            return crop
    return None

def _immediate_tile_action(tile, plan, current_day):
    """Devuelve (accion, nombre_de_tarea) para la tile en la que la unidad
    esta parada AHORA MISMO, o (None, None) si no hay nada que hacer sin
    moverse. AJUSTE V32: ahora tambien devuelve el nombre de tarea (para
    poder compararlo en TASK_PRIORITY contra el mejor candidato remoto --
    ver decide_unit_action mas abajo, donde se corrige el bug real de
    unidades que nunca viajaban a cosechar cultivos/animales lejanos
    porque siempre tenian algo LOCAL de menor prioridad para hacer)."""
    if isinstance(tile, dict):
        kind = tile.get("kind")

        if kind == "WEED":
            return UnitActions.dig(), "dig"

        if kind == "PLANT":
            if tile.get("yield_units", 0) > 0 and _is_plant_mature(tile, current_day):
                return UnitActions.harvest(), "harvest"
            if not tile.get("watered_today", False):
                return UnitActions.water(), "water"
            crop = tile.get("crop")
            if crop in FERTILIZER_PRIORITY_CROPS and tile.get("fertilized_until_day", -1) < 0 and plan.get("has_fertilizer_in_hand"):
                return UnitActions.fertilize(), "fertilize"

        if kind in ("COOP", "PASTURE"):
            if tile.get("animal") is not None:
                if tile.get("yield_units", 0) > 0 and _is_animal_mature(tile, current_day):
                    return UnitActions.harvest(), "harvest_animal"
                if tile.get("fertilizer_available", False):
                    return UnitActions.collect_fertilizer(), "collect_fertilizer"
                needs_feed = not tile.get("fed_today", False)
                needs_care = not tile.get("cared_today", False)
                if needs_feed and plan.get("has_wheat_in_hand"):
                    return UnitActions.feed(), "feed"
                if needs_care:
                    return UnitActions.care(), "care"
            else:
                # AJUSTE V39b: se coloca lo que la unidad YA CARGA
                # (per_unit_plan["has_species_in_hand"], seteado en
                # decide_unit_action segun el inventario real), no la
                # prioridad global del turno -- si no, una unidad que
                # camina con SHEEP nunca lo coloca cuando el turno
                # prioriza COW (ver V39 arriba, mismo bug).
                especie_en_mano = plan.get("has_species_in_hand")
                if especie_en_mano:
                    return UnitActions.place(especie_en_mano), "place_animal"

    return None, None

def _reserved_quantities(plan):
    """
    ANTES: reservaba el ITEM COMPLETO (ej. "WHEAT") sin limite -- si el
    cultivo cosechado era justamente WHEAT, el farmer nunca soltaba nada
    de trigo (pensaba que "hacia falta para alimentar"), acumulandolo
    para siempre sin vender ni una unidad. Bug real encontrado con datos
    de partidas reales (HARVEST 78%, DROP 0% en 720 turnos).
    AHORA: reserva solo la CANTIDAD que realmente hace falta cargar (ej.
    3 de trigo, lo que se recoge por viaje) -- cualquier excedente por
    encima de eso SI se puede soltar y vender. Y en el endgame (ultimos
    dias de temporada) no se reserva NADA -- no tiene sentido guardar
    trigo "para seguir alimentando" cuando ya no queda tiempo para que
    eso genere ninguna cosecha mas.
    """
    if plan.get("is_endgame"):
        return {}

    reserved = {}
    if plan.get("want_wheat"):
        reserved["WHEAT"] = plan.get("wheat_pickup_qty", 3)
    if plan.get("want_fertilizer"):
        reserved["FERTILIZER"] = plan.get("fertilizer_pickup_qty", 1)
    # AJUSTE V39 -- BUG CRITICO REAL: ANTES solo se reservaba UNA especie
    # (plan["place_species"], la prioridad de ESTE turno especifico, que
    # cambia turno a turno segun cual especie tenga stock en el shed en
    # ese momento). Si una unidad ya cargaba SHEEP pero el turno
    # siguiente el sistema pasaba a priorizar COW (porque el shed de COW
    # volvia a tener stock), el SHEEP que la unidad llevaba dejaba de
    # estar "reservado" -- y si esa unidad pasaba cerca del shed, lo
    # soltaba de vuelta, deshaciendo todo el viaje sin haberlo colocado
    # nunca. Confirmado en simulacion: el conteo de COW en el shed
    # oscilaba sin parar entre 0 y 3 durante dias, con CERO animales
    # colocados sostenido por 6+ dias pese a estructuras vacias
    # disponibles -- exactamente el patron de "recoger y devolver" en
    # loop. Ahora se reserva CUALQUIER especie animal que la unidad ya
    # tenga en la mochila (no solo la prioridad puntual de este turno),
    # asi nunca se suelta un animal a mitad de camino.
    for especie in ANIMAL_DATA:
        reserved[especie] = 1
    return reserved

def _droppable_items(unit_inventory, plan):
    """Cuanto de cada item en el inventario de la unidad EXCEDE lo
    reservado -- eso es lo que conviene soltar en el shed para venderlo."""
    reserved = _reserved_quantities(plan)
    result = {}
    for item, qty in unit_inventory.items():
        excess = (qty or 0) - reserved.get(item, 0)
        if excess > 0:
            result[item] = excess
    return result

def _needs_shed_trip(state, unit_inventory, plan, wheat_pickup_budget=None, animal_pickup_budget=None):
    has_droppable = bool(_droppable_items(unit_inventory, plan))

    place_species = plan.get("place_species")
    wheat_budget_ok = wheat_pickup_budget is None or wheat_pickup_budget.get("remaining", 0) > 0
    needs_wheat = (plan.get("want_wheat") and not unit_inventory.get("WHEAT")
                   and state.shed.get("WHEAT", 0) > 0 and wheat_budget_ok)
    animal_budget_ok = animal_pickup_budget is None or animal_pickup_budget.get("remaining", 0) > 0
    needs_species = (place_species and not unit_inventory.get(place_species)
                      and state.shed.get(place_species, 0) > 0 and animal_budget_ok)
    needs_fertilizer = (plan.get("want_fertilizer") and not unit_inventory.get("FERTILIZER")
                         and state.shed.get("FERTILIZER", 0) > 0)

    return has_droppable or needs_wheat or needs_species or needs_fertilizer

def _shed_action(pos, state, unit_inventory, plan, wheat_pickup_budget=None, animal_pickup_budget=None):
    if not is_shed_adjacent(pos, state.board_size):
        return None

    droppable = _droppable_items(unit_inventory, plan)
    if droppable:
        reserved = _reserved_quantities(plan)
        # Si nada de lo que cargamos esta reservado, un DROP simple vacia
        # todo el inventario de una (mas eficiente que ir item por item).
        nothing_reserved_here = not any(unit_inventory.get(k, 0) > 0 for k in reserved)
        if nothing_reserved_here:
            return UnitActions.drop()
        # Si hay algo que SI queremos conservar (ej. trigo para seguir
        # alimentando), soltamos solo el excedente de un item con PLACE,
        # no el inventario completo con DROP.
        item, qty = next(iter(droppable.items()))
        return UnitActions.place(item, qty)

    place_species = plan.get("place_species")

    # AJUSTE V33: el pickup de trigo ahora respeta un presupuesto
    # COMPARTIDO entre todas las unidades del turno (ver schedule_units) --
    # antes cada mano evaluaba "want_wheat" de forma aislada (solo miraba
    # si HABIA algun animal vivo en la granja, no si YA habia alguien
    # llevandole de comer), asi que varias manos terminaban levantando su
    # propio lote de 3 unidades el mismo dia sin coordinarse. Confirmado
    # en simulacion: el shed se vaciaba de 7-11 unidades de trigo recien
    # comprado en cuestion de turnos sin que el animal fuera alimentado ni
    # una sola vez ese dia -- coincide exacto con por que COW/SHEEP
    # escapan por hambre (2 dias seguidos sin comer) pese a que SI se
    # estaba gastando plata real en trigo.
    wheat_budget_ok = wheat_pickup_budget is None or wheat_pickup_budget.get("remaining", 0) > 0
    if plan.get("want_wheat") and not unit_inventory.get("WHEAT") and state.shed.get("WHEAT", 0) > 0 and wheat_budget_ok:
        qty = min(plan.get("wheat_pickup_qty", 3), state.shed["WHEAT"])
        if wheat_pickup_budget is not None:
            wheat_pickup_budget["remaining"] = wheat_pickup_budget.get("remaining", 0) - 1
        return UnitActions.pickup("WHEAT", qty)

    # AJUSTE V34 -- ver comentario largo en schedule_units: el pickup de
    # la especie a colocar ahora tambien respeta un presupuesto
    # compartido, limitado al numero real de estructuras vacias que la
    # necesitan -- antes CUALQUIER mano sin esa especie en la mochila la
    # levantaba, aunque ya hubiera otras unidades cargando lo mismo para
    # la UNICA estructura vacia disponible.
    animal_budget_ok = animal_pickup_budget is None or animal_pickup_budget.get("remaining", 0) > 0
    if place_species and not unit_inventory.get(place_species) and state.shed.get(place_species, 0) > 0 and animal_budget_ok:
        if animal_pickup_budget is not None:
            animal_pickup_budget["remaining"] = animal_pickup_budget.get("remaining", 0) - 1
        return UnitActions.pickup(place_species, 1)

    if plan.get("want_fertilizer") and not unit_inventory.get("FERTILIZER") and state.shed.get("FERTILIZER", 0) > 0:
        qty = min(plan.get("fertilizer_pickup_qty", 1), state.shed["FERTILIZER"])
        return UnitActions.pickup("FERTILIZER", qty)

    return None

def decide_unit_action(pos, state, unit_index, plan, reserved_seeds=None, wheat_pickup_budget=None, animal_pickup_budget=None, claimed_tiles=None):
    reserved_seeds = reserved_seeds if reserved_seeds is not None else {}
    fx, fy = pos
    tile = state.board[fy][fx]
    unit_inventory = state.inventory_of(unit_index)

    per_unit_plan = dict(plan)
    per_unit_plan["has_fertilizer_in_hand"] = bool(unit_inventory.get("FERTILIZER"))
    per_unit_plan["has_wheat_in_hand"] = bool(unit_inventory.get("WHEAT"))
    # AJUSTE V39b -- BUG CRITICO REAL: ANTES esto solo reconocia la
    # especie si coincidia con la prioridad GLOBAL del turno
    # (plan["place_species"], que cambia turno a turno). Una unidad que
    # ya cargaba SHEEP en la mochila quedaba "ciega" a su propia carga
    # apenas el turno pasaba a priorizar COW -- ni el place inmediato ni
    # la busqueda de candidatos sabian que hacer con ese SHEEP. Ahora se
    # detecta la especie REAL que la unidad tiene en el inventario, sin
    # importar la prioridad del turno.
    especie_cargada = next((sp for sp in ANIMAL_DATA if unit_inventory.get(sp, 0) > 0), None)
    per_unit_plan["has_species_in_hand"] = especie_cargada
    # a donde VIAJAR: si ya cargamos un animal, priorizamos colocar ESE
    # (no cambiar de idea a mitad de camino); si no, seguimos la
    # prioridad global de que especie levantar del shed a continuacion.
    especie_para_candidatos = especie_cargada or plan.get("place_species")

    immediate, immediate_task = _immediate_tile_action(tile, per_unit_plan, state.day)
    immediate_priority = TASK_PRIORITY.get(immediate_task, 99) if immediate is not None else None

    # AJUSTE V32 -- BUG CRITICO REAL ENCONTRADO CON DATOS DE 2 PARTIDAS
    # IDENTICAS: ANTES, si la unidad tenia CUALQUIER accion inmediata
    # disponible en la tile donde esta parada (tipicamente "regar", que
    # siempre hay de sobra en el cluster grande de WHEAT/CARROT), la
    # ejecutaba SIN COMPARAR contra si hay algo de MAYOR prioridad
    # esperando en otro lado del tablero -- una cosecha de cultivo o
    # animal lista, tarea con la prioridad MAS ALTA de todo el sistema
    # (TASK_PRIORITY["harvest"]=0 vs "water"=3). Con parches chicos y
    # aislados de un cultivo raro (TOMATO, casi siempre solo 1-2 tiles,
    # lejos del cluster principal) o animales en PASTURE/COOP alejados,
    # las unidades JAMAS viajaban hasta alli: el cluster grande siempre
    # les daba "algo que hacer" localmente antes de que la logica de
    # movimiento hacia otro objetivo entrara siquiera a jugar. Confirmado
    # en simulacion local: 2 tiles de TOMATO sobrevivieron 12 dias
    # (bastante mas que los 8 necesarios para la primera cosecha) con
    # yield_units=1 LISTO para cosechar, sin que ninguna unidad las
    # visitara ni una sola vez, hasta morir como weed -- y COW/SHEEP
    # acumulando yield_units=3-4 sin cosechar jamas. Coincide EXACTO con
    # 2 partidas reales identicas: TOMATO $500 gastado / $0 de ingreso,
    # SHEEP $500 gastado / $0 de ingreso, ambas veces. Ahora se compara
    # la prioridad de la accion LOCAL contra la del mejor candidato
    # REMOTO (usando la MISMA lista de candidatos y TASK_PRIORITY que ya
    # existian, sin inventar un sistema nuevo): si hay algo remoto de
    # prioridad ESTRICTAMENTE mejor (numero mas bajo), la unidad viaja
    # hacia alla en vez de quedarse haciendo la tarea local de menor
    # prioridad. Si la accion local ya es la mejor (o no hay nada mejor
    # remoto), se sigue ejecutando localmente como antes -- este cambio
    # SOLO afecta el caso donde algo mas urgente esta siendo ignorado.
    crop_to_plant = _pick_crop_to_plant(state, plan.get("crop_plan"), reserved_seeds)

    needs_shed_trip = False
    if immediate is None and tile is None:
        for bx, by, structure in plan.get("build_targets", []):
            if (bx, by) == (fx, fy):
                return UnitActions.build_coop() if structure == "COOP" else UnitActions.build_pasture()
        if crop_to_plant and not is_shed_adjacent(pos, state.board_size):
            reserved_seeds[crop_to_plant] = reserved_seeds.get(crop_to_plant, 0) + 1
            return UnitActions.plant(crop_to_plant)

    if immediate is None:
        shed_action = _shed_action(pos, state, unit_inventory, per_unit_plan, wheat_pickup_budget, animal_pickup_budget)
        if shed_action is not None:
            return shed_action
        needs_shed_trip = _needs_shed_trip(state, unit_inventory, plan, wheat_pickup_budget, animal_pickup_budget)

    candidates = gather_candidates(
        state,
        crop_to_plant,
        build_targets=plan.get("build_targets"),
        animals_to_place=especie_para_candidatos,
        needs_shed_trip=needs_shed_trip,
        exclude_tiles=claimed_tiles,
    )
    target = best_candidate(pos, candidates)

    # AJUSTE V36: apenas se elige un destino, se marca como "reclamado"
    # para que las DEMAS unidades de este mismo turno lo descarten (ver
    # gather_candidates) y elijan otra cosa -- sin esto, todas corrian el
    # mismo algoritmo desde posiciones casi identicas y convergian en el
    # MISMO destino turno tras turno, quedando pegadas todo el juego.
    if claimed_tiles is not None and target is not None:
        claimed_tiles.add((target[0], target[1]))

    if immediate is not None:
        if target is None:
            return immediate
        tx, ty, _task, _extra = target
        remote_priority = TASK_PRIORITY.get(_task, 99)

        # AJUSTE V32b -- CORRECCION DE UN SOBRE-AJUSTE PROPIO: la primera
        # version de este fix dejaba que CUALQUIER unidad abandonara
        # CUALQUIER accion local (incluido regar/alimentar) para perseguir
        # lo de mejor prioridad remota. Probado en simulacion: esto
        # provoco un colapso economico total (caja en $0 sostenido desde
        # el dia ~25 en las 3 corridas de prueba) -- el motivo real: con
        # varias manos todas persiguiendo la MISMA cosecha lejana
        # simultaneamente, el cluster grande de WHEAT se quedaba sin
        # nadie regandolo, y WHEAT (nuestro cultivo mas rentable por
        # lejos) se convertia en weed en masa. Regar/alimentar son
        # tareas con plazo real (2 dias sin agua/comida = perdida total),
        # mientras que una cosecha lista simplemente ESPERA hasta que
        # alguien la levante -- no tiene el mismo apuro que evitar que
        # algo se muera. Ahora el "viaje a lo remoto" esta acotado por
        # partida doble: (a) solo lo hace el farmer (indice 0), nunca las
        # manos contratadas, para no desguarnecer el riego con varias
        # unidades a la vez, y (b) nunca se abandona un riego/alimentado
        # que YA esta atrasado (consecutive_unwatered/unfed >= 1) -- solo
        # se pospone el riego/alimentado de HOY si todavia es la primera
        # vez que se salta (hay margen real de 1 dia mas antes de perder
        # la planta/animal).
        local_is_urgent = (
            (immediate_task == "water" and tile.get("consecutive_unwatered", 0) >= 1) or
            (immediate_task == "feed" and tile.get("consecutive_unfed", 0) >= 1)
        )

        # AJUSTE V33b -- BUG REAL CONFIRMADO EN SIMULACION: el override
        # anterior solo cubria "harvest"/"harvest_animal", nunca "feed" --
        # asi que aunque el trigo YA estuviera disponible y quieto en el
        # shed (el bug de coordinacion de V33 se corrigio), NINGUNA unidad
        # se desviaba nunca a llevarselo a un animal lejano: "feed" tiene
        # la MISMA prioridad numerica que "water" (ambas 3), asi que ni
        # siquiera calificaba como "estrictamente mejor" para el chequeo
        # de arriba. Confirmado con trazas reales: el shed se mantenia
        # con 3-7 unidades de trigo estable durante 2 dias completos sin
        # que "fed_today" pasara a True ni una sola vez, hasta que el
        # animal escapo. Ahora "feed" tambien califica, y cuando hay
        # EMPATE de prioridad (feed remoto=3 vs agua local=3) se rompe a
        # favor de lo remoto si esta cerca de escapar (consecutive_unfed
        # >= 1 en el animal remoto) -- perder un animal completo (costo
        # de compra + toda su produccion futura) es mucho mas caro que
        # atrasar UN riego que todavia tiene un dia entero de margen.
        remote_is_critical_feed = _task == "feed" and isinstance(_extra, int) and _extra >= 1
        should_chase_remote = (
            unit_index == 0
            and _task in ("harvest", "harvest_animal", "feed")
            and not local_is_urgent
            and (tx, ty) != (fx, fy)
            and (immediate_priority > remote_priority or remote_is_critical_feed)
        )
        if should_chase_remote:
            # AJUSTE V33c -- BUG REAL: el farmer se desviaba derecho hacia
            # el animal remoto, pero si no tenia trigo en la mochila
            # llegaba con las manos vacias y no podia alimentarlo (el
            # motor del juego exige trigo en inventario para que FEED
            # haga algo). Confirmado en simulacion: el shed se mantenia
            # con trigo disponible y estable, pero "fed_today" nunca
            # pasaba a True -- el farmer iba directo al animal sin pasar
            # por el shed primero. Ahora, si hace falta trigo, el primer
            # tramo del viaje es al shed (mas cercano), y solo despues de
            # tenerlo en mano el viaje apunta al animal.
            if _task == "feed" and not per_unit_plan.get("has_wheat_in_hand") and state.shed.get("WHEAT", 0) > 0:
                shed_target = nearest_shed_tile(pos, state.board_size)
                step = step_toward(fx, fy, shed_target[0], shed_target[1])
                return UnitActions.move(step) if step else immediate
            step = step_toward(fx, fy, tx, ty)
            return UnitActions.move(step) if step else immediate
        return immediate

    if target is None:
        if needs_shed_trip:
            shed_target = nearest_shed_tile(pos, state.board_size)
            step = step_toward(fx, fy, shed_target[0], shed_target[1])
            return UnitActions.move(step) if step else UnitActions.pass_turn()
        return UnitActions.pass_turn()

    tx, ty, _task, _extra = target
    if (tx, ty) == (fx, fy):
        return UnitActions.pass_turn()

    step = step_toward(fx, fy, tx, ty)
    return UnitActions.move(step) if step else UnitActions.pass_turn()

# ==========================================================
# scheduler.py
# ==========================================================

def schedule_units(state, plan):
    # AJUSTE V27: reserved_seeds se comparte entre TODAS las unidades de
    # este turno (farmer + cada mano) para que coordinen que cultivo
    # plantar sin pisarse la semilla disponible (ver _pick_crop_to_plant).
    reserved_seeds = {}

    # AJUSTE V36 -- BUG CRITICO REAL, CONFIRMADO CON LOG TURNO A TURNO:
    # farmer y las manos convergian en la MISMA tile y ejecutaban la
    # MISMA accion turno tras turno (ej. las 4 unidades en (4,2) haciendo
    # NORTH simultaneamente, o las 4 regando la MISMA tile) -- porque
    # cada unidad corria el mismo algoritmo greedy de "candidato mas
    # cercano" de forma INDEPENDIENTE, sin saber que otra unidad YA habia
    # elegido ese mismo destino este turno. Desde posiciones de partida
    # casi identicas (todas arrancan pegadas al shed), el "mejor"
    # candidato es el MISMO para las 4, asi que se quedaban pegadas todo
    # el juego -- desperdiciando 3 de cada 4 turnos de trabajo. Ahora
    # cada unidad reclama su destino apenas lo elige (ver
    # decide_unit_action), y las siguientes lo descartan de su propia
    # busqueda, forzando que se dispersen.
    claimed_tiles = set()

    # AJUSTE V33 -- BUG REAL CONFIRMADO EN SIMULACION (trazas turno a
    # turno): "want_wheat" solo miraba si HABIA algun animal vivo en TODA
    # la granja, sin coordinar entre unidades -- cada mano que pasaba por
    # el shed sin trigo en la mochila agarraba su propio lote de 3
    # unidades "por las dudas", aunque otra mano ya estuviera cargando
    # trigo hacia el mismo animal. Confirmado: el shed tenia 7-11 unidades
    # de trigo recien compradas y se vaciaba en pocos turnos sin que
    # NINGUN animal fuera alimentado ese dia -- coincide exacto con por
    # que COW/SHEEP escapan por hambre (2 dias seguidos sin comer) pese a
    # que la plata SI se estaba gastando en trigo. Ahora se calcula
    # cuantos animales de verdad necesitan comer HOY (y cuantas unidades
    # ya cargan trigo para eso) ANTES de procesar a cada unidad, y ese
    # numero es el limite real de cuantas manos pueden levantar trigo
    # nuevo del shed este turno.
    animales_sin_comer_hoy = sum(
        1 for x, y, t in iter_tiles(state.board)
        if isinstance(t, dict) and t.get("animal") is not None and not t.get("fed_today", False)
    )
    ya_cargando_trigo = sum(
        1 for idx in range(1 + len(state.hands_pos))
        if state.inventory_of(idx).get("WHEAT", 0) > 0
    )
    wheat_pickup_budget = {"remaining": max(0, animales_sin_comer_hoy - ya_cargando_trigo)}

    # AJUSTE V34 -- BUG CRITICO REAL, EL MAS GRAVE DE TODA LA SESION: mismo
    # problema de coordinacion que el trigo (ver V33), pero para colocar
    # animales -- y con un impacto mucho peor. "place_species" es un solo
    # valor compartido por TODAS las unidades sin ningun limite de cuantas
    # pueden intentar cargarlo al mismo tiempo. Con 6-8 manos, TODAS
    # agarraban la MISMA especie del shed para ir a colocarla, aunque solo
    # hubiera 1-2 estructuras vacias reales -- generando un loop de
    # pickup/drop que consumia CADA turno de CADA mano sin que ninguna
    # saliera jamas al campo. Confirmado con trazas reales: TODAS las
    # unidades (farmer + hasta 8 manos) quedaron pegadas en las 4 tiles
    # junto al shed durante 120+ turnos seguidos, mientras medio tablero
    # se llenaba de maleza sin que nadie fuera a cavarla -- este bug
    # explica el estancamiento del dinero y el bajo rendimiento en TODAS
    # las partidas reales de esta sesion. Ahora el pickup de la especie a
    # colocar se limita al numero real de estructuras vacias que la
    # necesitan.
    especies_a_colocar_hoy = 0
    place_species_plan = plan.get("place_species")
    if place_species_plan:
        estructura_necesaria = ANIMAL_DATA.get(place_species_plan, {}).get("structure")
        especies_a_colocar_hoy = sum(
            1 for x, y in find_empty_animal_structures(state.board)
            if state.board[y][x].get("kind") == estructura_necesaria
        )
    ya_cargando_especie = sum(
        1 for idx in range(1 + len(state.hands_pos))
        if place_species_plan and state.inventory_of(idx).get(place_species_plan, 0) > 0
    )
    animal_pickup_budget = {"remaining": max(0, especies_a_colocar_hoy - ya_cargando_especie)}

    # AJUSTE V24: ANTES, si decide_unit_action tiraba una excepcion para
    # CUALQUIER unidad (ej. una mano parada en una tile con un estado raro),
    # la excepcion se propagaba y tumbaba TODO el turno (via el try/except
    # de agent()) -- farmer Y todas las demas manos quedaban en PASS, aunque
    # su logica individual estuviera perfectamente bien. AHORA cada unidad
    # se evalua de forma aislada: si UNA falla, esa unidad puntual hace
    # PASS pero el resto sigue actuando con normalidad.
    def _safe_unit_action(pos, unit_index):
        try:
            return decide_unit_action(pos, state, unit_index, plan, reserved_seeds, wheat_pickup_budget, animal_pickup_budget, claimed_tiles)
        except Exception as e:
            print(f"ERROR aislado en decide_unit_action (unidad {unit_index}): {e}")
            return UnitActions.pass_turn()

    farmer_action = _safe_unit_action(state.farmer_pos, 0)

    hands_actions = [
        _safe_unit_action(pos, i + 1)
        for i, pos in enumerate(state.hands_pos)
    ]

    return farmer_action, hands_actions

# ==========================================================
# agent.py
# ==========================================================

_memory = MarketMemory()

# ==========================================================
# INSTRUMENTACION TEMPORAL DE DIAGNOSTICO (AJUSTE V44, ampliado V45)
# ==========================================================
# Motivo: probando plan_market_actions() de forma aislada, con el estado
# REAL de una partida jugada (mismo dinero, mismos precios, mismo
# tablero), el codigo SI genera ordenes de BUY_LAND/BUY_SEED para
# WHEAT/CARROT/STRAWBERRY/TOMATO y de HIRE -- pero en esa misma partida
# real, la tierra nunca se expandio y esos 4 cultivos nunca se compraron
# ni una vez en 720 turnos. Osea: la decision economica es correcta: algo
# DESPUES de calcularla le impide tener efecto real en el juego, y eso no
# se puede diagnosticar mas por lectura de codigo ni pruebas aisladas --
# hace falta ver la decision CRUDA turno a turno de una partida real.
#
# AJUSTE V45 -- BUG DE PROCESO (no de codigo): se confirmo, revisando el
# campo "action" real guardado en el replay de una partida, que esa
# corrida en particular NO fue generada por esta version del archivo (el
# turno 0 quedaba en PASS total, se pedian 8 HIRE de una sin ningun tope,
# y solo se compraba TOMATO) -- un patron que este codigo no puede
# producir. Para que esta confusion de version no se repita, cada turno
# ahora queda marcado con MAIN_VERSION, en DOS lugares independientes:
# 1) el archivo de log de abajo, y 2) un print() en el primerisimo turno
# (dia 0, hora 0), que Kaggle captura en su propio log de stdout aunque
# nunca se llegue a generar el .jsonl (por ejemplo, si el entorno no deja
# escribir a disco). Con cualquiera de los dos alcanza para confirmar
# despues, sin ambiguedad, que version corrio una partida dada.
MAIN_VERSION = "V59-2026-08-19"

DEBUG_LOG_ORDERS = True
DEBUG_LOG_PATH = "main_debug_orders.jsonl"

def _debug_log_turn(state, market_orders, plan):
    if state.day == 0 and state.hour == 0:
        print(f"[main.py version={MAIN_VERSION}] arrancando partida")
    if not DEBUG_LOG_ORDERS:
        return
    try:
        import json as _json
        registro = {
            "version": MAIN_VERSION,
            "day": state.day, "hour": state.hour, "money": state.money,
            "market_orders": market_orders,
            "crop_plan": plan.get("crop_plan"),
            "place_species": plan.get("place_species"),
            "build_targets": plan.get("build_targets"),
            "cuadrantes": list(state.unlocked_quadrants),
        }
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(_json.dumps(registro, default=str) + "\n")
    except Exception:
        pass  # nunca romper el turno por un problema de logging

def agent(obs, config=None):
    _apply_config(config)
    try:
        state = GameState(obs)

        # AJUSTE V24 -- BUG REAL ENCONTRADO: ANTES, este mismo "if day==0
        # and hour==0" estaba DUPLICADO aca Y adentro de
        # plan_market_actions -- pero como agent() se ejecuta primero y
        # retornaba de una, el bloque de plan_market_actions (que SI
        # compra MELON y STRAWBERRY ademas de WHEAT/CARROT, condicionado a
        # la plata disponible) quedaba INALCANZABLE: codigo muerto que
        # nunca se ejecutaba. El turno 0 real solo compraba WHEAT(3) y
        # CARROT(2), nunca MELON ni STRAWBERRY, sin importar cuanta plata
        # hubiera (el config real confirma $3000 iniciales -- de sobra
        # para las 4 semillas). Esto es coherente con la partida real
        # jugada, donde MELON y STRAWBERRY nunca aparecieron ni una vez en
        # 720 turnos. AHORA se elimina el atajo duplicado: el turno 0 pasa
        # por el camino normal (plan_market_actions + schedule_units), que
        # ya maneja el caso day==0/hour==0 correctamente y de forma mas
        # completa.
        market_orders, plan = plan_market_actions(state, _memory)
        _debug_log_turn(state, market_orders, plan)
        farmer_action, hands_actions = schedule_units(state, plan)

        if farmer_action is None:
            farmer_action = ["PASS"]

        decision = Decision(farmer=farmer_action, hands=hands_actions, market=market_orders)
        return decision.to_dict()

    except Exception as e:
        import traceback
        print(f"ERROR en agent (dia={obs.get('day')}, hora={obs.get('hour')}): {e}")
        traceback.print_exc()
        return {"farmer": ["PASS"], "hands": [], "market": []}

def main(obs, config=None):
    return agent(obs, config)