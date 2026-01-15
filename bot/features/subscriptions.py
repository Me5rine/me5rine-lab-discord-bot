import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

from aiohttp import web
from discord.ext import commands


@dataclass
class CacheEntry:
    ts: float
    payload: dict


class SubscriptionFeature:
    """
    GET /boosters?guild_id=...
    -> liste des boosters (premium_since)

    - Pas de guild.chunk()
    - Scan via REST guild.fetch_members(limit=None)
    - Cache TTL + lock + timeout
    """

    def __init__(
        self,
        bot: commands.Bot,
        api_key: str,
        cache_seconds: int = 300,
        build_timeout_seconds: int = 25,
    ):
        self.bot = bot
        self.api_key = api_key
        self.cache_seconds = max(10, int(cache_seconds))
        self.build_timeout_seconds = max(5, int(build_timeout_seconds))

        self._cache: dict[int, CacheEntry] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    def _auth(self, request: web.Request):
        key = request.headers.get("x-admin-lab-key", "")
        if key != self.api_key:
            raise web.HTTPUnauthorized(
                text=json.dumps({"error": "unauthorized"}),
                content_type="application/json",
            )

    def _get_lock(self, guild_id: int) -> asyncio.Lock:
        lock = self._locks.get(guild_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[guild_id] = lock
        return lock

    def _cache_valid(self, entry: CacheEntry) -> bool:
        return (time.time() - entry.ts) < self.cache_seconds

    async def _build_payload(self, guild_id: int) -> dict[str, Any]:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "guild_not_found_or_no_access"}),
                content_type="application/json",
            )

        boosters: list[dict[str, Any]] = []

        async def _scan():
            async for m in guild.fetch_members(limit=None):
                if m.premium_since:
                    boosters.append(
                        {
                            "discord_user_id": str(m.id),
                            "username": m.name,
                            "display_name": m.display_name,
                            "premium_since": m.premium_since.isoformat(),
                        }
                    )

        try:
            await asyncio.wait_for(_scan(), timeout=self.build_timeout_seconds)
        except asyncio.TimeoutError:
            raise web.HTTPAccepted(
                text=json.dumps(
                    {
                        "status": "building_cache",
                        "guild_id": str(guild_id),
                    }
                ),
                content_type="application/json",
            )

        return {
            "guild_id": str(guild.id),
            "guild_name": guild.name,
            "count": len(boosters),
            "boosters": boosters,
        }

    def register_routes(self, app: web.Application):
        app.router.add_get("/health", self.health)
        app.router.add_get("/boosters", self.boosters)

    async def health(self, request: web.Request):
        return web.json_response({"ok": True})

    async def boosters(self, request: web.Request):
        self._auth(request)

        gid = request.query.get("guild_id", "").strip()
        if not gid:
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "missing guild_id"}),
                content_type="application/json",
            )
        try:
            guild_id = int(gid)
        except ValueError:
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "invalid guild_id"}),
                content_type="application/json",
            )

        entry = self._cache.get(guild_id)
        if entry and self._cache_valid(entry):
            return web.json_response(entry.payload)

        lock = self._get_lock(guild_id)
        if lock.locked():
            raise web.HTTPAccepted(
                text=json.dumps({"status": "building_cache", "guild_id": str(guild_id)}),
                content_type="application/json",
            )

        async with lock:
            entry2 = self._cache.get(guild_id)
            if entry2 and self._cache_valid(entry2):
                return web.json_response(entry2.payload)

            payload = await self._build_payload(guild_id)
            self._cache[guild_id] = CacheEntry(ts=time.time(), payload=payload)
            return web.json_response(payload)
