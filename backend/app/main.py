import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.services.realtime.connection_manager import connection_manager
from app.services.realtime.redis_bus import subscribe_events

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
)

logger = logging.getLogger(__name__)


async def _forward_platform_events() -> None:
    """Relay Redis pub/sub events to connected WebSocket clients.

    Reconnects with backoff so the API stays healthy when Redis is down —
    the platform just isn't live until it returns.
    """
    while True:
        try:
            async for event in subscribe_events():
                await connection_manager.dispatch(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "platform_event_listener_reconnecting", extra={"error": str(exc)}
            )
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    listener = asyncio.create_task(_forward_platform_events())
    yield
    listener.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await listener


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": settings.app_name}
