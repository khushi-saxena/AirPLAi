"""
Projections over events.

This is where the design thesis becomes concrete: the box score, the scoreline,
and per-player stats are NOT stored as source data — they are COMPUTED from
confirmed events every time. Events are the single source of truth; everything
here is a derived view. In production this same logic backs a materialized view
refreshed at game end (and an incremental version for live stats).
"""
from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Event,
    EventStatus,
    EventType,
    Game,
    Player,
    TeamPlayer,
)
from app.schemas import GameSummary, PlayerStatLine

# Which event codes roll up into which stat line. Sport-agnostic: this map is
# derived from event_types in a fuller build; inlined here for the soccer demo.
STAT_RULES = {
    "goal": "goals",
    "assist": "assists",
    "shot": "shots",
    "foul": "fouls",
    "yellow_card": "yellow_cards",
    "red_card": "red_cards",
    "save": "saves",
}


def build_game_summary(db: Session, game: Game) -> GameSummary:
    # Only CONFIRMED events count toward official stats; CV drafts awaiting
    # human review are excluded until confirmed.
    rows = (
        db.execute(
            select(Event, EventType.code)
            .join(EventType, Event.event_type_id == EventType.id)
            .where(Event.game_id == game.id, Event.status == EventStatus.confirmed)
        )
        .all()
    )

    pending = db.scalar(
        select(Event.id)
        .where(Event.game_id == game.id, Event.status == EventStatus.draft)
        .limit(1)
    )
    pending_count = db.query(Event).filter(
        Event.game_id == game.id, Event.status == EventStatus.draft
    ).count()

    # tally per-player stats and the scoreline, purely from events
    per_player: dict[UUID, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    player_team: dict[UUID, UUID | None] = {}
    home_score = away_score = 0

    for event, code in rows:
        if code == "goal":
            if event.team_id == game.home_team_id:
                home_score += 1
            elif event.team_id == game.away_team_id:
                away_score += 1
        stat_key = STAT_RULES.get(code)
        if stat_key and event.primary_player_id:
            per_player[event.primary_player_id][stat_key] += 1
            player_team[event.primary_player_id] = event.team_id
        # assists are recorded inside a goal's details payload
        if code == "goal" and event.details.get("assist_player_id"):
            assist_id = UUID(event.details["assist_player_id"])
            per_player[assist_id]["assists"] += 1
            player_team.setdefault(assist_id, event.team_id)

    # resolve player names
    names: dict[UUID, str] = {}
    if per_player:
        for p in db.execute(
            select(Player).where(Player.id.in_(list(per_player.keys())))
        ).scalars():
            names[p.id] = p.full_name

    stat_lines = [
        PlayerStatLine(
            player_id=pid,
            player_name=names.get(pid, "Unknown"),
            team_id=player_team.get(pid),
            stats=dict(stats),
        )
        for pid, stats in per_player.items()
    ]
    stat_lines.sort(key=lambda s: (-s.stats.get("goals", 0), s.player_name))

    return GameSummary(
        game_id=game.id,
        status=game.status.value,
        home_team_id=game.home_team_id,
        away_team_id=game.away_team_id,
        home_score=home_score,
        away_score=away_score,
        event_count=len(rows),
        pending_review=pending_count,
        player_stats=stat_lines,
    )
