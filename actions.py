"""
actions.py
----------
Fabrica de acciones con la sintaxis REAL confirmada por la spec del
juego. Nada de TODOs pendientes aqui -- todo esto esta documentado.
"""

from dataclasses import dataclass, field


@dataclass(slots=True)
class Decision:
    farmer: list = field(default_factory=lambda: ["PASS"])
    hands: list = field(default_factory=list)
    market: list = field(default_factory=list)

    def to_dict(self):
        return {"farmer": self.farmer, "hands": self.hands, "market": self.market}


class UnitActions:
    """Acciones validas para un farmer/hand individual (una por turno)."""

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
    """Ordenes de mercado (hasta maxMarketOrdersPerTurn por turno, default 10)."""

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
        # Solo WHEAT y FERTILIZER se pueden comprar de vuelta al mercado.
        return ["BUY_PRODUCT", item, qty]

    @staticmethod
    def hire():
        return ["HIRE"]

    @staticmethod
    def buy_land():
        return ["BUY_LAND"]
