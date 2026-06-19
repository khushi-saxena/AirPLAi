# Study Guide — Game Day Operations Engine

A plain-English guide to what you built, why, and how to explain it. Read this
once before the presentation and you'll be able to defend every choice.

---

## 1. The 30-second pitch (say this first)

> "AirPLAi turns raw game footage into searchable intelligence. I built the
> **event tagging API** — the data spine of that system. My core idea is that
> **events are the single source of truth**: I don't store the score or the
> stats directly, I store every moment of the game as an event and *calculate*
> everything else from them. The score, player stats, clips, and dashboards are
> all just different questions asked of the same events. I built this piece
> because every other feature depends on it."

If you only memorize one thing, memorize that paragraph.

---

## 2. The big idea: events are the single source of truth

**The bank analogy.** Your bank doesn't store your balance as the truth. It
stores every *transaction* — deposits and withdrawals — and your balance is just
those added up. If the balance ever looks wrong, they recompute it from the
transactions.

In our system:
- **Events** = the transactions (a goal, a foul, a shot, a save).
- **Score and stats** = the balance (calculated, never stored as the truth).

**Why this is the right design:**
- If you stored the score directly and a bug changed it, the truth is corrupted.
  With events, you can always recompute and be correct.
- Clips, dashboards, the parent's "highlights of my kid," the box score — they're
  all just *different queries over the same events*. One source, many views.
- This is exactly why building the tagging API was the smart prototype choice:
  it's the foundation everything else stands on.

In the code, this idea lives in `app/services.py` — that file *computes* the
score and stats from events. Nothing reads a stored score.

---

## 3. How the system works: the waiter analogy

Picture a restaurant:
- The **kitchen / pantry** = the database (where data is stored).
- The **waiter** = the **API**. You never walk into the kitchen; you ask the
  waiter, and it fetches things for you.
- **FastAPI** = the tool (a Python framework) we used to build the waiter.

An **endpoint** is one specific thing the waiter knows how to do, like
"give me the box score for game 5" or "create a goal event." Each endpoint has:
- a **method**: `GET` (fetch something) or `POST` (create/do something), and
- a **path**: the address, e.g. `/games/{id}/summary`.

So `GET /games/5/summary` means "waiter, fetch me the summary for game 5."

---

## 4. The human + AI (CV) workflow

Today, a person tags the moments. Soon, **computer vision (CV)** — AI that
watches the video — will guess the moments automatically. But AI makes mistakes,
so:

- CV-created events arrive as **drafts** with a **confidence** score (how sure
  the AI is, 0 to 1).
- A human looks at the drafts in a **review queue** and clicks **confirm** or
  **reject**.
- Only **confirmed** events count toward the official score and stats.

**The intern analogy:** the AI is an intern who drafts notes; a senior person
checks and signs off before they go in the official record.

We recorded *who* confirmed each event and *when* (`reviewed_by`, `reviewed_at`)
so there's an audit trail. This matches exactly what Arman said: human-in-the-
loop now, full CV later.

In the code: `POST /events/{id}/confirm` and `/reject` are the sign-off buttons.
The review queue is `GET /games/{id}/review-queue`.

---

## 5. Multi-sport without rewriting anything

AirPLAi is "the AI video intelligence layer for all levels of **all sports**."
So the design supports many sports — but cleverly:

- Sports and event types are stored as **data in tables**, not hardcoded in the
  program. Adding basketball is just inserting new rows (a new sport, new event
  types like "3-pointer"). No code change, no database migration.
- Each event has a flexible `details` field (called **JSONB** in Postgres) that
  holds sport-specific extras — e.g. for a goal, the assisting player and whether
  it was a header.

**One-liner to say:** "Adding a sport is data, not a migration."

---

## 6. The three clocks (your senior-engineer detail)

This is the subtle point that makes you look experienced. Every event tracks
*three different notions of time*:

1. **Game clock** (`clock_ms`) — what a human sees: "the 63rd minute."
2. **Wall clock** (`occurred_at`) — the real-world timestamp. This is the
   authoritative one for ordering events.
3. **Video offset** — *where in the footage* the moment is. We compute it as
   `occurred_at − video_asset.recorded_start`, with a small per-camera
   correction (`sync_offset_ms`) because cameras start at slightly different
   times.

**Why it matters:** to cut a clip of a goal from two camera angles, you need to
know exactly where the goal is in *each* video file. Keeping these three clocks
separate is what makes multi-camera clip generation work. Most people conflate
them, and that's why the manual workflow breaks today.

---

## 7. What each file does

