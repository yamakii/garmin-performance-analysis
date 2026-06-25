# Claude Code Docker sandbox

Run Claude Code on this project inside a Docker container so that
`dangerouslyDisableSandbox` (letting the agent run arbitrary bash) is acceptable:
**Docker is the trust boundary**, and an **egress allowlist firewall** prevents
mounted secrets from being exfiltrated even if a dependency or a prompt-injection
compromises the container.

This is a self-contained `docker run` setup (no devcontainer / VS Code required),
adapted for this project's full toolchain (Python 3.12 + uv + Node 22 + the three
MCP servers). The firewall is based on the official
[`anthropics/claude-code` devcontainer](https://github.com/anthropics/claude-code/tree/main/.devcontainer),
extended with the hosts this project needs.

## Threat model — what this does and does not protect

This container is where you deliberately loosen the leash. Two compromise vectors
are assumed realistic:

- **Supply chain** — `uv sync` (PyPI), `npm`, `uvx serena` (unpinned git), apt:
  any dependency can run code at install/import time as the `claude` user and read
  whatever is mounted.
- **Prompt injection** — agents read web pages, issues, PRs and file contents; a
  malicious payload may try to make the agent run exfiltration bash.

| Layer | Protects against | Does **not** protect against |
|-------|------------------|------------------------------|
| `--cap-drop ALL`, `--security-opt no-new-privileges`, non-root `claude`, `--pids-limit`/`--memory`/`--cpus` | privilege escalation, host access, fork bombs, resource abuse | a process reading a mounted secret and `curl`-ing it out |
| **egress allowlist** (`init-firewall.sh`) | sending secrets / data to an arbitrary host | exfiltration to an **allowlisted** host (e.g. a malicious GitHub repo) |
| bind-mount scope (`/workspace` only) | touching files outside the repo + `data/` | corrupting/altering the mounted repo + `data/` (rw) |

> Capabilities: `--cap-drop ALL` removes every Linux capability, then only four
> are added back — `NET_ADMIN` + `NET_RAW` (so the entrypoint can install the
> firewall) and `SETUID` + `SETGID` (so it can drop root → `claude`). The
> interactive `claude` session itself then runs with no effective capabilities.

The blast radius if the container is fully compromised is therefore: the mounted
repo + `data/`, plus any secret you chose to mount in. See the project decision
log for why Garmin + GitHub creds are accepted inside the container given the
egress allowlist is in place.

## What is mounted

| Host | Container | Mode | Why |
|------|-----------|------|-----|
| repo root | `/workspace` | rw | live edits + `data/` DuckDB |
| `~/.claude/.credentials.json` | same | rw | reuse the subscription OAuth login (token refresh writes back) |
| named volume `garmin-claude-home` | `/home/claude/.claude` | rw | container-local Claude config/onboarding, **isolated from the live host session** |
| `.env` (via `--env-file`) | env vars | — | Garmin + `GITHUB_TOKEN` for the MCP servers |
| `GARMIN_DATA_DIR` / `GARMIN_RESULT_DIR` | same abs path | rw | only when they point outside the repo |

> The full `~/.claude` directory is **not** mounted on purpose: it holds the live
> host session's `sessions/`, `history.jsonl` and `jobs/`, which a second Claude
> process would race on. Only the credential file is shared.

## Prerequisites

- Docker (tested with 27.x).
- Logged in to Claude Code on the host (`~/.claude/.credentials.json` exists), or
  be ready to log in inside the container.
- A populated `.env` at the repo root (`cp .env.example .env` + fill in), if you
  want the `garmin-db` / `github` MCP servers to authenticate.

## Usage

```bash
# from the repo root
docker/run.sh            # build the image, then drop into a shell in the container
```

Inside the container (first run):

```bash
uv sync --extra dev      # build the project venv at /home/claude/uv-venv (not the host .venv)
claude                   # start Claude Code; MCP servers auto-start from .mcp.json
```

Subsequent runs can skip the rebuild:

```bash
NO_BUILD=1 docker/run.sh
```

To launch Claude directly instead of a shell:

```bash
docker/run.sh claude
```

## Extending the egress allowlist

If a service you need is blocked, add its host to the `for domain in …` loop in
[`init-firewall.sh`](./init-firewall.sh) and rebuild (`docker/run.sh`). GitHub
itself is covered dynamically via `api.github.com/meta`, so most GitHub hosts work
out of the box.

Common signs you need to add a host:
- `uv sync` fails to reach an index → add the index host.
- A `401`/timeout on Claude login → add the relevant `*.anthropic.com` / `claude.ai` host.

## Known limitations

- **DNS at startup**: non-GitHub hosts are resolved once when the firewall is
  installed. If a CDN rotates IPs mid-session, that host may become unreachable —
  **restart the container** (`docker/run.sh`) to re-resolve. GitHub uses published
  CIDR ranges and is unaffected.
- **node_modules / .venv are not shared** with the host (the container uses its own
  `UV_PROJECT_ENVIRONMENT=/home/claude/uv-venv`). For frontend work run
  `npm install` inside `packages/garmin-web/frontend` in the container.
- **`SANDBOX_FIREWALL=0`** (passed as a container env var) starts the container with
  the firewall disabled — debugging only; it removes the exfiltration protection.
- The container fails to start if the firewall cannot be installed (fail-closed):
  it will not run with an open network unless you explicitly set `SANDBOX_FIREWALL=0`.
