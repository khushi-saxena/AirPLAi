"""
Data model for the Game Day Operations Engine.

Design thesis: EVENTS are the single source of truth.
Stats, clips, dashboards and highlight reels are all PROJECTIONS over events.

Types are written to be portable: Postgres in production (UUID, JSONB, native
enums) and SQLite for a zero-setup local run. The GIN index on events.details
is added as a Postgres-only production migration (see alembic/ and README).
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# JSONB on Postgres, plain JSON on SQLite.
JSONFlexible = JSON().with_variant(JSONB, "postgresql")


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# --- enums -------------------------------------------------------------------
class GameStatus(str, enum.Enum):
    scheduled = "scheduled"
    live = "live"
    final = "final"
    canceled = "canceled"


class AssetStatus(str, enum.Enum):
    uploading = "uploading"
    uploaded = "uploaded"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class EventSource(str, enum.Enum):
    human = "human"
    cv = "cv"
    import_ = "import"


class EventStatus(str, enum.Enum):
    draft = "draft"
    confirmed = "confirmed"
    rejected = "rejected"


class ClipStatus(str, enum.Enum):
    queued = "queued"
    rendering = "rendering"
    ready = "ready"
    failed = "failed"


class ClipVisibility(str, enum.Enum):
    private = "private"
    team = "team"
    league = "league"
    public = "public"


# --- sport config (multi-sport without migrations) ---------------------------
class Sport(Base):
    __tablename__ = "sports"
    code: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    has_game_clock: Mapped[bool] = mapped_column(Boolean, default=True)
    period_count: Mapped[int] = mapped_column(Integer, default=2)
    period_length_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class EventType(Base):
    __tablename__ = "event_types"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    sport_code: Mapped[str] = mapped_column(ForeignKey("sports.code"), nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    is_scoring: Mapped[bool] = mapped_column(Boolean, default=False)
    clip_lead_ms: Mapped[int] = mapped_column(Integer, default=8000)
    clip_trail_ms: Mapped[int] = mapped_column(Integer, default=5000)
    details_schema: Mapped[dict | None] = mapped_column(JSONFlexible, nullable=True)
    __table_args__ = (UniqueConstraint("sport_code", "code", name="uq_event_type"),)


# --- org hierarchy -----------------------------------------------------------
class League(Base):
    __tablename__ = "leagues"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    sport_code: Mapped[str] = mapped_column(ForeignKey("sports.code"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Season(Base):
    __tablename__ = "seasons"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    league_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    starts_on: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    ends_on: Mapped[datetime | None] = mapped_column(Date, nullable=True)


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    league_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String, nullable=False)


class Player(Base):
    __tablename__ = "players"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    birthdate: Mapped[datetime | None] = mapped_column(Date, nullable=True)


class TeamPlayer(Base):
    __tablename__ = "team_players"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"))
    jersey_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[str | None] = mapped_column(String, nullable=True)
    __table_args__ = (UniqueConstraint("team_id", "player_id", "season_id", name="uq_roster"),)


# --- games & video -----------------------------------------------------------
class Game(Base):
    __tablename__ = "games"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    league_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leagues.id"))
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seasons.id"))
    sport_code: Mapped[str] = mapped_column(ForeignKey("sports.code"))
    home_team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"))
    field_label: Mapped[str | None] = mapped_column(String, nullable=True)
    scheduled_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[GameStatus] = mapped_column(Enum(GameStatus), default=GameStatus.scheduled)
    home_score: Mapped[int] = mapped_column(Integer, default=0)
    away_score: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VideoAsset(Base):
    __tablename__ = "video_assets"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    game_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"))
    camera_label: Mapped[str] = mapped_column(String, nullable=False)
    storage_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[AssetStatus] = mapped_column(Enum(AssetStatus), default=AssetStatus.uploading)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recorded_start_wall_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_offset_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- events: THE SPINE -------------------------------------------------------
class Event(Base):
    __tablename__ = "events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    game_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"))
    event_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event_types.id"))
    # three deliberately separate clocks:
    period: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clock_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)          # game clock (display)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # wall clock (authoritative)
    # who / which side:
    primary_player_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    # provenance — human + CV coexist with a review workflow:
    source: Mapped[EventSource] = mapped_column(Enum(EventSource), default=EventSource.human)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    status: Mapped[EventStatus] = mapped_column(Enum(EventStatus), default=EventStatus.confirmed)
    reviewed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # sport-specific payload:
    details: Mapped[dict] = mapped_column(JSONFlexible, default=dict)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    event_type: Mapped["EventType"] = relationship(lazy="joined")

    __table_args__ = (
        Index("idx_events_game_time", "game_id", "occurred_at", "id"),
        Index("idx_events_player_type", "primary_player_id", "event_type_id"),
        Index("idx_events_game_type", "game_id", "event_type_id"),
    )


# --- clips -------------------------------------------------------------------
class Clip(Base):
    __tablename__ = "clips"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    game_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"))
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"), nullable=True)
    video_asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("video_assets.id"))
    start_offset_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ClipStatus] = mapped_column(Enum(ClipStatus), default=ClipStatus.queued)
    visibility: Mapped[ClipVisibility] = mapped_column(Enum(ClipVisibility), default=ClipVisibility.team)
    storage_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        Index("idx_clips_event", "event_id"),
        Index("idx_clips_game", "game_id"),
    )


class ClipSubject(Base):
    __tablename__ = "clip_subjects"
    clip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clips.id", ondelete="CASCADE"), primary_key=True)
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    __table_args__ = (Index("idx_clip_subjects_player", "player_id"),)
