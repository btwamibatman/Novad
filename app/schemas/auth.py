from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class AuthUserRead(BaseModel):
    id: int
    username: str


class AuthSessionRead(BaseModel):
    session_id: str
    expires_at: datetime
    user: AuthUserRead
