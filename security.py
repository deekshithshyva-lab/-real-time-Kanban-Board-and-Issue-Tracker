"""Password hashing (bcrypt, off the event loop) and JWT helpers."""
import asyncio
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings


def _pw(password: str) -> bytes:
    return password.encode()[:72]  # bcrypt's hard input limit


async def hash_password(password: str) -> str:
    hashed = await asyncio.to_thread(bcrypt.hashpw, _pw(password), bcrypt.gensalt())
    return hashed.decode()


async def verify_password(password: str, hashed: str) -> bool:
    return await asyncio.to_thread(bcrypt.checkpw, _pw(password), hashed.encode())


def create_access_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode(
        {"sub": str(user_id), "exp": expires}, settings.jwt_secret, algorithm=settings.jwt_algorithm
    )


def decode_token(token: str) -> int | None:
    """Return the user id, or None if the token is invalid/expired."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
