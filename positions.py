"""Fractional-index ordering for Kanban cards.

Each task has a float `position`. To drop a card at index i of a column we place it
midway between its new neighbours, so a move updates ONE row instead of renumbering the
column. If repeated bisection shrinks a gap below MIN_GAP we renumber that column.
"""
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Task, TaskStatus

GAP = 1024.0
MIN_GAP = 1e-6


async def compute_position(
    db: AsyncSession,
    board_id: int,
    status: TaskStatus,
    index: int,
    exclude_task_id: int | None = None,
) -> tuple[float, bool]:
    """Return (position, needs_rebalance) for inserting at `index` in the column.
    Use a huge index (e.g. 10**9) to append at the bottom."""
    stmt = (
        select(Task.position)
        .where(Task.board_id == board_id, Task.status == status)
        .order_by(Task.position, Task.id)
    )
    if exclude_task_id is not None:
        stmt = stmt.where(Task.id != exclude_task_id)
    positions = list((await db.execute(stmt)).scalars())

    if not positions:
        return GAP, False
    index = max(0, min(index, len(positions)))
    if index == 0:
        return positions[0] - GAP, False
    if index == len(positions):
        return positions[-1] + GAP, False
    lo, hi = positions[index - 1], positions[index]
    return (lo + hi) / 2, (hi - lo) < MIN_GAP * 2


async def rebalance_column(db: AsyncSession, board_id: int, status: TaskStatus) -> None:
    """Renumber a column to evenly spaced positions, preserving order."""
    ids = (
        await db.execute(
            select(Task.id)
            .where(Task.board_id == board_id, Task.status == status)
            .order_by(Task.position, Task.id)
        )
    ).scalars().all()
    for i, task_id in enumerate(ids, start=1):
        await db.execute(update(Task).where(Task.id == task_id).values(position=i * GAP))
