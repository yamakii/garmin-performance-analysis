#!/usr/bin/env bash
set -euo pipefail

OVERRIDE_FILE="/tmp/garmin-mcp-server-dir"
DEFAULT_DIR="packages/garmin-mcp-server"

if [[ -f "$OVERRIDE_FILE" ]]; then
    # TTL check: discard stale overrides (>24h)
    if [[ $(find "$OVERRIDE_FILE" -mmin +1440 -print 2>/dev/null) ]]; then
        echo "garmin-db: Override file is stale (>24h), removing" >&2
        rm -f "$OVERRIDE_FILE"
    else
        OVERRIDE_DIR=$(cat "$OVERRIDE_FILE")
        if [[ -d "$OVERRIDE_DIR" ]] && [[ -f "$OVERRIDE_DIR/pyproject.toml" ]]; then
            echo "garmin-db: Starting from override: $OVERRIDE_DIR" >&2
            exec uv run --directory "$OVERRIDE_DIR" garmin-mcp-server
        else
            echo "garmin-db: Invalid override '$OVERRIDE_DIR', falling back to default" >&2
            rm -f "$OVERRIDE_FILE"
        fi
    fi
fi

echo "garmin-db: Starting from default: $DEFAULT_DIR" >&2
exec uv run --directory "$DEFAULT_DIR" garmin-mcp-server
