from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class UserRole(str, Enum):
    admin = "admin"
    operator = "operator"


class User(BaseModel):
    username: str
    hashed_password: str
    role: UserRole = UserRole.operator
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
