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


class RoleMembersFeature:
    """
    GET /role-members?guild_id=...&role_id=...
    -> renvoie uniquement des IDs de membres ayant le rôle

    - Pas de guild.chunk() (peut bloquer)
    - Scan via REST: guild.fetch_members(limit=None)
    - Cache TTL + lock (1 seul scan à la fois par guild/role)
    - Timeout pour ne jamais bloquer indéfiniment
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

        self._cache: dict[tuple[int, int], CacheEntry] = {}
        self._locks: dict[tuple[int, int], asyncio.Lock] = {}

    def _auth(self, request: web.Request):
        key = request.headers.get("x-admin-lab-key", "")
        if key != self.api_key:
            raise web.HTTPUnauthorized(
                text=json.dumps({"error": "unauthorized"}),
                content_type="application/json",
            )

    def _get_lock(self, cache_key: tuple[int, int]) -> asyncio.Lock:
        lock = self._locks.get(cache_key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[cache_key] = lock
        return lock

    def _cache_valid(self, entry: CacheEntry) -> bool:
        return (time.time() - entry.ts) < self.cache_seconds

    async def _build_payload(self, guild_id: int, role_id: int) -> dict[str, Any]:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "guild_not_found_or_no_access"}),
                content_type="application/json",
            )

        # IMPORTANT :
        # fetch_members utilise l’API REST, pas le cache gateway.
        # Il faut quand même que ton bot ait la permission "Server Members Intent"
        # activée dans le Dev Portal (sinon discord peut limiter).
        member_ids: list[str] = []

        # Scan de tous les membres, mais avec timeout global (sinon ça peut durer trop)
        async def _scan():
            async for member in guild.fetch_members(limit=None):
                # member.roles contient toujours @everyone + rôles si dispo
                if any(r.id == role_id for r in member.roles):
                    member_ids.append(str(member.id))

        try:
            await asyncio.wait_for(_scan(), timeout=self.build_timeout_seconds)
        except asyncio.TimeoutError:
            # On renvoie un 202 "building_cache" au lieu de bloquer.
            # La requête suivante réessaiera.
            raise web.HTTPAccepted(
                text=json.dumps(
                    {
                        "status": "building_cache",
                        "guild_id": str(guild_id),
                        "role_id": str(role_id),
                    }
                ),
                content_type="application/json",
            )

        # Nom du rôle : on tente via cache local (sans chunk), sinon "unknown"
        role_name = "unknown"
        role = guild.get_role(role_id)
        if role is not None:
            role_name = role.name

        payload = {
            "guild_id": str(guild.id),
            "guild_name": guild.name,
            "role_id": str(role_id),
            "role_name": role_name,
            "count": len(member_ids),
            "members": [{"discord_user_id": mid} for mid in member_ids],
        }
        return payload

    async def handler(self, request: web.Request):
        self._auth(request)

        gid = request.query.get("guild_id", "").strip()
        rid = request.query.get("role_id", "").strip()

        if not gid:
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "missing guild_id"}),
                content_type="application/json",
            )
        if not rid:
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "missing role_id"}),
                content_type="application/json",
            )

        try:
            guild_id = int(gid)
            role_id = int(rid)
        except ValueError:
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "invalid guild_id_or_role_id"}),
                content_type="application/json",
            )

        cache_key = (guild_id, role_id)

        # Cache hit
        entry = self._cache.get(cache_key)
        if entry and self._cache_valid(entry):
            return web.json_response(entry.payload)

        # 1 seul build à la fois par (guild, role)
        lock = self._get_lock(cache_key)
        if lock.locked():
            # quelqu’un est déjà en train de construire => 202 immédiat
            raise web.HTTPAccepted(
                text=json.dumps(
                    {
                        "status": "building_cache",
                        "guild_id": str(guild_id),
                        "role_id": str(role_id),
                    }
                ),
                content_type="application/json",
            )

        async with lock:
            # Re-check cache (une autre requête a pu le remplir juste avant nous)
            entry2 = self._cache.get(cache_key)
            if entry2 and self._cache_valid(entry2):
                return web.json_response(entry2.payload)

            payload = await self._build_payload(guild_id, role_id)
            self._cache[cache_key] = CacheEntry(ts=time.time(), payload=payload)
            return web.json_response(payload)

    def register_routes(self, app: web.Application):
        app.router.add_get("/role-members", self.handler)
