"""WebSocket connection manager backed by Redis pub/sub.

Why Redis: with N server processes, a client on process A must see changes made via
process B. Every mutation is *published* to Redis channel `board:<id>`; each process runs
one pattern-subscriber (`board:*`) and forwards messages to ITS locally connected sockets.
Result: horizontal scalability with a single Redis subscription per process.

Event envelope (JSON):
    {"type": "task.moved", "board_id": 1, "origin": "<client-id>|null", "data": {...}}
"""
import asyncio
import json
import logging
from collections import defaultdict
from contextlib import suppress

import redis.asyncio as aioredis
from fastapi import WebSocket

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = "board:"
SEND_TIMEOUT = 5.0  # drop clients that can't keep up instead of stalling the broadcast


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[int, set[WebSocket]] = defaultdict(set)
        self._redis: aioredis.Redis | None = None
        self._listener: asyncio.Task | None = None

    # ---- lifecycle ----
    async def start(self, redis_url: str) -> None:
        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._listener = asyncio.create_task(self._listen(), name="redis-pubsub-listener")

    async def stop(self) -> None:
        if self._listener:
            self._listener.cancel()
            with suppress(asyncio.CancelledError):
                await self._listener
        if self._redis:
            await self._redis.aclose()

    # ---- local socket registry ----
    def connect(self, board_id: int, ws: WebSocket) -> None:
        self._rooms[board_id].add(ws)

    def disconnect(self, board_id: int, ws: WebSocket) -> None:
        room = self._rooms.get(board_id)
        if room:
            room.discard(ws)
            if not room:
                del self._rooms[board_id]

    @property
    def connection_count(self) -> int:
        return sum(len(r) for r in self._rooms.values())

    # ---- publish (called by REST handlers AFTER the DB commit) ----
    async def publish(self, board_id: int, event_type: str, data: dict, origin: str | None = None) -> None:
        """Fire-and-forget: a Redis outage must never fail the REST request."""
        if self._redis is None:
            return
        payload = json.dumps({"type": event_type, "board_id": board_id, "origin": origin, "data": data})
        try:
            await self._redis.publish(f"{CHANNEL_PREFIX}{board_id}", payload)
        except Exception:
            logger.exception("Redis publish failed (event %s, board %s)", event_type, board_id)

    # ---- subscribe loop (one per process) ----
    async def _listen(self) -> None:
        assert self._redis is not None
        backoff, first = 1.0, True
        while True:
            pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
            try:
                await pubsub.psubscribe(f"{CHANNEL_PREFIX}*")
                backoff = 1.0
                if not first:
                    # We may have missed events while disconnected: tell clients to resync.
                    await self._broadcast_refresh_all()
                first = False
                async for message in pubsub.listen():
                    await self._dispatch(message)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Redis subscriber error; retrying in %.0fs", backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
            finally:
                with suppress(Exception):
                    await pubsub.aclose()

    async def _dispatch(self, message: dict) -> None:
        if message.get("type") != "pmessage":
            return
        try:
            board_id = int(message["channel"].removeprefix(CHANNEL_PREFIX))
        except ValueError:
            return
        await self._broadcast_local(board_id, message["data"])

    async def _broadcast_refresh_all(self) -> None:
        for board_id in list(self._rooms):
            payload = json.dumps({"type": "board.refresh", "board_id": board_id, "origin": None, "data": {}})
            await self._broadcast_local(board_id, payload)

    async def _broadcast_local(self, board_id: int, payload: str) -> None:
        sockets = list(self._rooms.get(board_id, ()))
        if not sockets:
            return
        results = await asyncio.gather(*(self._safe_send(ws, payload) for ws in sockets))
        for ws, ok in zip(sockets, results):
            if not ok:
                self.disconnect(board_id, ws)

    @staticmethod
    async def _safe_send(ws: WebSocket, payload: str) -> bool:
        try:
            await asyncio.wait_for(ws.send_text(payload), SEND_TIMEOUT)
            return True
        except Exception:
            return False


manager = ConnectionManager()
