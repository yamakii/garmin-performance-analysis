# Maintenance Runbook

How dependencies and security stay current in this repository, what runs by
itself, and what still needs a human. Policy summary for Claude sessions lives
in `.claude/rules/dev/maintenance-policy.md`; the interactive pass is the
`/maintenance` skill.

## What runs automatically

| Component | File | Schedule | What it does |
|-----------|------|----------|--------------|
| Dependabot | `.github/dependabot.yml` | weekly (uv, npm) / monthly (actions, docker), Monday 09:00 JST | Opens update PRs. Minor + patch updates are grouped into one PR per ecosystem; each major gets its own PR. Security advisories trigger PRs outside the schedule. |
| Dependabot auto-merge | `.github/workflows/dependabot-auto-merge.yml` | on each Dependabot PR | Enables GitHub auto-merge for minor/patch PRs, so they merge once the required `ci-guard` check is green. Major PRs only get a comment asking for review. |
| Security audit | `.github/workflows/security-audit.yml` | weekly (Monday 09:00 JST), on lockfile PRs, and on demand (*Run workflow*) | `pip-audit` over the exported `uv.lock` and `npm audit --audit-level=high` over the frontend lockfile. A scheduled failure opens (or comments on) an issue labelled `security-audit`. |
| CI | `.github/workflows/ci.yml` | every PR / push to main | Lint, type-check, tests, build. `uv.lock` is in the path filter, so a lockfile-only PR still runs `lint-and-test`. Runs with a read-only `GITHUB_TOKEN`. |

## One-time repository settings

These cannot be committed; check them once in **Settings**:

1. **General → Pull Requests → Allow auto-merge**: must be on, otherwise the
   auto-merge workflow fails on every Dependabot PR (visibly, in the PR checks).
2. **Code security → Dependabot alerts / security updates**: turn on so GitHub
   raises security PRs immediately instead of waiting for the weekly schedule.
3. Branch protection on `main` must keep `ci-guard` as the required check
   (auto-merge waits for required checks only).

## Weekly routine (mostly hands-off)

1. Monday morning: Dependabot opens grouped PRs. Minor/patch PRs merge on their
   own when CI passes.
2. If a grouped PR fails CI, the failure is real (a dependency changed
   behaviour). Check the job log, fix in a follow-up commit on the Dependabot
   branch or close the PR and open an issue.
3. A `security-audit` issue means a vulnerability that Dependabot could not
   fix (no fixed release yet, or a transitive dependency pinned by a parent).
   Run `/maintenance` or fix by hand, re-run the workflow with *Run workflow*,
   and close the issue when it is green.

## Handling a major update PR

Dependabot leaves majors open with a comment. To process one:

1. Read the package changelog / migration guide linked in the PR body.
2. If no code change is needed: run `scripts/ci-check.sh` on the branch (or
   trust `ci-guard`) and merge.
3. If code changes are needed: open an issue with the migration plan
   (`Validation Level: L2`), implement in a worktree via the normal
   Issue → Worktree → PR flow, and close the Dependabot PR.
4. If the major should be deferred: add an upper bound in the relevant
   `pyproject.toml` / `package.json` **with a comment stating why**, so the
   pin is re-evaluated later instead of being forgotten.

Current deliberate upper bounds:

| Package | Bound | Reason | Re-evaluate |
|---------|-------|--------|-------------|
| `mcp` (garmin-mcp-server) | `>=1.28.1,<2` | The server uses the low-level `mcp.server.Server` + `stdio_server` API in `server.py`, `json_server.py`, `markdown_server.py`; the 2.x migration has not been assessed. | Issue #942 follow-up |

## Runtime versions (human decision)

Python (`requires-python`, `uv python install 3.12` in CI) and Node
(`.nvmrc`, `engines` in `package.json`) are **not** bumped by automation.
Changing them affects every contributor's environment and the Docker sandbox
image, so decide explicitly, then update CI, `docker/Dockerfile`, and docs in
one PR.

## Running the audit locally

```bash
# Python: audit exactly the locked set
uv export --frozen --no-hashes --all-packages --no-emit-workspace \
  --format requirements-txt -o /tmp/req.txt
uvx pip-audit -r /tmp/req.txt --no-deps --desc off -f columns

# Python: preview what a full upgrade would change (majors show up here)
uv lock --upgrade --dry-run

# npm (frontend)
npm --prefix packages/garmin-web/frontend audit --audit-level=high
npm --prefix packages/garmin-web/frontend outdated
```

Then apply updates in a worktree and verify with `scripts/ci-check.sh`.
Keep `.pre-commit-config.yaml` revs for `ruff` and `black` equal to the
versions in `uv.lock` so local hooks and CI agree.

### Shared uv environment caveat

When `UV_PROJECT_ENVIRONMENT` is set (the Docker sandbox sets it to
`/home/claude/uv-venv`), every worktree and both workspace packages share one
virtualenv. Running `uv sync` for `packages/garmin-web` while the server checks
are running removes the server's dev extras (pytest-xdist, pytest-cov, mypy's
typeshed) mid-run. Run the checks sequentially, exactly as `scripts/ci-check.sh`
does; do not parallelise `uv sync` across packages.

## Ignoring an advisory

Only when the vulnerable code path is provably unused. Add
`--ignore-vuln <ID>` to the `pip-audit` step in `security-audit.yml` (or an
`npm audit` exclusion) together with a comment giving the reason and a date to
revisit. Never ignore to make the weekly run quiet.
