"""FastAPI application factory for garmin-web."""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from garmin_web.api.activities import router as activities_router
from garmin_web.api.activity_detail import router as activity_detail_router
from garmin_web.api.goal import router as goal_router
from garmin_web.api.trends import router as trends_router
from garmin_web.api.weekly_reviews import router as weekly_reviews_router

logger = logging.getLogger(__name__)

VITE_DEV_ORIGIN = "http://localhost:5173"

# packages/garmin-web/src/garmin_web/app.py -> packages/garmin-web/frontend/dist
_DEFAULT_STATIC_DIR = (
    Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
)


def create_app(
    db_path: str | Path | None = None,
    static_dir: str | Path | None = None,
) -> FastAPI:
    """Create the garmin-web FastAPI application.

    Args:
        db_path: Path to the DuckDB database file. If None, the path is
            resolved from GARMIN_DATA_DIR via garmin_mcp configuration.
        static_dir: Directory containing the built frontend (index.html +
            assets). If None, defaults to the package-relative
            `frontend/dist`. If the directory or its index.html is missing,
            a warning is logged and the API still works without the SPA.

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
    app.include_router(activity_detail_router)
    app.include_router(trends_router)
    app.include_router(goal_router)
    app.include_router(weekly_reviews_router)

    resolved_static_dir = Path(static_dir) if static_dir else _DEFAULT_STATIC_DIR
    _mount_spa(app, resolved_static_dir)
    return app


def _mount_spa(app: FastAPI, static_dir: Path) -> None:
    """Serve the built SPA with an index.html fallback for client routes.

    Registered after the API routers, so `/api/*` routes always win.
    When the build output is missing the SPA is simply not served.
    """
    index_file = static_dir / "index.html"
    if not index_file.is_file():
        logger.warning(
            "Frontend build not found at %s — serving API only. "
            "Run `npm run build` in packages/garmin-web/frontend.",
            static_dir,
        )
        return

    static_root = static_dir.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str) -> FileResponse:
        # Never shadow the API: unknown /api paths must stay 404, not HTML.
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        if full_path:
            candidate = (static_root / full_path).resolve()
            if candidate.is_file() and candidate.is_relative_to(static_root):
                return FileResponse(candidate)
        return FileResponse(index_file)
