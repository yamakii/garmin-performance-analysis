"""Half-generate the API endpoint table in ``docs/garmin-web.md`` from routes.

The endpoint table (``| Endpoint | Description |``) is rendered from the live
FastAPI routers and inserted between sentinel markers:

    <!-- BEGIN GENERATED: web-api-table -->
    | Endpoint | Description |
    | ... |
    <!-- END GENERATED: web-api-table -->

Everything outside the markers — prose, architecture notes — is hand-written
and preserved verbatim. Building the app via ``create_app()`` and walking
``app.routes`` means the table never depends on the running server, yet always
reflects the routers that define the API. The description for each endpoint is
the first line of the route handler's docstring.

Usage::

    # Refresh the generated table in place
    uv run --directory packages/garmin-web python -m garmin_web.scripts.generate_api_doc

    # Verify the committed doc is in sync (used by the drift test / CI)
    uv run --directory packages/garmin-web python -m garmin_web.scripts.generate_api_doc --check

An integration test (``tests/test_generate_api_doc.py``) asserts the committed
doc equals the generated output, so adding/removing a route without
regenerating fails CI.
"""

from __future__ import annotations

import argparse
import inspect
import sys
from collections.abc import Iterable
from pathlib import Path

from fastapi import FastAPI
from fastapi.routing import APIRoute

from garmin_web.app import create_app

# scripts -> garmin_web -> src -> garmin-web -> packages -> repo root
REPO_ROOT = Path(__file__).resolve().parents[5]
DOC_PATH = REPO_ROOT / "docs" / "garmin-web.md"

MARKER_BEGIN = "<!-- BEGIN GENERATED: web-api-table -->"
MARKER_END = "<!-- END GENERATED: web-api-table -->"


def _summary(route: APIRoute) -> str:
    """Return the first non-empty docstring line of the route handler.

    Falls back to the route's ``summary`` (FastAPI defaults it to the function
    name) when no docstring is present.
    """
    doc = inspect.getdoc(route.endpoint)
    if doc:
        for line in doc.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped
    return str(route.summary or route.name)


def _iter_api_routes(app: FastAPI) -> list[APIRoute]:
    """Return every ``APIRoute`` reachable from the app, recursing into routers.

    ``app.include_router`` wraps each router (FastAPI >= 0.138 yields
    ``_IncludedRouter`` objects exposing ``original_router``). Walking
    ``original_router``/``routes`` recursively keeps this resilient to that
    nesting without hard-coding the wrapper type.
    """
    found: list[APIRoute] = []
    seen: set[int] = set()

    def walk(routes: Iterable[object] | None) -> None:
        for route in routes or ():
            if id(route) in seen:
                continue
            seen.add(id(route))
            if isinstance(route, APIRoute):
                found.append(route)
            original = getattr(route, "original_router", None)
            if original is not None and original is not route:
                walk(getattr(original, "routes", None))
            nested = getattr(route, "routes", None)
            if nested is not None:
                walk(nested)

    walk(app.routes)
    return found


def collect_endpoints(app: FastAPI) -> list[tuple[str, str]]:
    """Collect ``(path, description)`` for read-only ``GET`` API routes.

    Only ``APIRoute`` entries under ``/api`` whose methods are exactly
    ``{"GET"}`` and that appear in the OpenAPI schema (``include_in_schema``)
    are returned. The SPA catch-all and HEAD/OPTIONS variants are excluded.
    The result is sorted by path.
    """
    endpoints: list[tuple[str, str]] = []
    for route in _iter_api_routes(app):
        if not route.include_in_schema:
            continue
        if not route.path.startswith("/api"):
            continue
        methods = route.methods or set()
        if methods != {"GET"}:
            continue
        endpoints.append((route.path, _summary(route)))
    return sorted(endpoints, key=lambda item: item[0])


def render_api_table(endpoints: list[tuple[str, str]]) -> str:
    """Render the generated ``| Endpoint | Description |`` block.

    The output is wrapped in the BEGIN/END sentinel markers. Endpoint paths are
    rendered as inline code.
    """
    lines = [
        MARKER_BEGIN,
        "| Endpoint | Description |",
        "|----------|-------------|",
    ]
    for path, description in endpoints:
        lines.append(f"| `{path}` | {description} |")
    lines.append(MARKER_END)
    return "\n".join(lines)


def apply_generated_block(doc_text: str, block: str) -> str:
    """Replace the marked region in ``doc_text`` with ``block``.

    The text between the BEGIN and END markers (inclusive) is swapped for
    ``block``; prose outside the markers is preserved verbatim.

    Raises:
        ValueError: if the begin/end markers are not found in the doc.
    """
    start_idx = doc_text.find(MARKER_BEGIN)
    if start_idx == -1:
        raise ValueError(f"missing BEGIN marker: {MARKER_BEGIN}")
    end_idx = doc_text.find(MARKER_END, start_idx)
    if end_idx == -1:
        raise ValueError(f"missing END marker: {MARKER_END}")
    end_idx += len(MARKER_END)
    return doc_text[:start_idx] + block + doc_text[end_idx:]


def render_doc(current_doc: str) -> str:
    """Render the full doc: swap the marked API table from the live routers.

    The returned text is what the committed doc must equal.
    """
    app = create_app()
    block = render_api_table(collect_endpoints(app))
    return apply_generated_block(current_doc, block)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed doc differs from the generated output.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DOC_PATH,
        help=f"Doc path (default: {DOC_PATH})",
    )
    args = parser.parse_args(argv)

    if not args.output.exists():
        print(f"MISSING: {args.output} does not exist.")
        return 1
    current = args.output.read_text(encoding="utf-8")
    content = render_doc(current)

    if args.check:
        if current != content:
            print(
                f"OUT OF SYNC: {args.output} differs from the FastAPI routes. "
                "Regenerate with: python -m garmin_web.scripts.generate_api_doc"
            )
            return 1
        print(f"OK: {args.output} is in sync with the FastAPI routes.")
        return 0

    args.output.write_text(content, encoding="utf-8")
    print(f"Wrote {args.output}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
