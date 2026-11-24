from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import verified_user
from src.auth.schemas import Me
from src.database import get_session
from src.notifications import service
from src.notifications.schemas import PushConfig, SubscriptionIn, Unsubscribe
from src.schemas import ErrorResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Not signed in"},
    403: {"model": ErrorResponse, "description": "Not a verified student yet"},
}

Student = Annotated[Me, Depends(verified_user)]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/config", response_model=PushConfig, summary="The key a device subscribes with")
async def config() -> PushConfig:
    return service.config()


@router.put(
    "/subscription",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="This device wants notifications",
    responses=_ERRORS,
)
async def subscribe(body: SubscriptionIn, user: Student, session: Session) -> None:
    await service.subscribe(session, user, body)


@router.post(
    "/subscription/remove",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="This device doesn't want notifications any more",
    responses=_ERRORS,
)
async def unsubscribe(body: Unsubscribe, user: Student, session: Session) -> None:
    await service.unsubscribe(session, user, body.endpoint)
