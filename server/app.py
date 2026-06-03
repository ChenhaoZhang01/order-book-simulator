"""WebSocket order-book server.

Exposes a REST endpoint to submit orders and a WebSocket that streams the
live book depth + trade prints to every connected client. A background task
injects random liquidity so the book is alive out of the box.
"""

from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))
from orderbook import OrderBook, Order, Side, OrderType  # noqa: E402

app = FastAPI(title="Order Book Simulator")
book = OrderBook("SIM")


class Hub:
    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket):
        self.clients.discard(ws)

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


hub = Hub()


class OrderIn(BaseModel):
    side: str
    quantity: int
    price: float | None = None
    order_type: str = "limit"


async def push_state(trades=None):
    await hub.broadcast(
        {
            "type": "state",
            "depth": book.depth(),
            "trades": [t.as_dict() for t in (trades or [])],
        }
    )


@app.post("/order")
async def submit_order(o: OrderIn):
    order = Order(
        side=Side(o.side),
        quantity=o.quantity,
        price=o.price,
        order_type=OrderType(o.order_type),
    )
    trades = book.submit(order)
    await push_state(trades)
    return {"order_id": order.id, "trades": [t.as_dict() for t in trades]}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await hub.connect(ws)
    await ws.send_json({"type": "state", "depth": book.depth(), "trades": []})
    try:
        while True:
            await ws.receive_text()  # keepalive / ignore client msgs
    except WebSocketDisconnect:
        hub.disconnect(ws)


async def liquidity_bot():
    """Random walk of limit + market orders so the book moves."""
    mid = 100.0
    while True:
        await asyncio.sleep(0.8)
        mid += random.uniform(-0.3, 0.3)
        if random.random() < 0.25:
            side = random.choice([Side.BUY, Side.SELL])
            book.submit(Order(side, random.randint(1, 5), order_type=OrderType.MARKET))
        else:
            side = random.choice([Side.BUY, Side.SELL])
            offset = random.uniform(0.05, 1.5)
            price = round(mid - offset if side == Side.BUY else mid + offset, 2)
            book.submit(Order(side, random.randint(1, 8), price))
        await push_state()


@app.on_event("startup")
async def _start():
    asyncio.create_task(liquidity_bot())


@app.get("/")
async def index():
    return HTMLResponse((Path(__file__).parent / "client.html").read_text())
