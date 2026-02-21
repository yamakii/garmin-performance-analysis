#!/usr/bin/env bash
set -euo pipefail

OVERRIDE_FILE="/tmp/garmin-mcp-server-dir"
DEFAULT_DIR="packages/garmin-mcp-server"

if [[ -f "$OVERRIDE_FILE" ]]; then
    OVERRIDE_DIR=$(cat "$OVERRIDE_FILE")
    if [[ -d "$OVERRIDE_DIR" ]]; then
        exec uv run --directory "$OVERRIDE_DIR" garmin-mcp-server
    else
        echo "Warning: Override dir '$OVERRIDE_DIR' not found, using default" >&2
        rm -f "$OVERRIDE_FILE"
    fi
fi

exec uv run --directory "$DEFAULT_DIR" garmin-mcp-server
