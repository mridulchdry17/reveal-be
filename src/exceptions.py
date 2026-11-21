from fastapi import Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """Base for errors raised by services. Mapped to HTTP in one place below."""

    status_code = 400
    code = "domain_error"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.code
        super().__init__(self.detail)


class Unauthenticated(DomainError):
    status_code = 401
    code = "unauthenticated"


class NotFound(DomainError):
    status_code = 404
    code = "not_found"


class PermissionDenied(DomainError):
    status_code = 403
    code = "permission_denied"


class Conflict(DomainError):
    status_code = 409
    code = "conflict"


class RateLimited(DomainError):
    status_code = 429
    code = "rate_limited"


async def domain_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):
        raise exc
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "detail": exc.detail},
    )