| File | In plain English |
|---|---|
| `app/models.py` | Defines the database tables — the shape of a player, an event, a game, a clip. This is the schema. |
| `app/routers/events.py` | The tagging API: create events, list them, the review queue, confirm/reject. The heart of the project. |
| `app/routers/games.py` | The game summary (box score) endpoint. |
| `app/routers/players.py` | A player's highlight feed, and the "clips of my kid" query for parents. |
| `app/services.py` | The math that calculates score + stats *from* events (the projection logic). |
| `app/schemas.py` | The "order format" — what you send the API and what shape it sends back. |
| `app/seed.py` | Fills the database with a realistic sample soccer game, including CV drafts. |
| `app/main.py` | Starts the app and connects all the endpoints. |
| `tests/` | Automated checks proving the key behaviors work. |
| `Dockerfile`, `docker-compose.yml`, `render.yaml` | Instructions to run it with Postgres and put it online. |

---

## 8. What happens, step by step, when you tag a goal

Trace this out loud and you'll sound fluent:

1. The app sends `POST /games/{id}/events` with the details (goal, which player,
   what time).
2. The events router checks the game exists and that "goal" is a valid event
   type for that sport.
3. Because a human sent it, it's saved with status **confirmed**. (If the AI had
   sent it, it'd be saved as a **draft** instead.)
4. It's written to the `events` table in the database.
5. Later, someone calls `GET /games/{id}/summary`. The service layer reads all
   confirmed events, counts the goals per team to get the score, tallies each
   player's stats, and returns it. The score was never stored — it was computed
   right then from the events.

---

## 9. Why you built THIS piece (your defense)

If they ask *"Why the tagging API and not the dashboard or the clip service?"*:

> "Because every other feature is a *view* over events. The dashboard reads
> events live. Clips are events with a start and end time. Stats are events
> added up. Parent highlights are events filtered by player. If the event model
> is right, the rest is a query. If it's wrong, you rebuild the whole product.
> So it's the highest-leverage thing to get right, and it's the foundation the
> other four options all depend on."

---

## 10. Likely questions and how to answer

**"Why SQLite and Postgres both?"**
> "It runs on SQLite with zero setup so anyone can clone and try it instantly,
> but it targets Postgres in production — same SQLAlchemy models, just a
> different database URL. Postgres gives me real JSONB, native enums, and
> concurrency for scale."

**"How would you handle live stats?"** (Arman said these are valuable)
> "Because stats are a projection over events, live stats just means projecting
> incrementally as events are confirmed, and pushing updates to clients over a
> WebSocket. The data model doesn't change at all — it's an extra read path. I've
> built WebSocket streaming before, so that's a natural next step."

**"How does this scale to 10,000 games?"**
> "The API is stateless, so I scale it horizontally behind a load balancer.
> Postgres scales with read replicas first, then partitioning events by game and
> time. Video lives in object storage, which scales on its own, served through a
> CDN. The dominant cost is storage, so the big lever is tiering old footage to
> cold storage." (The architecture doc has the numbers.)

**"What about bad CV data?"**
> "CV events come in as drafts with a confidence score and never count until a
> human confirms them. I sort the review queue by lowest confidence first so
> humans review the riskiest calls. Every confirm/reject is logged with who and
> when."

**"What would you do with more time?"**
> "A real-time WebSocket path for live stats, Alembic migrations plus the
> Postgres GIN index on the details field, authentication and multi-tenancy, and
> a background worker that actually renders the video clips."

**"What's the weakest part?"**
> "The clip generation is modeled but not rendering real video — I stored clip
> definitions (which camera, start, end) but didn't wire up the actual ffmpeg
> cutting, because I chose to spend my time making the data spine excellent. I'd
> do that next."
(Honesty about tradeoffs scores points — they explicitly value it.)

---

## 11. Glossary (so no word trips you up)

- **API** — the "waiter"; the layer apps talk to instead of touching the database.
- **Endpoint** — one specific thing the API can do (`GET /games/5/summary`).
- **FastAPI** — the Python framework used to build the API.
- **Database** — organized storage, made of tables.
- **Schema** — the definition of those tables (what columns exist).
- **ORM (SQLAlchemy)** — lets you work with database rows as Python objects
  instead of writing raw SQL. `models.py` uses it.
- **Migration** — a versioned change to the database schema.
- **Projection** — a value *computed* from source data (our score/stats from events).
- **Keyset pagination** — fetching results in pages efficiently by remembering
  the last item instead of counting from the start (fast even with millions of rows).
- **CV (computer vision)** — AI that analyzes video.
- **JSONB** — a Postgres column type that stores flexible JSON data (our
  sport-specific `details`).
- **Source of truth** — the one place the real data lives; everything else is derived.
