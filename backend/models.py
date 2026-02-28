"""Pydantic data models for boni memory API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Metrics(BaseModel):
    cpu_percent: float
    ram_percent: float
    battery_percent: Optional[float] = None
    is_charging: bool = False
    active_app: str = ""
    running_apps: int = 0
    hour: int = 0
    minute: int = 0


class Reaction(BaseModel):
    message: str
    mood: str = "chill"


class MemoryCreate(BaseModel):
    metrics: Metrics
    reaction: Reaction
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_id: str = "anonymous"


class MemoryRecord(BaseModel):
    id: str
    metrics: Metrics
    reaction: Reaction
    timestamp: datetime
    embedding_text: str = ""
    user_id: str = "anonymous"


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    user_id: str = "anonymous"


class MemorySearchResult(BaseModel):
    id: str
    timestamp: datetime
    reaction: Reaction
    metrics: Metrics
    similarity: float = 0.0


class SearchResponse(BaseModel):
    memories: list[MemorySearchResult] = []
