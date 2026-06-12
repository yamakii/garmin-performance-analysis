"""FastAPI application factory for garmin-web."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from garmin_web.api.activities import router as activities_router
from garmin_web.api.trends import router as trends_router

VITE_DEV_ORIGIN = "http://localhost:5173"


def create_app(db_path: str | Path | None = None) -> FastAPI:
    """Create the garmin-web FastAPI application.

    Args:
        db_path: Path to the DuckDB database file. If None, the path is
            resolved from GARMIN_DATA_DIR via garmin_mcp configuration.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(title="garmin-web", version="0.1.0")
    app.state.db_path = db_path
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[VITE_DEV_ORIGIN],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(activities_router)
    app.include_router(trends_router)
    return app
