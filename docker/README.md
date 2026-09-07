# Claude Code Docker sandbox

Run Claude Code on this project inside a Docker container so that
`dangerouslyDisableSandbox` (letting the agent run arbitrary bash) is acceptable:
**Docker is the trust boundary**, and an **egress allowlist firewall** prevents
mounted secrets from being exfiltrated even if a dependency or a prompt-injection
compromises the container.

This is a self-contained `docker run` setup (no devcontainer / VS Code required),
adapted for this project's full toolchain (Python 3.12 + uv + Node 24 + the three
MCP servers). The firewall started from the official
[`anthropics/claude-code` devcontainer](https://github.com/anthropics/claude-code/tree/main/.devcontainer)
and now gates on **DNS** instead of startup-resolved IPs (see below).

### How the egress gate works

The allowlist is [`allowed-domains.txt`](./allowed-domains.txt) (one domain per
line; an entry covers the domain and all its subdomains). At container start,
`init-firewall.sh`:

1. starts **dnsmasq as the only resolver** (`/etc/resolv.conf` → `127.0.0.1`),
   configured to forward *only* allowlisted names to the upstream DNS server and to
   add every IPv4 it returns to the `allowed-domains` ipset **at resolution time**;
2. **refuses every other name locally** — it never reaches the upstream resolver
   (no DNS tunnelling) and never obtains an IP to connect to;
3. installs iptables rules that accept loopback, dnsmasq's own upstream queries
   (matched by uid), the Docker host network, established flows and the ipset —
   and reject everything else, including port 53 / 22 towards arbitrary hosts.

Nothing on the client side changes: `WebFetch`, the MCP servers, `uv`, `git` and
`curl` all resolve through the normal resolver and just work for listed hosts.
Because IPs enter the set when they are resolved, CDN rotation mid-session is no
longer a problem, and the old `api.github.com/meta` CIDR prefetch (with its
rate-limit fail-closed mode) is gone — `github.com` is simply an allowlisted name.

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
| **egress allowlist** (`init-firewall.sh` + dnsmasq, `allowed-domains.txt`) | sending secrets / data to an arbitrary host, DNS tunnelling, SSH/DNS to arbitrary hosts | exfiltration to an **allowlisted** host (a malicious GitHub repo, or a GET with a query string to a docs-tier host); a direct connection to an IP that happens to be in the set because an allowlisted CDN neighbour resolved to it |
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
>
> The image also sets `CLAUDE_CONFIG_DIR=/home/claude/.claude` so Claude Code's
> `.claude.json` (auth session, per-project trust, user-scoped MCP servers) lands
> **inside** the mounted dir. By default it lives at `$HOME/.claude.json` — a
> sibling of `~/.claude/`, outside the mount — and would be lost every restart
> ("Claude configuration file not found at: /home/claude/.claude.json").

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

### Python inside the image

The project interpreter is **uv-managed** (`uv python install 3.12` at build
time, stored under `/opt/uv/python`), not the base image's apt Python. This
decouples the Ubuntu release from `requires-python`: bumping `FROM ubuntu:…`
does not change which Python the project runs on, and vice versa. The distro
`python3` is still installed, but only for OS-level scripting (the
`.claude/hooks/*.sh` JSON one-liners). At runtime `UV_PYTHON_DOWNLOADS=never`
stays in effect, so the egress allowlist needs no Python download host.

To change the project Python version, edit the `uv python install <version>`
line (and `UV_PYTHON`) in the Dockerfile together with `requires-python` and CI,
then rebuild.

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

If a service you need is blocked, add its domain to
[`allowed-domains.txt`](./allowed-domains.txt) and rebuild (`docker/run.sh`). An
entry covers the domain **and all its subdomains** (`github.com` already covers
`api.github.com`, `codeload.github.com`, …), so list the apex when the whole
vendor is trusted and a specific host when it is not. The file is validated at
boot (a malformed line refuses to start the container) and on the host by
`scripts/tests/test-sandbox-allowlist.sh`.

A read-only **documentation tier** (python.org, duckdb.org, docs.astral.sh, …) is
included so `WebFetch` can read upstream docs. Keep additions to vendors whose docs
the project actually reads: a GET with a query string can still carry data out.

Common signs you need to add a host:
- **`WebFetch` fails with `Command failed with no output`** — that is what a
  blocked host looks like from the tool. Confirm from a container shell with
  `getent hosts <host>` (unlisted → no result) or
  `curl -s -o /dev/null -w '%{http_code}' --connect-timeout 4 https://<host>`
  (`000` = blocked, anything else = reachable).
- `uv sync` fails to reach an index → add the index host.
- A `401`/timeout on Claude login → add the relevant `*.anthropic.com` / `claude.ai` host.

## Claude Code's built-in sandbox: pinned off

Claude Code has its own Bash sandbox (bubblewrap + a hostname-filtering proxy).
It is **deliberately not enabled** inside this container: the image ships a
static [`managed-settings.json`](./managed-settings.json) (`sandbox.enabled:
false`) that overrides the `sandbox.enabled: true` the host may have saved into
the bind-mounted `.claude/settings.local.json`, and bubblewrap is not installed.
Two reasons, both established on 2026-09-07 (#1028, #1031, #1032, #1033):

1. **It cannot run here.** bubblewrap needs an unprivileged user namespace, and
   every hardening layer blocks it — relaxing one only exposes the next
   (probed in CI on an Ubuntu 24.04 runner with the same `docker run` flags as
   `run.sh`):

   | Relaxed | `bwrap` error |
   |---------|---------------|
   | nothing (default) | `No permissions to create a new namespace` — Docker's default seccomp profile refuses `unshare(CLONE_NEWUSER)` |
   | `--security-opt seccomp=unconfined` | `Failed to make / slave: Permission denied` — the `docker-default` AppArmor profile denies `mount` |
   | `--security-opt apparmor=unconfined` | `No permissions to create a new namespace` — seccomp again |
   | both | `setting up uid map: Permission denied` — the **host** sysctl `kernel.apparmor_restrict_unprivileged_userns=1` (Ubuntu 24.04 default) |

   Making it work means a custom seccomp profile, an AppArmor profile that
   permits `mount`, **and** turning off Ubuntu's unprivileged-userns restriction
   for the whole host — three reductions of the outer hardening.
2. **It would add little.** It covers only Bash (not the MCP servers, `WebFetch`
   or Claude's own file tools); its hostname allowlist duplicates the firewall's
   DNS gate, which already applies to every process; its write scoping stays
   within the blast radius the threat model already accepts; and it cannot stop
   the one residual exfil path, an allowlisted host.

Why pin it off instead of leaving it unconfigured: with bubblewrap *missing*,
Claude Code silently falls back to unsandboxed Bash, but with bubblewrap
installed and unable to unshare **every sandboxed Bash command fails** (observed
after #1030). The pin plus the absence of `bwrap` makes the container's behaviour
independent of whatever `settings.local.json` says; `sandbox-smoke.sh` asserts
both. If the trade above is ever made on purpose, revert #1033.

## Verifying the sandbox

After a rebuild (or whenever egress behaves oddly), boot a throwaway container
straight into the smoke test; it runs as the unprivileged `claude` user after the
firewall is up and proves the gate from the inside:

```bash
NO_BUILD=1 docker/run.sh sandbox-smoke.sh
```

It checks that allowlisted names resolve and connect, that unlisted names are
refused by the resolver, that DNS/SSH to foreign hosts and direct connections to
non-allowlisted IPs are rejected, and that the docs tier is reachable. The same
script runs in CI (`docker-build` job) on every `docker/**` change.

## Known limitations

- **Name-based, not content-based**: the gate decides on the resolved name. It
  does not inspect TLS, so a process that already holds an allowlisted IP can talk
  to any port on it, and a GET to an allowlisted host can carry data in its URL.
  Treat every entry in `allowed-domains.txt` as a host you are willing to send
  data to.
- **IPv6 is filtered** (`filter-AAAA`): the container has no IPv6 egress and the
  ipset is IPv4-only, so AAAA answers are dropped to avoid connect timeouts.
- **node_modules / .venv are not shared** with the host (the container uses its own
  `UV_PROJECT_ENVIRONMENT=/home/claude/uv-venv`). For frontend work run
  `npm install` inside `packages/garmin-web/frontend` in the container.
- **`SANDBOX_FIREWALL=0`** (passed as a container env var) starts the container with
  the firewall disabled — debugging only; it removes the exfiltration protection.
- The container fails to start if the firewall cannot be installed or its
  self-check fails (fail-closed — e.g. a malformed `allowed-domains.txt`, dnsmasq
  not starting, or `api.github.com` unreachable): it will not run with an open
  network unless you explicitly set `SANDBOX_FIREWALL=0`.
