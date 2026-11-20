from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Body of every DomainError response. Clients branch on `code`, never on `detail`."""

    code: str
    detail: str
