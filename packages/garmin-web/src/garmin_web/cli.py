"""CLI entrypoint for garmin-web (`uv run garmin-web`)."""

import argparse

import uvicorn

from garmin_web.app import create_app


def main() -> None:
    """Start the garmin-web server with uvicorn.

    Options: --host (default 127.0.0.1), --port (default 8765).
    """
    parser = argparse.ArgumentParser(
        prog="garmin-web",
        description="Serve the Garmin analysis web app (API + built frontend).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Bind port (default: 8765)",
    )
    args = parser.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
