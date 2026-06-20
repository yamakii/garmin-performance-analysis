#!/usr/bin/env bash
# Pre-commit: ban grep-able code smells captured from project memory.
# Add '# noqa: <rule>' on a line to suppress.
set -uo pipefail
status=0

SRC_DIRS="packages/garmin-mcp-server/src"
[ -d packages/garmin-web/src ] && SRC_DIRS="$SRC_DIRS packages/garmin-web/src"

# Rule 1: hardcoded user data paths — use get_db_path()/$GARMIN_DATA_DIR
hits=$(grep -rnE "/home/yamakii/(garmin_data|workspace/claude_workspace)" --include="*.py" $SRC_DIRS 2>/dev/null | grep -v "noqa") || true
if [ -n "$hits" ]; then
  echo "ERROR: hardcoded user data path found (use get_db_path() / \$GARMIN_DATA_DIR):"
  echo "$hits"
  echo ""
  status=1
fi

# Rule 2: float variance compared with == 0 — use peak-to-peak / relative tolerance
hits=$(grep -rnE "(np\.)?(std|var)\([^)]*\)[[:space:]]*==[[:space:]]*0" --include="*.py" $SRC_DIRS 2>/dev/null | grep -v "noqa") || true
if [ -n "$hits" ]; then
  echo "ERROR: float variance tested with '== 0' (catastrophic cancellation; use np.ptp / relative tolerance):"
  echo "$hits"
  echo ""
  status=1
fi

[ "$status" -ne 0 ] && echo "Add '# noqa' on the offending line to suppress if intentional."
exit $status
