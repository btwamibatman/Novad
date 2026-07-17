from datetime import datetime

from pydantic import BaseModel


class SessionRead(BaseModel):
    session_id: str
    user_id: int
    expires_at: datetime
