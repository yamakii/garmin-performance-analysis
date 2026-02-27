#!/usr/bin/env bash
# Pre-commit hook: Ban direct duckdb.connect() in production code.
# Use get_connection()/get_write_connection() from garmin_mcp.database.connection instead.
# Add '# noqa: duckdb-connect' to suppress for legitimate uses (benchmarks, etc.)

matches=$(grep -rn "duckdb\.connect(" --include="*.py" packages/garmin-mcp-server/src/ | grep -v "connection.py" | grep -v "noqa")

if [ -n "$matches" ]; then
    echo "ERROR: Direct duckdb.connect() found in production code:"
    echo "$matches"
    echo ""
    echo "Use get_connection()/get_write_connection() from garmin_mcp.database.connection"
    echo "Or add '# noqa: duckdb-connect' to suppress."
    exit 1
fi
