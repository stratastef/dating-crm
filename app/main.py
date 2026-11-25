from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.audit import router as audit_router
from app.auth import CurrentUser, Db
from app.cards import router as cards_router
from app.db import database_url
from app.jobs import enqueue
from app.voice import router as voice_router


def create_app(url: str | None = None) -> FastAPI:
    engine = create_engine(url or database_url(), pool_pre_ping=True)
    app = FastAPI(title="Dating CRM")
    app.state.engine = engine

    @app.get("/health")
    def health() -> dict[str, str]:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            raise HTTPException(status_code=503, detail="database unreachable")
        return {"status": "ok"}

    @app.get("/me")
    def me(user: CurrentUser) -> dict[str, str]:
        return {"email": user.email}

    @app.post("/jobs/ping")
    def ping_job(user: CurrentUser, db: Db) -> dict[str, int]:
        return {"id": enqueue(db, user.id, "ping")}

    @app.get("/jobs/{job_id}")
    def job(job_id: int, user: CurrentUser, db: Db) -> dict:
        row = db.execute(
            text("SELECT id, kind, status, attempts FROM jobs WHERE id = :id AND user_id = :user_id"),
            {"id": job_id, "user_id": user.id},
        ).one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="job not found")
        return dict(row._mapping)

    app.include_router(audit_router)
    app.include_router(cards_router)
    app.include_router(voice_router)

    return app
