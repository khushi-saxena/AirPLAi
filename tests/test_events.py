"""Tests for the Event Tagging API and the projection logic."""


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_create_human_event_is_confirmed(client):
    g = client.ctx["game_id"]
    r = client.post(f"/games/{g}/events", json={
        "event_type_code": "goal",
        "occurred_at": "2025-04-12T10:11:00Z",
        "primary_player_id": client.ctx["player_id"],
        "team_id": client.ctx["team_id"],
        "source": "human",
    })
    assert r.status_code == 201
    body = r.json()
    # human tags are authoritative immediately
    assert body["status"] == "confirmed"
    assert body["source"] == "human"


def test_cv_event_enters_review_queue_then_confirms(client):
    g = client.ctx["game_id"]
    # CV proposes a goal as a low-confidence DRAFT
    r = client.post(f"/games/{g}/events", json={
        "event_type_code": "goal",
        "occurred_at": "2025-04-12T10:38:00Z",
        "primary_player_id": client.ctx["player_id"],
        "team_id": client.ctx["team_id"],
        "source": "cv",
        "confidence": 0.62,
    })
    assert r.status_code == 201
    event_id = r.json()["id"]
    assert r.json()["status"] == "draft"  # not yet counted

    # it shows up in the review queue
    queue = client.get(f"/games/{g}/review-queue").json()
    assert any(e["id"] == event_id for e in queue)

    # a human confirms it -> status flips and audit trail is recorded
    c = client.post(f"/events/{event_id}/confirm", json={"reviewed_by": "coach_dana"})
    assert c.status_code == 200
    assert c.json()["status"] == "confirmed"
    assert c.json()["reviewed_by"] == "coach_dana"
    assert c.json()["reviewed_at"] is not None

    # confirming again is rejected (idempotency guard)
    again = client.post(f"/events/{event_id}/confirm", json={"reviewed_by": "x"})
    assert again.status_code == 409


def test_summary_is_a_projection_of_confirmed_events(client):
    g = client.ctx["game_id"]
    # one confirmed goal for the home team
    client.post(f"/games/{g}/events", json={
        "event_type_code": "goal",
        "occurred_at": "2025-04-12T10:11:00Z",
        "primary_player_id": client.ctx["player_id"],
        "team_id": client.ctx["team_id"],
        "source": "human",
    })
    # one CV DRAFT goal — must NOT count until confirmed
    client.post(f"/games/{g}/events", json={
        "event_type_code": "goal",
        "occurred_at": "2025-04-12T10:20:00Z",
        "team_id": client.ctx["team_id"],
        "source": "cv",
        "confidence": 0.4,
    })

    s = client.get(f"/games/{g}/summary").json()
    assert s["home_score"] == 1          # draft excluded from the score
    assert s["pending_review"] == 1      # but visible as pending
    assert s["player_stats"][0]["stats"]["goals"] == 1


def test_unknown_event_type_rejected(client):
    g = client.ctx["game_id"]
    r = client.post(f"/games/{g}/events", json={
        "event_type_code": "touchdown",   # not a soccer event
        "occurred_at": "2025-04-12T10:11:00Z",
        "source": "human",
    })
    assert r.status_code == 422
