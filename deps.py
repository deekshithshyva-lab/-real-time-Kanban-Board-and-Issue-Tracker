"""Shared FastAPI dependencies and access-control helpers."""
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db
from .models import BoardMember, Task, User
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"}
    )
    if creds is None:
        raise unauthorized
    user_id = decode_token(creds.credentials)
    user = await db.get(User, user_id) if user_id else None
    if user is None:
        raise unauthorized
    return user


def get_origin(x_client_id: str | None = Header(default=None)) -> str | None:
    """Per-browser-window id sent by the frontend; echoed in events so a window can
    ignore the broadcast of its own action (optimistic updates)."""
    return x_client_id


async def require_board_member(db: AsyncSession, board_id: int, user_id: int) -> BoardMember:
    """404 (not 403) for non-members so board existence isn't leaked."""
    member = await db.get(BoardMember, (board_id, user_id))
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Board not found")
    return member


async def load_task_for_member(db: AsyncSession, task_id: int, user: User) -> Task:
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    await require_board_member(db, task.board_id, user.id)
    return task
