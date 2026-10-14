"""Pydantic request/response schemas."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import Priority, TaskStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth / users ----
class RegisterIn(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=64)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=64)


class UserOut(ORMModel):
    id: int
    email: str
    display_name: str


class AuthOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---- boards ----
class BoardCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class MemberAdd(BaseModel):
    email: EmailStr


class MemberOut(ORMModel):
    user: UserOut
    role: str


# ---- tasks ----
class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    priority: Priority = Priority.MEDIUM
    assignee_ids: list[int] = []


class TaskUpdate(BaseModel):
    """Partial update: only fields present in the payload are changed."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: TaskStatus | None = None
    priority: Priority | None = None
    assignee_ids: list[int] | None = None


class TaskMove(BaseModel):
    status: TaskStatus
    index: int = Field(ge=0, description="Target index inside the destination column")


class TaskOut(ORMModel):
    id: int
    board_id: int
    title: str
    description: str
    status: TaskStatus
    priority: Priority
    position: float
    reporter_id: int | None
    assignees: list[UserOut]
    created_at: datetime
    updated_at: datetime


class BoardOut(ORMModel):
    id: int
    name: str
    owner_id: int
    created_at: datetime


class BoardDetail(BoardOut):
    members: list[MemberOut]
    tasks: list[TaskOut]


# ---- comments ----
class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class CommentOut(ORMModel):
    id: int
    task_id: int
    body: str
    created_at: datetime
    author: UserOut
