#!/usr/bin/env bash
# Resolve which Claude Code version the sandbox image installs (#1346).
#
# Sourced by docker/run.sh and by scripts/tests/test-claude-version.sh. Keep the
# parsing side-effect free so it stays unit-testable on the host without docker
# (same arrangement as docker/lib/uv-venv.sh).
#
# Why: the Dockerfile installs the CLI in one layer,
#   RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}
# and run.sh passed the literal default `latest` on every build. The build-arg
# VALUE never changed, so docker reused the cached layer and the image kept
# whatever version that layer first resolved (2026-09-23: container 2.1.273 vs
# published 2.1.280). The in-container auto-updater is off by design
# (DISABLE_AUTOUPDATER=1 + non-root user, #545), so the rebuild is the only
# update path — and the default path silently did nothing. Resolving `latest` to
# a concrete version here turns the build-arg into a cache key that changes
# exactly when a new release exists: a rebuild updates, and a rebuild with no
# new release still hits the cache.

CLAUDE_CODE_PKG="@anthropic-ai/claude-code"
CLAUDE_CODE_REGISTRY="${CLAUDE_CODE_REGISTRY:-https://registry.npmjs.org}"

# claude_version_is_semver <string>
# True for a plain npm version ("2.1.280", "2.1.280-beta.1"). Guards against
# feeding registry error text or an empty answer into the build-arg.
claude_version_is_semver() {
  [[ "${1:-}" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-+][0-9A-Za-z.-]+)?$ ]]
}

# claude_version_parse <json>
# Prints the "version" field of an npm registry document, "" when absent.
# npm's own metadata keys are camel-cased ("_npmVersion", "_nodeVersion"), so an
# anchored `"version"` key match cannot pick them up.
claude_version_parse() {
  printf '%s' "${1:-}" \
    | grep -o '"version"[[:space:]]*:[[:space:]]*"[^"]*"' \
    | head -1 \
    | sed 's/.*"\([^"]*\)"[[:space:]]*$/\1/'
}

# claude_version_fetch_latest
# Prints the newest published version; returns 1 if it cannot be determined.
# npm first (it honours the host's registry / proxy / auth config), then curl.
claude_version_fetch_latest() {
  local v json
  if command -v npm >/dev/null 2>&1; then
    v="$(npm view "$CLAUDE_CODE_PKG" version 2>/dev/null | tr -d '\r' | tail -1)"
    if claude_version_is_semver "$v"; then printf '%s\n' "$v"; return 0; fi
  fi
  if command -v curl >/dev/null 2>&1; then
    json="$(curl -fsSL --max-time 10 "$CLAUDE_CODE_REGISTRY/$CLAUDE_CODE_PKG/latest" 2>/dev/null)" || json=""
    v="$(claude_version_parse "$json")"
    if claude_version_is_semver "$v"; then printf '%s\n' "$v"; return 0; fi
  fi
  return 1
}

# claude_version_resolve [requested]
# Prints the value to pass as the CLAUDE_CODE_VERSION build-arg. An explicit pin
# goes through untouched; "latest" (or empty) resolves to the newest published
# version. When the registry is unreachable it prints "latest" — the previous
# behaviour, which builds fine but may reuse the cached layer — and returns 1 so
# the caller can warn.
claude_version_resolve() {
  local requested="${1:-latest}" v
  if [ -n "$requested" ] && [ "$requested" != "latest" ]; then
    printf '%s\n' "$requested"
    return 0
  fi
  if v="$(claude_version_fetch_latest)"; then
    printf '%s\n' "$v"
    return 0
  fi
  printf 'latest\n'
  return 1
}
