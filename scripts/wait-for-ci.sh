#!/usr/bin/env bash
# Block until a PR's required check (default: ci-guard) completes, then print
# one line of JSON and exit by conclusion. Replaces the `sleep N` →
# `pull_request_read(get_check_runs)` polling loop that used to cost 3-6 LLM
# round-trips per PR (dev-reference.md §8: loops of the same tool become one
# script call).
#
# READ-ONLY. Uses the GitHub REST API (pulls → head sha → check-runs) with
# GITHUB_TOKEN. It never writes to GitHub; merging stays with
# mcp__github__merge_pull_request (github-mcp-only.md documents this exception).
#
# Usage: scripts/wait-for-ci.sh <pr-number> [--timeout SEC] [--interval SEC]
#                               [--check NAME] [--repo owner/name]
#   --timeout   max seconds to wait (default 900)
#   --interval  seconds between polls (default 30)
#   --check     check-run name to wait for (default ci-guard)
#   --repo      owner/name (default: parsed from `git remote get-url origin`)
#
# stdout (always one line of JSON on a decided outcome):
#   {"pr":N,"sha":"...","check":"ci-guard","status":"completed",
#    "conclusion":"success","elapsed_s":N,"runs":[{"name","status","conclusion"}]}
#
# Exit codes:
#   0  check completed with conclusion=success
#   1  check completed with any other conclusion (failure, cancelled, ...)
#   2  timed out before the check completed
#   3  environment / API error (no GITHUB_TOKEN, bad args, curl or JSON error)
set -uo pipefail

API="${GITHUB_API_URL:-https://api.github.com}"
TIMEOUT=900
INTERVAL=30
CHECK="ci-guard"
REPO=""
PR=""

while [ $# -gt 0 ]; do
  case "$1" in
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --check) CHECK="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    -*) echo "wait-for-ci: unknown option $1" >&2; exit 3 ;;
    *) if [ -z "$PR" ]; then PR="$1"; shift; else echo "wait-for-ci: unexpected arg $1" >&2; exit 3; fi ;;
  esac
done

if ! [[ "$PR" =~ ^[0-9]+$ ]]; then
  echo "wait-for-ci: PR number required (got '${PR}')" >&2
  exit 3
fi
if [ -z "${GITHUB_TOKEN:-}" ]; then
  echo "wait-for-ci: GITHUB_TOKEN is not set (read-only token is enough)" >&2
  exit 3
fi
if [ -z "$REPO" ]; then
  url="$(git remote get-url origin 2>/dev/null || true)"
  REPO="$(printf '%s' "$url" | sed -E 's#^(https://github.com/|git@github.com:)##; s#\.git$##')"
  if ! [[ "$REPO" =~ ^[^/]+/[^/]+$ ]]; then
    echo "wait-for-ci: cannot resolve owner/name from origin '$url'; pass --repo" >&2
    exit 3
  fi
fi

api_get() {
  curl -sS --max-time 30 \
    -H "Authorization: Bearer $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "$API/repos/$REPO/$1"
}

head_sha() {
  api_get "pulls/$PR" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(1)
sha = (d.get("head") or {}).get("sha")
if not sha:
    sys.stderr.write("wait-for-ci: " + str(d.get("message") or "no head.sha in PR response") + "\n")
    sys.exit(1)
print(sha)
'
}

# Prints: "<status>\t<conclusion>\t<runs-json>" for CHECK on SHA.
# status is "absent" when the check-run has not been registered yet.
check_state() {
  api_get "commits/$1/check-runs?per_page=100" | CHECK="$CHECK" python3 -c '
import json, os, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(1)
runs = d.get("check_runs")
if runs is None:
    sys.stderr.write("wait-for-ci: " + str(d.get("message") or "no check_runs in response") + "\n")
    sys.exit(1)
slim = [{"name": r.get("name"), "status": r.get("status"), "conclusion": r.get("conclusion")} for r in runs]
target = [r for r in slim if r["name"] == os.environ["CHECK"]]
if not target:
    print("absent\t\t" + json.dumps(slim, ensure_ascii=False))
else:
    t = target[0]
    print((t["status"] or "") + "\t" + (t["conclusion"] or "") + "\t" + json.dumps(slim, ensure_ascii=False))
'
}

emit() {  # emit <sha> <status> <conclusion> <runs-json> <elapsed>
  printf '{"pr":%s,"sha":"%s","check":"%s","status":"%s","conclusion":"%s","elapsed_s":%s,"runs":%s}\n' \
    "$PR" "$1" "$CHECK" "$2" "$3" "$5" "$4"
}

start=$(date +%s)
last_status="absent"; last_conclusion=""; last_runs="[]"; sha=""
while :; do
  sha="$(head_sha)" || exit 3
  state="$(check_state "$sha")" || exit 3
  last_status="${state%%$'\t'*}"
  rest="${state#*$'\t'}"
  last_conclusion="${rest%%$'\t'*}"
  last_runs="${rest#*$'\t'}"
  elapsed=$(( $(date +%s) - start ))

  if [ "$last_status" = "completed" ]; then
    emit "$sha" "completed" "$last_conclusion" "$last_runs" "$elapsed"
    [ "$last_conclusion" = "success" ] && exit 0
    exit 1
  fi
  if [ "$elapsed" -ge "$TIMEOUT" ]; then
    emit "$sha" "${last_status:-absent}" "timeout" "$last_runs" "$elapsed"
    exit 2
  fi
  sleep "$INTERVAL"
done
