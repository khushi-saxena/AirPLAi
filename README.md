# AirPLAi — Game Day Operations Engine

**Event Tagging API** — the data spine of the Game Day Operations Engine.

> **Thesis:** *Events are the single source of truth.* The scoreline, player
> stats, clips, dashboards, and highlight reels are all **projections** over
> events. Get this layer right and everything downstream is a query. That's why,
> of the five prototype options, I built this one: it's the piece every other
> feature depends on.

This repo is **Part 2** (the working prototype) of the trial project. The
architecture document (Part 1) covers the full ingestion → processing → storage
→ delivery → scaling design; this code implements the spine of it.

---

## What it does

- **Tag events** during/after a game (goals, shots, fouls, cards, saves…).
- **Human-in-the-loop CV workflow:** computer vision proposes events as
  low-confidence **drafts**; a human **confirms** or **rejects** them. Only
  confirmed events count toward official stats. (This is the near-term workflow
  the AirPLAi team described: human-in-the-loop, CV as first pass.)
- **Game summary** — a live box score computed *from* events, never stored as
  source data.
- **Player feeds & the parent use-case** — every clip featuring a given player,
  including ones where they weren't the primary actor.
- **Multi-sport by design** — sports and event types are *data*, not hardcoded
  enums. Adding basketball is a set of `INSERT`s, not a migration.

## Quick start (zero setup, SQLite)

```bash
pip install -r requirements.txt
python -m app.seed            # creates + seeds a realistic GBA soccer game
uvicorn app.main:app --reload
```

Open the interactive docs at **http://localhost:8000/docs**.

## Production-like run (Postgres via Docker)

```bash
docker compose up --build     # Postgres + API, auto-seeded
```

The app targets **Postgres in production** (UUID, JSONB, native enums) and falls
back to **SQLite** for a dependency-free local demo. `DATABASE_URL` switches
between them.

## Try the workflow

```bash
# pick the seeded game
GID=$(curl -s localhost:8000/games | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")

# box score — a projection over confirmed events
curl -s localhost:8000/games/$GID/summary | python3 -m json.tool

# the CV review queue (lowest-confidence drafts first)
curl -s localhost:8000/games/$GID/review-queue | python3 -m json.tool

# confirm a draft -> watch the score/stats update on the next summary call
EID=$(curl -s localhost:8000/games/$GID/review-queue | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")
curl -s -X POST localhost:8000/events/$EID/confirm -H 'content-type: application/json' -d '{"reviewed_by":"coach_dana"}'
```

## Key endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/games/{id}/events` | Tag an event (human = confirmed; CV = draft) |
| `GET`  | `/games/{id}/events` | List/filter events, keyset pagination |
| `GET`  | `/games/{id}/review-queue` | CV drafts awaiting human review |
| `POST` | `/events/{id}/confirm` | Confirm a draft (records reviewer + timestamp) |
| `POST` | `/events/{id}/reject` | Reject a draft |
| `GET`  | `/games/{id}/summary` | Box score + stats, projected from events |
| `GET`  | `/players/{id}/events` | A player's highlight feed |
| `GET`  | `/players/{id}/clips` | Shareable clips featuring a player |

## Tests

```bash
pytest -q
```

Covers human-tag confirmation, the full CV draft → review → confirm flow with
its audit trail and idempotency guard, the stats-as-projection invariant
(drafts excluded from the score), and event-type validation.

## Design decisions

These are the calls I made where the brief left them open:

1. **Events as the single source of truth.** Stats and the scoreline are
   recomputed from events, never authoritative on their own — a stats bug can
   never corrupt the truth.
2. **Three separate clocks.** Each event carries a *game clock* (`clock_ms`, for
   display), a *wall clock* (`occurred_at`, authoritative for ordering), and an
   implied *video offset* (`occurred_at − video_asset.recorded_start`, with a
   per-camera `sync_offset_ms` for drift). This is what makes multi-camera clip
   cutting work.
3. **CV-ready from day one.** `source` / `confidence` / `status` +
   `reviewed_by` / `reviewed_at` let human and CV events coexist with a review
   trail — matching the team's human-in-the-loop-now, full-CV-later roadmap.
4. **Multi-sport via data, not enums.** Justified by AirPLAi's own positioning
   ("all levels of all sports"): `sports` + `event_types` reference tables plus
   a `jsonb` details column. Soccer is the seeded implementation.
5. **Indexes map 1:1 to query patterns.** `(game_id, occurred_at, id)` for the
   timeline + keyset pagination, `(primary_player_id, event_type_id)` for player
   highlights, `(game_id, event_type_id)` for the box score.

## What I'd do with more time

- A thin real-time read path (WebSocket/SSE) for the live stats the team called
  valuable — events fan out to subscribers as they're confirmed.
- Alembic migrations + the Postgres-only GIN index on `events.details`.
- Auth/tenancy and a clip-rendering worker behind a queue.

## Layout

```
app/
  models.py      # the schema (data spine)
  schemas.py     # request/response shapes
  services.py    # the projection logic (stats FROM events)
  routers/       # events (tagging + review), games, players
  seed.py        # realistic GBA soccer game incl. CV drafts
tests/
```
