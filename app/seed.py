"""
Seed a realistic youth-soccer game so the API has something to serve.

Includes a mix of human-confirmed events and CV-proposed DRAFTS (with confidence
scores) sitting in the review queue — mirroring the human-in-the-loop workflow.

Run:  python -m app.seed
"""
from datetime import datetime, timedelta, timezone

from app.database import Base, SessionLocal, engine
from app.models import (
    Clip,
    ClipSubject,
    ClipVisibility,
    Event,
    EventSource,
    EventStatus,
    EventType,
    Game,
    GameStatus,
    League,
    Player,
    Season,
    Sport,
    Team,
    TeamPlayer,
    VideoAsset,
)

SOCCER_EVENT_TYPES = [
    # code, display, is_scoring, lead_ms, trail_ms
    ("goal", "Goal", True, 10000, 6000),
    ("shot", "Shot", False, 6000, 4000),
    ("assist", "Assist", False, 8000, 4000),
    ("foul", "Foul", False, 4000, 4000),
    ("yellow_card", "Yellow Card", False, 5000, 5000),
    ("red_card", "Red Card", False, 6000, 6000),
    ("save", "Save", False, 5000, 4000),
    ("substitution", "Substitution", False, 3000, 3000),
    ("corner_kick", "Corner Kick", False, 6000, 6000),
]


