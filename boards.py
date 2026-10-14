from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import get_current_user, get_origin, require_board_member
from ..models import Board, BoardMember, Task, User
from ..realtime.manager import manager
from ..schemas import BoardCreate, BoardDetail, BoardOut, MemberAdd, MemberOut

router = APIRouter(prefix="/boards", tags=["boards"])


@router.post("", response_model=BoardOut, status_code=status.HTTP_201_CREATED)
async def create_board(body: BoardCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    board = Board(name=body.name, owner_id=user.id, members=[BoardMember(user_id=user.id, role="owner")])
    db.add(board)
    await db.commit()
    return board


@router.get("", response_model=list[BoardOut])
async def list_boards(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = (
        select(Board)
        .join(BoardMember, BoardMember.board_id == Board.id)
        .where(BoardMember.user_id == user.id)
        .order_by(Board.created_at.desc())
    )
    return (await db.execute(stmt)).scalars().all()


@router.get("/{board_id}", response_model=BoardDetail)
async def get_board(board_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Full board snapshot (members + every task). The frontend loads this once, then
    stays in sync through WebSocket events."""
    await require_board_member(db, board_id, user.id)
    board = await db.get(Board, board_id)
    tasks = (
        await db.execute(select(Task).where(Task.board_id == board_id).order_by(Task.position, Task.id))
    ).scalars().all()
    return {
        "id": board.id, "name": board.name, "owner_id": board.owner_id,
        "created_at": board.created_at, "members": board.members, "tasks": tasks,
    }


@router.delete("/{board_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_board(board_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    member = await require_board_member(db, board_id, user.id)
    if member.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can delete a board")
    await db.delete(await db.get(Board, board_id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{board_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
async def add_member(
    board_id: int,
    body: MemberAdd,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    origin: str | None = Depends(get_origin),
):
    member = await require_board_member(db, board_id, user.id)
    if member.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can add members")
    target = (await db.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No user with that email")
    if await db.get(BoardMember, (board_id, target.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Already a member")
    db.add(BoardMember(board_id=board_id, user_id=target.id, role="member"))
    await db.commit()
    out = MemberOut(user=target, role="member")
    await manager.publish(board_id, "member.added", out.model_dump(mode="json"), origin)
    return out
