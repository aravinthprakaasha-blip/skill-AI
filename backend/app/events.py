"""Realtime event bus: WebSocket fan-out, bridged through Redis pub/sub when workers are separate."""
import asyncio
import json
import logging

from fastapi import WebSocket

from .config import get_settings

log = logging.getLogger("skillforge.events")
settings = get_settings()
CHANNEL = "skillforge:events"


class ConnectionManager:
    def __init__(self) -> None:
        self.rooms: dict[str, set[WebSocket]] = {}

    async def connect(self, profile_id: str, ws: WebSocket) -> None:
        self.rooms.setdefault(profile_id, set()).add(ws)

    def disconnect(self, profile_id: str, ws: WebSocket) -> None:
        self.rooms.get(profile_id, set()).discard(ws)

    async def broadcast(self, profile_id: str, message: dict) -> None:
        for ws in list(self.rooms.get(profile_id, ())):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(profile_id, ws)


manager = ConnectionManager()


async def publish(profile_id: str, message: dict) -> None:
    """Called by agents. Never raises: realtime delivery is best-effort."""
    try:
        if settings.redis_url:
            import redis.asyncio as aioredis

            client = aioredis.from_url(settings.redis_url)
            try:
                await client.publish(CHANNEL, json.dumps({"profile_id": profile_id, "message": message}, default=str))
            finally:
                await client.aclose()
        else:
            await manager.broadcast(profile_id, message)
    except Exception as exc:
        log.warning("event publish failed: %s", type(exc).__name__)


async def redis_listener() -> None:
    """API-side relay: Redis channel -> connected WebSockets."""
    import redis.asyncio as aioredis

    while True:
        try:
            client = aioredis.from_url(settings.redis_url)
            pubsub = client.pubsub()
            await pubsub.subscribe(CHANNEL)
            async for item in pubsub.listen():
                if item.get("type") == "message":
                    data = json.loads(item["data"])
                    await manager.broadcast(data["profile_id"], data["message"])
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("redis listener error (%s); retrying", type(exc).__name__)
            await asyncio.sleep(3)
