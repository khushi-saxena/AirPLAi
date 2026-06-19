from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

from app.models import EventSource, EventStatus


# --- events ------------------------------------------------------------------
class EventCreate(BaseModel):
    event_type_code: str = Field(..., examples=["goal"])
    occurred_at: datetime
    period: int | None = None
    clock_ms: int | None = None
    primary_player_id: UUID | None = None
    team_id: UUID | None = None
    source: EventSource = EventSource.human
    confidence: float | None = Field(None, ge=0, le=1)
    details: dict = Field(default_factory=dict)
    created_by: str | None = None


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    game_id: UUID
    event_type_id: UUID
    period: int | None
    clock_ms: int | None
    occurred_at: datetime
    primary_player_id: UUID | None
    team_id: UUID | None
    source: EventSource
    confidence: float | None
    status: EventStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    details: dict
    created_by: str | None
    created_at: datetime


class EventPage(BaseModel):
    items: list[EventOut]
    next_cursor: str | None = None


class ReviewAction(BaseModel):
    reviewed_by: str = Field(..., examples=["coach_dana"])


# --- projections (stats / summary) -------------------------------------------
class PlayerStatLine(BaseModel):
    player_id: UUID
    player_name: str
    team_id: UUID | None
    stats: dict[str, float]


class GameSummary(BaseModel):
    game_id: UUID
    status: str
    home_team_id: UUID
    away_team_id: UUID
    home_score: int
    away_score: int
    event_count: int
    pending_review: int
    player_stats: list[PlayerStatLine]
