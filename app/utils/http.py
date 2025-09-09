
import aiohttp, asyncio, random
from aiohttp import ClientTimeout

# Network/Retry settings (shared)
NET_MAX_RETRIES = 5
NET_BASE_BACKOFF = 0.5   # seconds
NET_TIMEOUT = ClientTimeout(total=12, sock_connect=6, sock_read=6)

_aiohttp_session: aiohttp.ClientSession | None = None

async def get_http_session() -> aiohttp.ClientSession:
    global _aiohttp_session
    if _aiohttp_session is None or _aiohttp_session.closed:
        _aiohttp_session = aiohttp.ClientSession(timeout=NET_TIMEOUT)
    return _aiohttp_session

async def jitter_backoff(attempt: int) -> float:
    # exponential backoff with a small random jitter
    return NET_BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 0.2)
