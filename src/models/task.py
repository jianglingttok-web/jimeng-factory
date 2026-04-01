from __future__ import annotations

import time
import uuid
from enum import StrEnum

from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    PENDING = "pending"
    SUBMITTING = "submitting"
    GENERATING = "generating"
    DOWNLOADING = "downloading"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Task(BaseModel):
    task_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    product_name: str
    variant_id: str
    prompt: str
    account_name: str
    status: TaskStatus = TaskStatus.PENDING
    result_video_path: str | None = None
    error_message: str | None = None
    retry_count: int = 0
    max_retries: int = 2
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    submitted_at: float | None = None
    result_url: str | None = None
    duration_seconds: int | None = None
