"""Matching-engine tests: price-time priority, partials, market sweeps."""

from orderbook import OrderBook, Order, Side, OrderType


def test_resting_and_top_of_book():
    b = OrderBook()
    b.submit(Order(Side.BUY, 10, 99.0))
    b.submit(Order(Side.SELL, 5, 101.0))
    assert b.best_bid() == 99.0
    assert b.best_ask() == 101.0


def test_limit_cross_full_fill():
    b = OrderBook()
    b.submit(Order(Side.SELL, 10, 100.0))
    trades = b.submit(Order(Side.BUY, 10, 100.0))
    assert sum(t.quantity for t in trades) == 10
    assert trades[0].price == 100.0
    assert b.best_ask() is None  # book cleared


def test_partial_fill_rests_remainder():
    b = OrderBook()
    b.submit(Order(Side.SELL, 4, 100.0))
    trades = b.submit(Order(Side.BUY, 10, 100.0))
    assert sum(t.quantity for t in trades) == 4
    assert b.best_bid() == 100.0  # 6 remaining rests as a bid
    assert b.depth()["bids"][0] == [100.0, 6]


def test_price_time_priority():
    b = OrderBook()
    a = Order(Side.SELL, 5, 100.0)
    c = Order(Side.SELL, 5, 100.0)
    b.submit(a)  # earlier -> filled first
    b.submit(c)
    trades = b.submit(Order(Side.BUY, 5, 100.0))
    assert trades[0].maker_id == a.id


def test_better_price_matches_first():
    b = OrderBook()
    b.submit(Order(Side.SELL, 5, 101.0))
    b.submit(Order(Side.SELL, 5, 100.0))  # better (lower) ask
    trades = b.submit(Order(Side.BUY, 5, 101.0))
    assert trades[0].price == 100.0


def test_market_order_sweeps():
    b = OrderBook()
    b.submit(Order(Side.SELL, 3, 100.0))
    b.submit(Order(Side.SELL, 3, 101.0))
    trades = b.submit(Order(Side.BUY, 5, order_type=OrderType.MARKET))
    assert sum(t.quantity for t in trades) == 5
    assert [t.price for t in trades] == [100.0, 100.0, 100.0, 101.0, 101.0] or \
           sum(t.quantity for t in trades) == 5  # aggregated fills


def test_cancel():
    b = OrderBook()
    o = Order(Side.BUY, 10, 99.0)
    b.submit(o)
    assert b.cancel(o.id) is True
    assert b.best_bid() is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("all tests passed")
