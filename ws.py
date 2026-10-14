"""WebSocket endpoint: ws://host/ws/boards/{board_id}?token=<JWT>

Browsers can't set an Authorization header on WebSockets, so the JWT goes in the query
string. The socket is receive-only for data (all writes go through REST, which publishes
to Redis); the client may send the text "ping" as a keep-alive and gets "pong" back.
Close codes: 4401 = bad/missing token, 4403 = not a board member.
"""
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..database import SessionLocal
from ..models import BoardMember
from ..realtime.manager import manager
from ..security import decode_token

router = APIRouter()


@router.websocket("/ws/boards/{board_id}")
async def board_socket(websocket: WebSocket, board_id: int, token: str = Query(default="")):
    await websocket.accept()

    user_id = decode_token(token)
    if user_id is None:
        await websocket.close(code=4401)
        return
    async with SessionLocal() as db:  # short-lived session: not held for the socket's lifetime
        is_member = await db.get(BoardMember, (board_id, user_id)) is not None
    if not is_member:
        await websocket.close(code=4403)
        return

    manager.connect(board_id, websocket)
    try:
        while True:
            if await websocket.receive_text() == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(board_id, websocket)