def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed():
    reset_db()
    db = SessionLocal()
    try:
        # --- sport + event type catalog ---
        soccer = Sport(
            code="soccer", display_name="Soccer", has_game_clock=True,
            period_count=2, period_length_ms=45 * 60 * 1000,
        )
        db.add(soccer)
        et = {}
        for code, name, scoring, lead, trail in SOCCER_EVENT_TYPES:
            obj = EventType(
                sport_code="soccer", code=code, display_name=name,
                is_scoring=scoring, clip_lead_ms=lead, clip_trail_ms=trail,
            )
            db.add(obj)
            et[code] = obj
        db.flush()

        # --- league / season / teams ---
        league = League(name="Georgia Basketball Association — Soccer Div", sport_code="soccer")
        db.add(league)
        db.flush()
        season = Season(league_id=league.id, name="Spring 2025")
        db.add(season)
        db.flush()

        falcons = Team(league_id=league.id, name="Decatur Falcons")
        hawks = Team(league_id=league.id, name="Marietta Hawks")
        db.add_all([falcons, hawks])
        db.flush()

        # --- players + rosters ---
        roster = {
            falcons: [("Maya Patel", 7, "FW"), ("Sofia Reyes", 10, "MF"),
                      ("Ava Chen", 1, "GK"), ("Liam Okafor", 4, "DF")],
            hawks: [("Noah Williams", 9, "FW"), ("Diego Santos", 8, "MF"),
                    ("Ethan Park", 12, "GK"), ("Jordan Blake", 5, "DF")],
        }
        players = {}
        for team, plist in roster.items():
            for name, num, pos in plist:
                p = Player(full_name=name)
                db.add(p)
                db.flush()
                db.add(TeamPlayer(team_id=team.id, player_id=p.id,
                                  season_id=season.id, jersey_number=num, position=pos))
                players[name] = p
        db.flush()

        # --- game + cameras ---
        kickoff = datetime(2025, 4, 12, 10, 0, 0, tzinfo=timezone.utc)
        game = Game(
            league_id=league.id, season_id=season.id, sport_code="soccer",
            home_team_id=falcons.id, away_team_id=hawks.id,
            field_label="Field 3", scheduled_start=kickoff, status=GameStatus.final,
        )
        db.add(game)
        db.flush()

        sideline = VideoAsset(
            game_id=game.id, camera_label="sideline", status="ready",
            duration_ms=95 * 60 * 1000, recorded_start_wall_time=kickoff,
            sync_offset_ms=0, storage_uri="s3://airplai-demo/field3/sideline.mp4",
        )
        goalcam = VideoAsset(
            game_id=game.id, camera_label="goal-cam", status="ready",
            duration_ms=95 * 60 * 1000,
            recorded_start_wall_time=kickoff + timedelta(seconds=12),  # started 12s late
            sync_offset_ms=12000, storage_uri="s3://airplai-demo/field3/goalcam.mp4",
        )
        db.add_all([sideline, goalcam])
        db.flush()

        def ev(minute, code, player=None, team=None, source=EventSource.human,
               confidence=None, status=None, details=None):
            wall = kickoff + timedelta(minutes=minute)
            st = status or (EventStatus.draft if source == EventSource.cv else EventStatus.confirmed)
            return Event(
                game_id=game.id, event_type_id=et[code].id,
                period=1 if minute <= 45 else 2,
                clock_ms=int(minute * 60 * 1000),
                occurred_at=wall,
                primary_player_id=players[player].id if player else None,
                team_id=team.id if team else None,
                source=source, confidence=confidence, status=st,
                details=details or {}, created_by="ops_tagger" if source == EventSource.human else "cv_pipeline_v1",
            )

        events = [
            # confirmed, human-tagged
            ev(6, "shot", "Maya Patel", falcons),
            ev(11, "goal", "Maya Patel", falcons,
               details={"assist_player_id": str(players["Sofia Reyes"].id), "shot_type": "header"}),
            ev(23, "foul", "Jordan Blake", hawks),
            ev(24, "yellow_card", "Jordan Blake", hawks),
            ev(31, "save", "Ava Chen", falcons),
            ev(38, "goal", "Noah Williams", hawks,
               details={"assist_player_id": str(players["Diego Santos"].id), "shot_type": "volley"}),
            ev(52, "goal", "Sofia Reyes", falcons, details={"shot_type": "penalty"}),
            ev(67, "shot", "Diego Santos", hawks),
            ev(74, "save", "Ethan Park", hawks),
            # CV-proposed DRAFTS awaiting human review (the review queue)
            ev(58, "shot", "Noah Williams", hawks, source=EventSource.cv, confidence=0.91),
            ev(63, "corner_kick", team=falcons, source=EventSource.cv, confidence=0.77),
            ev(81, "goal", "Maya Patel", falcons, source=EventSource.cv, confidence=0.52,
               details={"note": "possible offside - low confidence"}),
        ]
        db.add_all(events)
        db.flush()

        # cache the scoreline from confirmed goals (a projection)
        game.home_score = 2
        game.away_score = 1

        # --- a couple of shareable clips (parent use-case) ---
        goal_event = events[1]  # Maya's 11' goal
        clip = Clip(
            game_id=game.id, event_id=goal_event.id, video_asset_id=goalcam.id,
            start_offset_ms=11 * 60 * 1000 - et["goal"].clip_lead_ms,
            end_offset_ms=11 * 60 * 1000 + et["goal"].clip_trail_ms,
            status="ready", visibility=ClipVisibility.team,
            title="Maya Patel goal (11')",
            storage_uri="s3://airplai-demo/clips/maya-goal-11.mp4",
            thumbnail_uri="s3://airplai-demo/clips/maya-goal-11.jpg",
        )
        db.add(clip)
        db.flush()
        # the clip features both the scorer and the assister
        db.add_all([
            ClipSubject(clip_id=clip.id, player_id=players["Maya Patel"].id),
            ClipSubject(clip_id=clip.id, player_id=players["Sofia Reyes"].id),
        ])

        db.commit()

        print("Seed complete.")
        print(f"  League:  {league.name}")
        print(f"  Game id: {game.id}   ({falcons.name} 2 - 1 {hawks.name})")
        print(f"  Maya Patel id: {players['Maya Patel'].id}")
        print(f"  Events:  {len(events)} ({sum(1 for e in events if e.source==EventSource.cv)} CV drafts in review queue)")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
