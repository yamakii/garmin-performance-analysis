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
    echo "INFO: $ENV_FILE not found — relying on host OS env vars for credentials." >&2
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

# Load .env (if present) so its GARMIN_* values feed the resolution below.
# Inherited host OS env vars stay set unless .env overrides them.
if [ -n "$ENV_FILE" ]; then
    # shellcheck disable=SC1090
    set -a; . "$ENV_FILE" 2>/dev/null || true; set +a
fi

env_args=()
[ -n "$ENV_FILE" ] && env_args+=( --env-file "$ENV_FILE" )

# Map a host dir to its container path. Inside-repo dirs are already bind-mounted
# at /workspace; outside-repo dirs get mounted at the same absolute path. Result
# in CONTAINER_PATH (no $(...) — mounts+= must mutate the parent shell's array).
CONTAINER_PATH=""
resolve_dir() {
    local abs rel
    abs="$(cd "$1" && pwd)"
    case "$abs/" in
        "$REPO_ROOT"/*)
            rel="${abs#"$REPO_ROOT"}"                  # "" or "/sub/dir"
            CONTAINER_PATH="/workspace${rel}"
            ;;
        *)
            mounts+=( -v "$abs:$abs" )
            CONTAINER_PATH="$abs"
            ;;
    esac
}

# Data/result dirs: mount (if outside the repo) and forward the env var pointing
# at the CONTAINER-side path so the MCP server resolves it to the mounted dir.
if [ -n "${GARMIN_DATA_DIR:-}" ] && [ -d "$GARMIN_DATA_DIR" ]; then
    resolve_dir "$GARMIN_DATA_DIR";   env_args+=( -e "GARMIN_DATA_DIR=$CONTAINER_PATH" )
fi
if [ -n "${GARMIN_RESULT_DIR:-}" ] && [ -d "$GARMIN_RESULT_DIR" ]; then
    resolve_dir "$GARMIN_RESULT_DIR"; env_args+=( -e "GARMIN_RESULT_DIR=$CONTAINER_PATH" )
fi

# Garth token cache: mount it (same abs path) + point GARMINTOKENS at it so the
# container reuses OAuth tokens instead of a fresh credential login each run.
tokendir="${GARMINTOKENS:-$HOME/.garth}"
mkdir -p "$tokendir" 2>/dev/null || true
if [ -d "$tokendir" ]; then
    tok_abs="$(cd "$tokendir" && pwd)"
    mounts+=( -v "$tok_abs:$tok_abs" )
    env_args+=( -e "GARMINTOKENS=$tok_abs" )
fi

# GitHub token: derive from the host gh CLI if not already exported.
if [ -z "${GITHUB_TOKEN:-}" ] && command -v gh >/dev/null 2>&1; then
    GITHUB_TOKEN="$(gh auth token 2>/dev/null || true)"; export GITHUB_TOKEN
fi

# Plain (non-path) credential passthrough. A value-less `-e VAR` pulls VAR from
# this script's env (OS env, possibly augmented by .env) and overrides any
# same-named entry from --env-file. Keep creds in your shell instead of .env.
# CLAUDE_CODE_OAUTH_TOKEN (from `claude setup-token`) / ANTHROPIC_API_KEY /
# ANTHROPIC_AUTH_TOKEN authenticate Claude Code itself without an interactive
# login — the single-file ~/.claude/.credentials.json bind mount can't persist
# OAuth token refresh, so without one of these the container re-prompts to log in.
for v in GARMIN_EMAIL GARMIN_PASSWORD GITHUB_TOKEN \
         CLAUDE_CODE_OAUTH_TOKEN ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN; do
    [ -n "${!v:-}" ] && env_args+=( -e "$v" )
done
[ -n "${GITHUB_TOKEN:-}" ] || echo "WARN: GITHUB_TOKEN unset — github MCP won't authenticate." >&2

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
