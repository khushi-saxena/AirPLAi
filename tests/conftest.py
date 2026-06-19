import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import (
    EventType,
    Game,
    GameStatus,
    League,
    Player,
    Season,
    Sport,
    Team,
)


@pytest.fixture()
def client():
    # fresh file-backed sqlite per test so connections share state
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    db = TestingSession()
    soccer = Sport(code="soccer", display_name="Soccer")
    db.add(soccer)
    db.add_all([
        EventType(sport_code="soccer", code="goal", display_name="Goal", is_scoring=True),
        EventType(sport_code="soccer", code="shot", display_name="Shot"),
    ])
    league = League(name="Test League", sport_code="soccer")
    db.add(league); db.flush()
    season = Season(league_id=league.id, name="2025")
    db.add(season); db.flush()
    home = Team(league_id=league.id, name="Home")
    away = Team(league_id=league.id, name="Away")
    db.add_all([home, away]); db.flush()
    player = Player(full_name="Test Striker")
    db.add(player); db.flush()
    game = Game(league_id=league.id, season_id=season.id, sport_code="soccer",
                home_team_id=home.id, away_team_id=away.id, status=GameStatus.live)
    db.add(game); db.commit()

    ctx = {"game_id": str(game.id), "team_id": str(home.id), "player_id": str(player.id)}
    db.close()

    def override_get_db():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    c = TestClient(app)
    c.ctx = ctx
    yield c
    app.dependency_overrides.clear()
    os.unlink(path)
