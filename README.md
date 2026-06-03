# Order Book Simulator

A live **limit order book** with a real matching engine, streamed to the
browser over **WebSockets**. The kind of core data structure trading firms
(Jane Street, Citadel, Optiver) actually quiz you on.

![stack](https://img.shields.io/badge/stack-Python%20·%20FastAPI%20·%20WebSockets-1f6feb)

## What it does

- **Price-time priority** matching: best price first, FIFO within a price.
- **Limit** orders rest in the book; **market** orders sweep the opposite side.
- Partial fills, cancels, and live **top-of-book / spread / last trade**.
- A built-in liquidity bot random-walks the mid so the book is alive on load.
- Real-time **depth ladder** + **trade tape** in the browser, plus a manual
  order-entry form.

## Architecture

```
engine/
  orderbook.py        matching engine (heaps of price levels, FIFO queues)
  test_orderbook.py   priority, partials, market sweeps, cancels
server/
  app.py              FastAPI: POST /order, WS /ws, liquidity bot
  client.html         depth ladder + trade tape (vanilla JS)
```

The engine is **pure Python, dependency-free** — you can drop `orderbook.py`
into any project. The server is a thin transport layer over it.

## Run it

```bash
pip install -r requirements.txt
uvicorn server.app:app --reload --port 8000
# open http://localhost:8000
```

Watch the bot trade, then submit your own limit/market orders from the form
and see them match against resting liquidity.

## Tests

```bash
cd engine && python test_orderbook.py     # or: pytest
```

Covered: resting & top-of-book, full/partial fills, **price priority**,
**time priority (FIFO)**, market-order sweeps across levels, cancels.

## Design notes

- Bids are a max-heap (negated), asks a min-heap; each price maps to a
  `PriceLevel` FIFO `deque`. Matching at the touch is O(1); best-price
  lookup is O(log n) amortized with lazy deletion of emptied levels.
- The engine is synchronous and deterministic — easy to test and to replay.
  The async layer only handles I/O and broadcasting.
