# syntax=docker/dockerfile:1
#
# Claude Code sandbox image for garmin-performance-analysis.
#
# Docker is the trust boundary: `dangerouslyDisableSandbox` (arbitrary bash from
# the agent) is acceptable INSIDE this container because capabilities are dropped,
# the writable scope is the mounted repo, and init-firewall.sh restricts egress to
# an allowlist (see entrypoint.sh / init-firewall.sh).
#
# Full dev environment: Python 3.12 + uv + Node 24 + native libs + Claude Code,
# so analysis, implementation, tests and all three MCP servers run inside.

FROM ubuntu:26.04

# ---- build args ----
ARG CLAUDE_CODE_VERSION=latest
ARG NODE_MAJOR=24
# Match the host uid/gid so the bind-mounted repo + data/ stay correctly owned.
# run.sh passes the caller's id; 1000 is the typical first Linux user.
ARG USER_UID=1000
ARG USER_GID=1000
ARG TZ=Asia/Tokyo

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ="${TZ}"

# ---- system packages ----
#  python3                  : the DISTRO python, only for OS-level scripting (the
#                             .claude/hooks/*.sh `python3 -c` JSON one-liners). The
#                             project interpreter is uv-managed (see below), so this
#                             may be whatever version the base image ships.
#  build-essential, libgomp1: native wheel safety net (scipy/scikit-learn OpenMP runtime)
#  iptables/ipset/iproute2  : egress firewall (init-firewall.sh)
#  dnsmasq-base             : allowlist-only resolver that feeds the ipset (DNS is
#                             the gate, see init-firewall.sh). -base = binary only,
#                             no init script trying to start a service at build time.
#  dnsutils                 : `dig` for the firewall self-check + sandbox-smoke.sh
#  jq                       : sandbox-smoke.sh JSON checks
#  git/curl/ca-certificates : tooling + `uvx serena` (installs from git)
# The `dnsmasq` system user is what the resolver drops to; iptables matches its uid
# to let ONLY the resolver reach the upstream DNS server.
# Deliberately NOT installed: bubblewrap + socat (Claude Code's built-in Bash
# sandbox). It cannot create a user namespace under this container's hardening
# and is pinned off by managed-settings.json — see docker/README.md (#1033).
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git unzip gnupg \
      python3 \
      build-essential libgomp1 \
      iptables ipset iproute2 dnsmasq-base dnsutils jq \
    && rm -rf /var/lib/apt/lists/* \
    && (getent passwd dnsmasq >/dev/null \
        || useradd --system --no-create-home --shell /usr/sbin/nologin dnsmasq)

# ---- Node.js (NodeSource, matches repo .nvmrc=24) ----
RUN curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# ---- uv (Astral) ----
# The real binaries live in /usr/local/lib/uv; /usr/local/bin/uv is the wrapper
# below (#1047), which derives UV_PROJECT_ENVIRONMENT per checkout so a worktree
# command never re-syncs the MCP server's venv. uvx is untouched (symlink).
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/lib/uv sh \
    && ln -s /usr/local/lib/uv/uvx /usr/local/bin/uvx
COPY lib/uv-venv.sh /usr/local/lib/sandbox/uv-venv.sh
COPY uv-wrapper.sh /usr/local/bin/uv
RUN chmod +x /usr/local/bin/uv

# ---- project Python: uv-managed, downloaded at BUILD time only ----
# Decouples the project interpreter from the base image's apt Python, so the
# Ubuntu release can move without touching `requires-python` (and vice versa).
# The install lands in a world-readable system dir (not root's ~/.local) so the
# unprivileged `claude` user finds it; at runtime UV_PYTHON_DOWNLOADS=never (set
# below) keeps uv from ever fetching an interpreter, so the egress allowlist in
# init-firewall.sh does not change.
ENV UV_PYTHON_INSTALL_DIR=/opt/uv/python
RUN uv python install 3.12 \
    && chmod -R a+rX /opt/uv

# ---- Claude Code CLI ----
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}

# ---- non-root user matching the host uid/gid ----
# ubuntu:24.04 ships a uid 1000 "ubuntu" user; rename/repurpose it to `claude`
# instead of failing. For any other uid, create the user fresh.
RUN if getent group "${USER_GID}" >/dev/null; then \
        groupmod -n claude "$(getent group "${USER_GID}" | cut -d: -f1)"; \
    else \
        groupadd -g "${USER_GID}" claude; \
    fi \
    && if getent passwd "${USER_UID}" >/dev/null; then \
        usermod -l claude -d /home/claude -m "$(getent passwd "${USER_UID}" | cut -d: -f1)"; \
    else \
        useradd -m -u "${USER_UID}" -g "${USER_GID}" -s /bin/bash claude; \
    fi \
    && mkdir -p /home/claude/.claude /home/claude/uv-venvs /workspace \
    && chown -R "${USER_UID}:${USER_GID}" /home/claude /workspace

# ---- environment ----
# The container's uv venvs live OUTSIDE the bind-mounted /workspace so they never
# clobber the host .venv: one per (checkout, package) under /home/claude/uv-venvs,
# chosen by the /usr/local/bin/uv wrapper (docker/lib/uv-venv.sh) — there is
# deliberately NO global UV_PROJECT_ENVIRONMENT any more (#1047). UV_PYTHON=3.12
# resolves to the uv-managed interpreter installed above; UV_PYTHON_DOWNLOADS=never
# means no managed downloads at runtime (= smaller egress surface).
# DISABLE_AUTOUPDATER=1: Claude Code is npm-global-installed as root but runs as
# the non-root `claude` user (cap-drop ALL, no-new-privileges), so the in-place
# auto-updater can't write the global npm dir and fails on startup. Updating is
# done by rebuilding the image (see CLAUDE_CODE_VERSION build-arg / docker/README).
# CLAUDE_CONFIG_DIR=/home/claude/.claude: by default Claude Code writes its big
# config file to $HOME/.claude.json — a SIBLING of ~/.claude/, so OUTSIDE the
# bind-mounted ~/.claude dir → lost on every restart ("config file not found").
# Pointing CLAUDE_CONFIG_DIR at the mounted dir relocates .claude.json (and all
# config) inside it, so auth/trust/MCP state persists. Sessions already live at
# $CLAUDE_CONFIG_DIR/… so no data moves; the atomic rewrite stays within the mount.
ENV UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=3.12 \
    PATH=/usr/local/bin:$PATH \
    SHELL=/bin/bash \
    DISABLE_AUTOUPDATER=1 \
    CLAUDE_CONFIG_DIR=/home/claude/.claude

# ---- firewall + entrypoint ----
# allowed-domains.txt is the single source of the egress allowlist (edit + rebuild).
# lib/allowlist.sh holds the pure logic (also unit-tested on the host by
# scripts/tests/test-sandbox-allowlist.sh); sandbox-smoke.sh proves the gate from
# inside a booted container (CI docker-build job, or `docker/run.sh sandbox-smoke.sh`).
# managed-settings.json pins Claude Code's built-in sandbox OFF inside the
# container (managed settings override the bind-mounted .claude/settings.local.json,
# whose `sandbox.enabled: true` was saved on the host). Docker is the boundary.
COPY managed-settings.json /etc/claude-code/managed-settings.json
COPY allowed-domains.txt /etc/sandbox/allowed-domains.txt
COPY lib/allowlist.sh /usr/local/lib/sandbox/allowlist.sh
COPY init-firewall.sh /usr/local/bin/init-firewall.sh
COPY sandbox-smoke.sh /usr/local/bin/sandbox-smoke.sh
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/init-firewall.sh /usr/local/bin/sandbox-smoke.sh /usr/local/bin/entrypoint.sh

WORKDIR /workspace

# The container starts as root only long enough for entrypoint.sh to install the
# egress firewall, then drops to the unprivileged `claude` user before running CMD.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["bash"]
