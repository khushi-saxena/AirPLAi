from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.database import Base, engine
from app.routers import events, games, players


@asynccontextmanager
async def lifespan(app: FastAPI):
    # For the demo we create tables on startup. Production uses Alembic
    # migrations (see alembic/ and README) so schema changes are versioned.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="AirPLAi — Game Day Operations Engine",
    description="Event Tagging API. Events are the single source of truth; "
    "stats, clips and summaries are projections over them.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(events.router)
app.include_router(games.router)
app.include_router(players.router)


@app.get("/", include_in_schema=False)
def root():
    # the shared demo link lands on the interactive docs
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}