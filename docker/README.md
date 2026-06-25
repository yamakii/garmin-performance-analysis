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
| `.env` (via `--env-file`) | env vars | — | optional credential source for the MCP servers |
| `GARMIN_DATA_DIR` / `GARMIN_RESULT_DIR` | mounted + remapped (see below) | rw | only when set; in-repo dirs resolve to `/workspace/<rel>` |
| `$GARMINTOKENS` (default `~/.garth`) | same abs path | rw | persist garth OAuth token cache across runs (skip repeated logins) |

> The full `~/.claude` directory is **not** mounted on purpose: it holds the live
> host session's `sessions/`, `history.jsonl` and `jobs/`, which a second Claude
> process would race on. The container keeps its **own** session history in the
> named volume (persists across runs, but is **separate from the host's** — you
> can't resume a host conversation in the container and vice versa).

### Credentials: `.env` or host OS env

`docker/run.sh` accepts credentials from **either** `.env` **or** your host shell
environment — you don't need both. For each of `GARMIN_EMAIL`, `GARMIN_PASSWORD`,
`GARMIN_DATA_DIR`, `GARMIN_RESULT_DIR`, `GITHUB_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`,
`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, a value present in your host env is
forwarded into the container with `-e VAR` and **takes precedence** over the same
key in `.env`. This lets you keep secrets out of `.env`.

- **GitHub token**: if `GITHUB_TOKEN` isn't already exported, it is derived from
  `gh auth token` on the host (no PAT stored anywhere). Run `gh auth login` first.
- **Data/result dirs**: the container-side `GARMIN_DATA_DIR` / `GARMIN_RESULT_DIR`
  are remapped to the path where the dir is actually mounted — an in-repo dir
  becomes `/workspace/<rel>` (already mounted via the repo bind-mount); an
  out-of-repo dir is bind-mounted at the same absolute path. So the MCP server
  always resolves them to a real mounted location.

### Stop the container re-prompting for login

The container shares only the single file `~/.claude/.credentials.json` with the
host. Claude Code refreshes its OAuth token mid-session and rewrites that file
atomically (temp file + rename), which a **single-file bind mount can't persist**
back to the host — so the refreshed token is lost and the next run prompts to log
in again. (Sessions still persist; only auth doesn't.)

Fix it by supplying a non-interactive token via env — no file write-back needed:

```bash
# one-time, on the host (subscription-compatible, ~1-year token):
claude setup-token
export CLAUDE_CODE_OAUTH_TOKEN=<the printed token>   # add to your shell rc or .env
```

`docker/run.sh` forwards `CLAUDE_CODE_OAUTH_TOKEN` into the container, where it
outranks the (non-persisting) file-based OAuth, so the container is authenticated
on every run without a login prompt. `ANTHROPIC_API_KEY` (Console credits) or
`ANTHROPIC_AUTH_TOKEN` (gateway/proxy) work the same way if you prefer those.

## Prerequisites

- Docker (tested with 27.x).
- Logged in to Claude Code on the host (`~/.claude/.credentials.json` exists), or
  be ready to log in inside the container. To avoid re-logging-in on every run,
  export `CLAUDE_CODE_OAUTH_TOKEN` (see "Stop the container re-prompting for login").
- Credentials for the `garmin-db` / `github` MCP servers, supplied **either** via a
  populated `.env` (`cp .env.example .env` + fill in) **or** as host OS env vars
  (`GARMIN_EMAIL`, `GARMIN_PASSWORD`, …; `GITHUB_TOKEN` falls back to `gh auth token`).

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
