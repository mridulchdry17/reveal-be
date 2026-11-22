import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import verified_user
from src.auth.schemas import Me
from src.chats import service
from src.chats.schemas import ChatSummary, ChatThread, MessageOut, SendMessage
from src.database import get_session
from src.schemas import ErrorResponse

router = APIRouter(prefix="/chats", tags=["chats"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Not signed in"},
    403: {"model": ErrorResponse, "description": "Not a verified student yet"},
}
_CHAT_ERRORS: dict[int | str, dict[str, Any]] = {
    **_ERRORS,
    404: {"model": ErrorResponse, "description": "No such live match"},
}

Student = Annotated[Me, Depends(verified_user)]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=list[ChatSummary], summary="My chats", responses=_ERRORS)
async def chats(user: Student, session: Session) -> list[ChatSummary]:
    return await service.chats(session, user)


@router.get("/{match_id}", response_model=ChatThread, summary="One chat", responses=_CHAT_ERRORS)
async def thread(match_id: uuid.UUID, user: Student, session: Session) -> ChatThread:
    return await service.thread(session, user, match_id)


@router.post(
    "/{match_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Send a message",
    responses=_CHAT_ERRORS,
)
async def send(
    match_id: uuid.UUID, body: SendMessage, user: Student, session: Session
) -> MessageOut:
    return await service.send(session, user, match_id, body.body)


@router.post(
    "/{match_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="I've seen the latest message",
    responses=_CHAT_ERRORS,
)
async def mark_read(match_id: uuid.UUID, user: Student, session: Session) -> None:
    await service.mark_read(session, user, match_id)
