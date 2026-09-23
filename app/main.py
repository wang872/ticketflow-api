from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import Base, get_engine, get_session_factory
from app.errors import AppError, app_error_handler
from app.routers import admin, auth, tickets
from app.seed import seed_data
from app.services.tickets import start_sla_checker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("ticketflow")


def _ensure_sqlite_dir() -> None:
    settings = get_settings()
    if settings.database_url.startswith("sqlite:///./"):
        rel_path = settings.database_url.removeprefix("sqlite:///./")
        Path(rel_path).parent.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    _ensure_sqlite_dir()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    if settings.seed_on_startup:
        db = get_session_factory()()
        try:
            seed_data(db)
        finally:
            db.close()
    stopper = None
    if settings.sla_checker_enabled:
        stopper = start_sla_checker()
        logger.info("Background SLA checker enabled")
    yield
    if stopper is not None:
        stopper.set()


app = FastAPI(
    title="TicketFlow API",
    description="Enterprise work-order / helpdesk backend with RBAC, FSM, SLA, and audit logs.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_exception_handler(AppError, app_error_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(tickets.router)
app.include_router(admin.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
