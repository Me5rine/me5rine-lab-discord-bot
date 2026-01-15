import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    discord_bot_token: str
    admin_lab_api_key: str
    http_host: str = "127.0.0.1"
    http_port: int = 8787
    boosters_cache_seconds: int = 300
    role_members_cache_seconds: int = 300


def load_settings() -> Settings:
    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    key = os.getenv("ADMIN_LAB_API_KEY", "").strip()

    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN manquant dans .env")
    if not key:
        raise RuntimeError("ADMIN_LAB_API_KEY manquant dans .env")

    host = os.getenv("HTTP_HOST", "127.0.0.1").strip()
    port = int(os.getenv("HTTP_PORT", "8787").strip())

    boosters_cache_seconds = int(os.getenv("BOOSTERS_CACHE_SECONDS", "300").strip())
    role_members_cache_seconds = int(
        os.getenv("ROLE_MEMBERS_CACHE_SECONDS", str(boosters_cache_seconds)).strip()
    )

    return Settings(
        discord_bot_token=token,
        admin_lab_api_key=key,
        http_host=host,
        http_port=port,
        boosters_cache_seconds=boosters_cache_seconds,
        role_members_cache_seconds=role_members_cache_seconds,
    )
