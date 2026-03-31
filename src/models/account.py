from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class AccountStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


class Account(BaseModel):
    name: str
    space_id: str
    cdp_url: str
    web_port: int
    status: AccountStatus = AccountStatus.ACTIVE
    generating_count: int = 0
    max_concurrent: int = Field(default=10, ge=1)
