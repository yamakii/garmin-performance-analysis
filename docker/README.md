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
| **Claude Code built-in sandbox** (bubblewrap + socat, managed settings — [below](#claude-codes-built-in-sandbox-inside-the-container)) | a Bash command writing outside the working dir / listed paths, or reaching a host the allowlist does not name; with `CLAUDE_CREDENTIAL_MASK=1`, a Bash command reading `GARMIN_PASSWORD` / `GITHUB_TOKEN` | anything the MCP servers or `WebFetch` do (they are not sandboxed); a command Claude re-runs with `dangerouslyDisableSandbox` |

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

## Claude Code's built-in sandbox inside the container

Claude Code has its own Bash sandbox (bubblewrap + a hostname-filtering proxy).
Before #1028 the image shipped neither `bwrap` nor `socat`, so the
`sandbox.enabled: true` in `.claude/settings.local.json` silently fell back to
unsandboxed Bash inside the container. The image now carries both, and the
entrypoint writes a **managed settings** file
(`/etc/claude-code/managed-settings.json`, generated by
[`lib/gen-managed-settings.sh`](./lib/gen-managed-settings.sh)) on every boot:

| Key | Value | Why |
|-----|-------|-----|
| `sandbox.enabled` | `true` | second layer inside Docker: per-command filesystem scope + hostname allowlist for **Bash** |
| `enableWeakerNestedSandbox` | `true` | under `--cap-drop ALL` + Docker's default seccomp profile bubblewrap cannot mount a fresh `/proc`; the outer container is the boundary |
| `autoAllowBashIfSandboxed` | `true` | sandboxed commands run without prompts |
| `filesystem.allowWrite` | uv venv, `~/.cache`, `~/.npm`, `~/.claude/{jobs,projects}`, `/tmp`, `$GARMIN_DATA_DIR`, `$GARMIN_RESULT_DIR`, `$GARMINTOKENS` | what `uv sync`, the MCP scripts and Claude's own job/memory writes need outside the working dir |
| `network.allowedDomains` | every `allowed-domains.txt` entry as `d` + `*.d` | same list as the firewall, so sandboxed commands never hit a domain prompt |

Managed settings are the tier Claude Code honours for credential masking and
their booleans override the bind-mounted project/user settings, so the policy is
**container-only and repo-controlled**; the `sandbox` block in
`.claude/settings.local.json` keeps applying on the host and is superseded in the
container. Before writing the file, the entrypoint **probes whether bubblewrap
can create a user namespace** as the `claude` user; if it cannot, the file says
`enabled: false` and a boot log line says why. This matters because Claude Code
only falls back to unsandboxed Bash when bubblewrap is *missing* — with
bubblewrap installed but unable to unshare, **every sandboxed Bash command fails**
with the bwrap error (observed on the hardened container). `sandbox-smoke.sh`
reports which case you are in and fails if the policy and the probe disagree.

Two switches, forwarded from your shell by `docker/run.sh`:

- **`CLAUDE_SANDBOX=0`** — write an explicit `enabled: false` (e.g. while
  diagnosing a `Read-only file system` failure from a path missing in
  `allowWrite`; add the path to the generator instead of leaving this off).
- **`CLAUDE_CREDENTIAL_MASK=1`** — opt-in. Sandboxed commands see a placeholder
  for `GARMIN_PASSWORD` / `GITHUB_TOKEN`; the sandbox proxy injects the real
  value only on requests to the Garmin auth/API hosts and `api.github.com` /
  `github.com`. This needs the proxy to **terminate TLS**
  (`network.tlsTerminate`), which means every sandboxed client (`uv`, Python
  `certifi`, `git`) must trust the proxy's CA — the Claude Code docs do not
  state how that trust is established for third-party tools, so try it, run
  `uv sync` and `uv run python -m garmin_mcp.scripts.bulk_fetch_raw_data …`
  from a Claude session, and keep it on only if both work. The MCP servers are
  not sandboxed and keep the real credentials either way.

Verify from a Claude session with `/sandbox`: the panel shows whether the
sandbox is active and which policy is in force.

### Why it still falls back on a hardened host

bubblewrap needs an unprivileged **user namespace**. Probed in CI (Ubuntu 24.04
runner, same `docker run` flags as `run.sh`), every hardening layer blocks it,
and relaxing one only exposes the next:

| Relaxed | `bwrap` error |
|---------|---------------|
| nothing (default) | `No permissions to create a new namespace` — Docker's default seccomp profile refuses `unshare(CLONE_NEWUSER)` |
| `--security-opt seccomp=unconfined` | `Failed to make / slave: Permission denied` — the `docker-default` AppArmor profile denies `mount` |
| `--security-opt apparmor=unconfined` | `No permissions to create a new namespace` — seccomp again |
| both | `setting up uid map: Permission denied` — the **host** sysctl `kernel.apparmor_restrict_unprivileged_userns=1` (Ubuntu 24.04 default) gives an unconfined process no capabilities inside its new namespace |

So an effective built-in sandbox needs a custom seccomp profile, an AppArmor
profile that permits `mount`, **and** turning off Ubuntu's unprivileged-userns
restriction on the host — three deliberate reductions of the outer hardening,
to gain an inner layer that covers only Bash. Until that trade is made on
purpose, the entrypoint's probe fails, the managed policy says
`enabled: false`, Bash runs unsandboxed as before, `sandbox-smoke.sh` prints the
exact `bwrap` error and the seccomp / AppArmor / sysctl state, and Docker remains
the boundary. In that state `CLAUDE_CREDENTIAL_MASK=1` has nothing to act on
either. Once the host allows the namespace, the same boot flips the policy on
without any config change.

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
