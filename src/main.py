from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.exceptions import DomainError, domain_error_handler
from src.health.router import router as health_router


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
    return app


app = create_app()
