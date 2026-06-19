from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Game
from app.schemas import GameSummary
from app.services import build_game_summary

router = APIRouter(tags=["games"])


@router.get("/games/{game_id}/summary", response_model=GameSummary)
def game_summary(game_id: UUID, db: Session = Depends(get_db)):
    """Live box score, computed from confirmed events (a projection, not stored)."""
    game = db.get(Game, game_id)
    if not game:
        raise HTTPException(404, "Game not found")
    return build_game_summary(db, game)


@router.get("/games")
def list_games(db: Session = Depends(get_db)):
    games = db.execute(select(Game)).scalars()
    return [
        {
            "id": str(g.id),
            "field_label": g.field_label,
            "status": g.status.value,
            "home_score": g.home_score,
            "away_score": g.away_score,
        }
        for g in games
    ]
