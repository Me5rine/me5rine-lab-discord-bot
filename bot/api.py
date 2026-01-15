from aiohttp import web

async def start_api(app: web.Application, host: str, port: int):
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"[HTTP] Listening on {host}:{port}")
