from datetime import datetime

from pydantic import BaseModel


class SessionRead(BaseModel):
    session_id: str
    expires_at: datetime
