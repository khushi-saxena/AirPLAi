from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Clip,
    ClipSubject,
    ClipVisibility,
    Event,
    EventStatus,
    Player,
)
from app.schemas import EventOut

router = APIRouter(tags=["players"])


@router.get("/players/{player_id}/events", response_model=list[EventOut])
def player_events(player_id: UUID, db: Session = Depends(get_db)):
    """Every confirmed moment featuring this player, across all games."""
    if not db.get(Player, player_id):
        raise HTTPException(404, "Player not found")
    rows = db.execute(
        select(Event)
        .where(
            Event.primary_player_id == player_id,
            Event.status == EventStatus.confirmed,
        )
        .order_by(Event.occurred_at.desc())
    ).scalars()
    return list(rows)


@router.get("/players/{player_id}/clips")
def player_clips(player_id: UUID, db: Session = Depends(get_db)):
    """
    The parent use-case: every shareable clip featuring this player.
    One indexed join via clip_subjects — works even when the kid isn't the
    primary actor on the event.
    """
    if not db.get(Player, player_id):
        raise HTTPException(404, "Player not found")
    rows = db.execute(
        select(Clip)
        .join(ClipSubject, ClipSubject.clip_id == Clip.id)
        .where(
            ClipSubject.player_id == player_id,
            Clip.visibility != ClipVisibility.private,
        )
        .order_by(Clip.created_at.desc())
    ).scalars()
    return [
        {
            "id": str(c.id),
            "title": c.title,
            "status": c.status.value,
            "visibility": c.visibility.value,
            "storage_uri": c.storage_uri,
            "thumbnail_uri": c.thumbnail_uri,
        }
        for c in rows
    ]
