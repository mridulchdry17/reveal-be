import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.admin.router import router as admin_router
from src.auth.router import router as auth_router
from src.chats.router import router as chats_router
from src.config import settings
from src.drops.router import router as drops_router
from src.exceptions import DomainError, domain_error_handler
from src.guesses.router import router as guesses_router
from src.health.router import router as health_router
from src.hides.router import router as hides_router
from src.jobs import running
from src.matches.router import matches_router
from src.matches.router import router as likes_router
from src.notifications.router import router as notifications_router
from src.profiles.router import router as profiles_router
from src.safety.router import blocks_router
from src.safety.router import router as safety_router
from src.swaps.router import router as swaps_router
from src.verification.router import router as verification_router
from src.waitlist.router import router as waitlist_router

# Product endpoints live under /v1. Installed PWAs keep old code cached, so a breaking
# change ships as /v2 alongside /v1 instead of changing /v1 in place.
API_V1 = "/v1"


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Tests drive the jobs themselves; servers without VAPID keys have nothing to send.
    if settings.push_enabled and settings.environment != "test":
        async with running():
            yield
    else:
        yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Reveal API",
        lifespan=lifespan,
        version="0.1.0",
        openapi_url="/openapi.json" if settings.show_docs else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(DomainError, domain_error_handler)
    app.include_router(health_router)
    app.include_router(admin_router, prefix=API_V1)
    app.include_router(auth_router, prefix=API_V1)
    app.include_router(drops_router, prefix=API_V1)
    app.include_router(likes_router, prefix=API_V1)
    app.include_router(matches_router, prefix=API_V1)
    app.include_router(chats_router, prefix=API_V1)
    app.include_router(safety_router, prefix=API_V1)
    app.include_router(blocks_router, prefix=API_V1)
    app.include_router(hides_router, prefix=API_V1)
    app.include_router(notifications_router, prefix=API_V1)
    app.include_router(swaps_router, prefix=API_V1)
    app.include_router(guesses_router, prefix=API_V1)
    app.include_router(profiles_router, prefix=API_V1)
    app.include_router(verification_router, prefix=API_V1)
    app.include_router(waitlist_router, prefix=API_V1)
    return app


app = create_app()
