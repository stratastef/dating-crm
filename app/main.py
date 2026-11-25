from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.db import database_url


def create_app(url: str | None = None) -> FastAPI:
    engine = create_engine(url or database_url(), pool_pre_ping=True)
    app = FastAPI(title="Dating CRM")

    @app.get("/health")
    def health() -> dict[str, str]:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            raise HTTPException(status_code=503, detail="database unreachable")
        return {"status": "ok"}

    return app
