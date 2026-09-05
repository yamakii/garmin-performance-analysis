"""FastAPI application factory for garmin-web."""

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from garmin_web.api.activities import router as activities_router
from garmin_web.api.activity_detail import router as activity_detail_router
from garmin_web.api.durability import router as durability_router
from garmin_web.api.goal import router as goal_router
from garmin_web.api.race import router as race_router
from garmin_web.api.recovery import router as recovery_router
from garmin_web.api.training_load import router as training_load_router
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
    app.include_router(race_router)
    app.include_router(training_load_router)
    app.include_router(durability_router)
    app.include_router(recovery_router)
    app.include_router(weekly_reviews_router)

    resolved_static_dir = Path(static_dir) if static_dir else _DEFAULT_STATIC_DIR
    _mount_spa(app, resolved_static_dir)
    return app


def _resolve_static_file(static_root: Path, full_path: str) -> Path | None:
    """Return the file under ``static_root`` named by ``full_path``, or ``None``.

    ``full_path`` is attacker-controlled (it is the request URL), so containment
    is established *before* any filesystem access: the joined path is normalised
    -- which collapses ``..`` segments and lets an absolute path override the
    root -- and only a result that still sits under ``static_root`` is stat-ed.

    Checking containment after the stat would leave an existence oracle for
    arbitrary filesystem paths even though the file contents never escape
    (CodeQL ``py/path-injection``).
    """
    if not full_path:
        return None

    root = str(static_root)
    candidate = os.path.normpath(os.path.join(root, full_path))
    if not candidate.startswith(root + os.sep):
        return None

    resolved = Path(candidate)
    return resolved if resolved.is_file() else None


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
        asset = _resolve_static_file(static_root, full_path)
        if asset is not None:
            return FileResponse(asset)
        return FileResponse(index_file)
