#!/usr/bin/env bash
#
# Build and launch the Claude Code sandbox container for this project.
#
# Docker is the trust boundary. Inside the container you may run Claude Code with
# dangerouslyDisableSandbox: capabilities are dropped, the writable scope is the
# mounted repo + data/, and init-firewall.sh restricts egress to an allowlist.
#
# Usage:
#   docker/run.sh            # build (if needed) + open an interactive shell, then run `claude`
#   docker/run.sh claude     # build + launch claude directly
#   NO_BUILD=1 docker/run.sh # skip the build step (reuse the existing image)
set -euo pipefail

IMAGE="garmin-claude-sandbox"
CONTAINER="garmin-claude"
CONFIG_VOLUME="garmin-claude-home"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

command -v docker >/dev/null 2>&1 || { echo "ERROR: docker not found on PATH" >&2; exit 1; }

ENV_FILE="$REPO_ROOT/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "WARN: $ENV_FILE not found — garmin-db / github MCP will fail to authenticate." >&2
    ENV_FILE=""
fi

CRED_FILE="$HOME/.claude/.credentials.json"
if [ ! -f "$CRED_FILE" ]; then
    echo "WARN: $CRED_FILE not found — you will need to log in to Claude inside the container." >&2
fi

# ---- build ----
if [ "${NO_BUILD:-0}" != "1" ]; then
    echo "▶ Building $IMAGE (context: $SCRIPT_DIR) ..."
    docker build \
        --build-arg "USER_UID=$(id -u)" \
        --build-arg "USER_GID=$(id -g)" \
        -t "$IMAGE" \
        "$SCRIPT_DIR"
fi

# ---- mounts ----
mounts=(
    -v "$REPO_ROOT:/workspace"
    -v "$CONFIG_VOLUME:/home/claude/.claude"          # container-local Claude config/onboarding (named volume)
)
# Share ONLY the credentials file with the host (rw, for OAuth token refresh).
# The rest of ~/.claude stays in the named volume so the container never collides
# with a live host Claude session's sessions/history/jobs state.
if [ -f "$CRED_FILE" ]; then
    mounts+=( -v "$CRED_FILE:/home/claude/.claude/.credentials.json" )
fi

# Data/result dirs that live OUTSIDE the repo must be mounted explicitly at the
# same absolute path (the in-repo default data/ is already under /workspace).
if [ -n "$ENV_FILE" ]; then
    # shellcheck disable=SC1090
    set -a; . "$ENV_FILE" 2>/dev/null || true; set +a
    for d in "${GARMIN_DATA_DIR:-}" "${GARMIN_RESULT_DIR:-}"; do
        [ -n "$d" ] && [ -d "$d" ] || continue
        abs="$(cd "$d" && pwd)"
        case "$abs/" in
            "$REPO_ROOT"/*) : ;;                       # inside repo → already mounted
            *) mounts+=( -v "$abs:$abs" ) ;;
        esac
    done
fi

env_args=()
[ -n "$ENV_FILE" ] && env_args+=( --env-file "$ENV_FILE" )

# ---- run ----
echo "▶ Launching $CONTAINER ..."
exec docker run --rm -it \
    --name "$CONTAINER" \
    -w /workspace \
    "${mounts[@]}" \
    "${env_args[@]}" \
    --network bridge \
    --cap-drop ALL \
    --cap-add NET_ADMIN \
    --cap-add NET_RAW \
    --cap-add SETUID \
    --cap-add SETGID \
    --security-opt no-new-privileges \
    --pids-limit 512 \
    --memory 4g \
    --cpus 2 \
    "$IMAGE" "$@"
