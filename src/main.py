from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.exceptions import DomainError, domain_error_handler
from src.health.router import router as health_router
from src.waitlist.router import router as waitlist_router

# Product endpoints live under /v1. Installed PWAs keep old code cached, so a breaking
# change ships as /v2 alongside /v1 instead of changing /v1 in place.
API_V1 = "/v1"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Reveal API",
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
    app.include_router(waitlist_router, prefix=API_V1)
    return app


app = create_app()
