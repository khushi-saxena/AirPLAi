"""
The Event Tagging API — the core component.

Includes the human-in-the-loop workflow Arman described: CV proposes events as
`draft`; a human confirms or rejects them. Confirm/reject are first-class.
"""
import base64
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Event,
    EventSource,
    EventStatus,
    EventType,
    Game,
)
from app.schemas import EventCreate, EventOut, EventPage, ReviewAction

router = APIRouter(tags=["events"])


def _encode_cursor(occurred_at: datetime, event_id: UUID) -> str:
    raw = f"{occurred_at.isoformat()}|{event_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts, eid = raw.split("|")
    return datetime.fromisoformat(ts), UUID(eid)


def _get_game(db: Session, game_id: UUID) -> Game:
    game = db.get(Game, game_id)
    if not game:
        raise HTTPException(404, "Game not found")
    return game


def _resolve_event_type(db: Session, sport_code: str, code: str) -> EventType:
    et = db.scalar(
        select(EventType).where(
            EventType.sport_code == sport_code, EventType.code == code
        )
    )
    if not et:
        raise HTTPException(
            422, f"Unknown event type '{code}' for sport '{sport_code}'"
        )
    return et


@router.post("/games/{game_id}/events", response_model=EventOut, status_code=201)
def create_event(game_id: UUID, payload: EventCreate, db: Session = Depends(get_db)):
    game = _get_game(db, game_id)
    et = _resolve_event_type(db, game.sport_code, payload.event_type_code)

    # CV-proposed events land as drafts pending human review; human tags are
    # confirmed immediately.
    status = (
        EventStatus.draft
        if payload.source == EventSource.cv
        else EventStatus.confirmed
    )

    event = Event(
        game_id=game.id,
        event_type_id=et.id,
        period=payload.period,
        clock_ms=payload.clock_ms,
        occurred_at=payload.occurred_at,
        primary_player_id=payload.primary_player_id,
        team_id=payload.team_id,
        source=payload.source,
        confidence=payload.confidence,
        status=status,
        details=payload.details,
        created_by=payload.created_by,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get("/games/{game_id}/events", response_model=EventPage)
def list_events(
    game_id: UUID,
    db: Session = Depends(get_db),
    event_type_code: str | None = None,
    player_id: UUID | None = None,
    status: EventStatus | None = None,
    source: EventSource | None = None,
    limit: int = Query(50, le=200),
    cursor: str | None = None,
):
    _get_game(db, game_id)
    q = select(Event).where(Event.game_id == game_id)

    if event_type_code:
        q = q.join(EventType, Event.event_type_id == EventType.id).where(
            EventType.code == event_type_code
        )
    if player_id:
        q = q.where(Event.primary_player_id == player_id)
    if status:
        q = q.where(Event.status == status)
    if source:
        q = q.where(Event.source == source)

    # keyset pagination on the (occurred_at, id) index — stable under inserts
    if cursor:
        c_ts, c_id = _decode_cursor(cursor)
        q = q.where(
            (Event.occurred_at, Event.id) > (c_ts, c_id)
        )

    q = q.order_by(Event.occurred_at, Event.id).limit(limit + 1)
    rows = list(db.execute(q).scalars())

    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_cursor(last.occurred_at, last.id)
        rows = rows[:limit]

    return EventPage(items=rows, next_cursor=next_cursor)


@router.get("/games/{game_id}/review-queue", response_model=list[EventOut])
def review_queue(game_id: UUID, db: Session = Depends(get_db)):
    """CV-proposed events awaiting a human decision, lowest-confidence first."""
    _get_game(db, game_id)
    rows = db.execute(
        select(Event)
        .where(Event.game_id == game_id, Event.status == EventStatus.draft)
        .order_by(Event.confidence.asc().nullsfirst())
    ).scalars()
    return list(rows)


@router.get("/events/{event_id}", response_model=EventOut)
def get_event(event_id: UUID, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Event not found")
    return event


@router.post("/events/{event_id}/confirm", response_model=EventOut)
def confirm_event(event_id: UUID, action: ReviewAction, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Event not found")
    if event.status != EventStatus.draft:
        raise HTTPException(409, f"Event is '{event.status.value}', not a draft")
    event.status = EventStatus.confirmed
    event.reviewed_by = action.reviewed_by
    event.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(event)
    return event


@router.post("/events/{event_id}/reject", response_model=EventOut)
def reject_event(event_id: UUID, action: ReviewAction, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Event not found")
    if event.status != EventStatus.draft:
        raise HTTPException(409, f"Event is '{event.status.value}', not a draft")
    event.status = EventStatus.rejected
    event.reviewed_by = action.reviewed_by
    event.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(event)
    return event
