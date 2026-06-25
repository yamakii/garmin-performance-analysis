# syntax=docker/dockerfile:1
#
# Claude Code sandbox image for garmin-performance-analysis.
#
# Docker is the trust boundary: `dangerouslyDisableSandbox` (arbitrary bash from
# the agent) is acceptable INSIDE this container because capabilities are dropped,
# the writable scope is the mounted repo, and init-firewall.sh restricts egress to
# an allowlist (see entrypoint.sh / init-firewall.sh).
#
# Full dev environment: Python 3.12 + uv + Node 22 + native libs + Claude Code,
# so analysis, implementation, tests and all three MCP servers run inside.

FROM ubuntu:24.04

# ---- build args ----
ARG CLAUDE_CODE_VERSION=latest
ARG NODE_MAJOR=22
# Match the host uid/gid so the bind-mounted repo + data/ stay correctly owned.
# run.sh passes the caller's id; 1000 is the typical first Linux user.
ARG USER_UID=1000
ARG USER_GID=1000
ARG TZ=Asia/Tokyo

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ="${TZ}"

# ---- system packages ----
#  python3.12(+venv)        : project runtime (uv uses the system interpreter; no managed-Python downloads)
#  build-essential, libgomp1: native wheel safety net (scipy/scikit-learn OpenMP runtime)
#  iptables/ipset/iproute2  : egress firewall (init-firewall.sh)
#  dnsutils/aggregate/jq    : firewall domain resolution + GitHub meta range processing
#  git/curl/ca-certificates : tooling + `uvx serena` (installs from git)
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git unzip gnupg \
      python3.12 python3.12-venv python3-pip \
      build-essential libgomp1 \
      iptables ipset iproute2 dnsutils aggregate jq \
    && rm -rf /var/lib/apt/lists/*

# ---- Node.js (NodeSource, matches repo .nvmrc=22) ----
RUN curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# ---- uv (Astral) into /usr/local/bin (on PATH for every user) ----
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

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
    && mkdir -p /home/claude/.claude /home/claude/uv-venv /workspace \
    && chown -R "${USER_UID}:${USER_GID}" /home/claude /workspace

# ---- environment ----
# Keep the container's uv venv OUTSIDE the bind-mounted /workspace so it never
# clobbers the host .venv. Use the system Python (no managed downloads at runtime
# = smaller egress surface).
# DISABLE_AUTOUPDATER=1: Claude Code is npm-global-installed as root but runs as
# the non-root `claude` user (cap-drop ALL, no-new-privileges), so the in-place
# auto-updater can't write the global npm dir and fails on startup. Updating is
# done by rebuilding the image (see CLAUDE_CODE_VERSION build-arg / docker/README).
ENV UV_PROJECT_ENVIRONMENT=/home/claude/uv-venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=python3.12 \
    PATH=/usr/local/bin:$PATH \
    SHELL=/bin/bash \
    DISABLE_AUTOUPDATER=1

# ---- firewall + entrypoint ----
COPY init-firewall.sh /usr/local/bin/init-firewall.sh
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/init-firewall.sh /usr/local/bin/entrypoint.sh

WORKDIR /workspace

# The container starts as root only long enough for entrypoint.sh to install the
# egress firewall, then drops to the unprivileged `claude` user before running CMD.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["bash"]
