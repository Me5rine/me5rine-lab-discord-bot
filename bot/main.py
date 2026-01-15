import asyncio
from aiohttp import web

from .settings import load_settings
from .discord_client import build_bot
from .api import start_api
from .features.subscriptions import SubscriptionFeature
from .features.role_members import RoleMembersFeature

async def main():
    settings = load_settings()
    bot = build_bot()

    app = web.Application()

    subs = SubscriptionFeature(
        bot=bot,
        api_key=settings.admin_lab_api_key,
        cache_seconds=settings.boosters_cache_seconds,
    )
    subs.register_routes(app)

    role_members = RoleMembersFeature(
        bot=bot,
        api_key=settings.admin_lab_api_key,
        cache_seconds=settings.role_members_cache_seconds,
    )
    role_members.register_routes(app)

    api_started = False

    @bot.event
    async def on_ready():
        nonlocal api_started
        print(f"[DISCORD] Logged in as {bot.user} (id={bot.user.id})")

        if not api_started:
            api_started = True
            bot.loop.create_task(start_api(app, settings.http_host, settings.http_port))

    await bot.start(settings.discord_bot_token)

if __name__ == "__main__":
    asyncio.run(main())
