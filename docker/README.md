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
| `$CLAUDE_DOCKER_HOME` (default `~/.claude-docker`) | `/home/claude/.claude` | rw | the container's own Claude home — sessions/history/auth persist on the host, **isolated from the host's `~/.claude`** |
| `.env` (via `--env-file`) | env vars | — | optional credential source for the MCP servers |
| `GARMIN_DATA_DIR` / `GARMIN_RESULT_DIR` | mounted + remapped (see below) | rw | only when set; in-repo dirs resolve to `/workspace/<rel>` |
| `$GARMINTOKENS` (default `~/.garth`) | same abs path | rw | persist garth OAuth token cache across runs (skip repeated logins) |

> The container's `~/.claude` is a **dedicated host directory** (`~/.claude-docker`
> by default), **not** the host's own `~/.claude`. That keeps its sessions,
> `history.jsonl`, `jobs/` and `.credentials.json` persistent on the host across
> runs while never racing the live host Claude session. Because it's a *directory*
> bind mount (not the old named volume + single-file credentials mount), Claude
> Code's atomic OAuth token refresh persists too: **you log in once inside the
> container and it sticks** — no re-login every run. The container's session
> history is its own and is **not shared** with the host's (you can't resume a
> host conversation in the container, by design).

### Credentials: `.env` or host OS env

`docker/run.sh` accepts credentials from **either** `.env` **or** your host shell
environment — you don't need both. For each of `GARMIN_EMAIL`, `GARMIN_PASSWORD`,
`GARMIN_DATA_DIR`, `GARMIN_RESULT_DIR`, `GITHUB_TOKEN`, a value present in your
host env is forwarded into the container with `-e VAR` and **takes precedence**
over the same key in `.env`. This lets you keep secrets out of `.env`.

- **GitHub token**: if `GITHUB_TOKEN` isn't already exported, it is derived from
  `gh auth token` on the host (no PAT stored anywhere). Run `gh auth login` first.
- **Data/result dirs**: the container-side `GARMIN_DATA_DIR` / `GARMIN_RESULT_DIR`
  are remapped to the path where the dir is actually mounted — an in-repo dir
  becomes `/workspace/<rel>` (already mounted via the repo bind-mount); an
  out-of-repo dir is bind-mounted at the same absolute path. So the MCP server
  always resolves them to a real mounted location.

## Prerequisites

- Docker (tested with 27.x).
- On first run, log in to Claude **inside the container** once — it persists in
  `~/.claude-docker` on the host, so later runs don't prompt again. (The host's
  own `~/.claude` login is intentionally not shared.)
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

### Updating Claude Code

Claude Code's in-container auto-updater is **disabled** (`DISABLE_AUTOUPDATER=1`):
it's npm-global-installed as root but runs as the non-root `claude` user, so it
can't write the global npm dir and would just fail on startup. Update by
rebuilding the image with the target version:

```bash
CLAUDE_CODE_VERSION=2.1.193 docker/run.sh   # reinstalls that version
```

`run.sh` passes `CLAUDE_CODE_VERSION` (default `latest`) as a build-arg. Changing
the value busts the cached `npm install -g …@<version>` layer; a plain rebuild
reuses it and won't pick up a newer release. To force the newest without pinning,
rebuild that layer fresh with `docker build --no-cache` (or bump the version).

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
