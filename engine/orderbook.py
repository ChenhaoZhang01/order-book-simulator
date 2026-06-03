"""A price-time-priority limit order book with a matching engine.

Implements the core data structure used by exchanges and trading firms:

  * Limit orders rest in the book at their price.
  * Market orders sweep the opposite side until filled or exhausted.
  * Matching follows **price priority**, then **time priority (FIFO)** at a
    given price level.
  * Partial fills, cancels, and best-bid/ask (top of book) are supported.

Each side keeps a heap of prices (bids as a max-heap via negation, asks as a
min-heap). The resting orders live in per-price `PriceLevel` FIFO queues, so
matching at the touch is O(1) and finding the best price is O(log n).
"""

from __future__ import annotations

import heapq
import itertools
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"


_ids = itertools.count(1)


@dataclass
class Order:
    side: Side
    quantity: int
    price: Optional[float] = None  # None for market orders
    order_type: OrderType = OrderType.LIMIT
    id: int = field(default_factory=lambda: next(_ids))
    seq: int = 0  # assigned by the book for time priority


@dataclass
class Trade:
    price: float
    quantity: int
    taker_id: int
    maker_id: int
    aggressor: Side

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["aggressor"] = self.aggressor.value
        return d


class PriceLevel:
    """FIFO queue of resting orders at one price on one side."""

    def __init__(self, price: float, side: Side):
        self.price = price
        self.side = side
        self.orders: deque[Order] = deque()
        self.volume = 0

    def add(self, order: Order):
        self.orders.append(order)
        self.volume += order.quantity

    def reduce_front(self, qty: int):
        self.orders[0].quantity -= qty
        self.volume -= qty
        if self.orders[0].quantity == 0:
            self.orders.popleft()

    def remove(self, order_id: int) -> bool:
        for o in self.orders:
            if o.id == order_id:
                self.volume -= o.quantity
                self.orders.remove(o)
                return True
        return False

    @property
    def empty(self) -> bool:
        return not self.orders


class OrderBook:
    """Single-symbol limit order book with a matching engine."""

    def __init__(self, symbol: str = "SIM"):
        self.symbol = symbol
        self.bid_levels: dict[float, PriceLevel] = {}
        self.ask_levels: dict[float, PriceLevel] = {}
        self._bid_heap: list[float] = []   # max-heap via negation
        self._ask_heap: list[float] = []   # min-heap
        self._seq = itertools.count(1)
        self.last_trade_price: Optional[float] = None

    # ---- top of book -------------------------------------------------
    def best_bid(self) -> Optional[float]:
        while self._bid_heap:
            p = -self._bid_heap[0]
            lvl = self.bid_levels.get(p)
            if lvl and not lvl.empty:
                return p
            heapq.heappop(self._bid_heap)
            self.bid_levels.pop(p, None)
        return None

    def best_ask(self) -> Optional[float]:
        while self._ask_heap:
            p = self._ask_heap[0]
            lvl = self.ask_levels.get(p)
            if lvl and not lvl.empty:
                return p
            heapq.heappop(self._ask_heap)
            self.ask_levels.pop(p, None)
        return None

    # ---- order entry -------------------------------------------------
    def submit(self, order: Order) -> list[Trade]:
        order.seq = next(self._seq)
        limit = None if order.order_type == OrderType.MARKET else order.price
        trades = self._match(order, limit)
        if order.order_type == OrderType.LIMIT and order.quantity > 0:
            self._rest(order)
        return trades

    def _crosses(self, side: Side, resting_price: float, limit: Optional[float]) -> bool:
        if limit is None:
            return True
        return resting_price <= limit if side == Side.BUY else resting_price >= limit

    def _match(self, taker: Order, limit: Optional[float]) -> list[Trade]:
        trades: list[Trade] = []
        take_best = self.best_ask if taker.side == Side.BUY else self.best_bid
        levels = self.ask_levels if taker.side == Side.BUY else self.bid_levels

        while taker.quantity > 0:
            best = take_best()
            if best is None or not self._crosses(taker.side, best, limit):
                break
            level = levels[best]
            while taker.quantity > 0 and not level.empty:
                maker = level.orders[0]
                fill = min(taker.quantity, maker.quantity)
                trades.append(
                    Trade(best, fill, taker.id, maker.id, taker.side)
                )
                taker.quantity -= fill
                level.reduce_front(fill)
                self.last_trade_price = best
            if level.empty:
                levels.pop(best, None)
        return trades

    def _rest(self, order: Order):
        if order.side == Side.BUY:
            lvl = self.bid_levels.get(order.price)
            if lvl is None:
                lvl = PriceLevel(order.price, Side.BUY)
                self.bid_levels[order.price] = lvl
                heapq.heappush(self._bid_heap, -order.price)
        else:
            lvl = self.ask_levels.get(order.price)
            if lvl is None:
                lvl = PriceLevel(order.price, Side.SELL)
                self.ask_levels[order.price] = lvl
                heapq.heappush(self._ask_heap, order.price)
        lvl.add(order)

    def cancel(self, order_id: int) -> bool:
        for book in (self.bid_levels, self.ask_levels):
            for lvl in book.values():
                if lvl.remove(order_id):
                    return True
        return False

    # ---- snapshot ----------------------------------------------------
    def depth(self, n: int = 10) -> dict:
        bids = sorted(self.bid_levels.values(), key=lambda l: -l.price)[:n]
        asks = sorted(self.ask_levels.values(), key=lambda l: l.price)[:n]
        return {
            "symbol": self.symbol,
            "bids": [[l.price, l.volume] for l in bids if not l.empty],
            "asks": [[l.price, l.volume] for l in asks if not l.empty],
            "best_bid": self.best_bid(),
            "best_ask": self.best_ask(),
            "last_trade": self.last_trade_price,
        }
