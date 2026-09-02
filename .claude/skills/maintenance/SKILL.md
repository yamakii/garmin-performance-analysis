---
name: maintenance
description: "Run the repository maintenance pass — audit dependencies for vulnerabilities and outdated versions, apply security + minor/patch updates in a worktree, sync pre-commit revs, verify with ci-check, and ship a PR; majors and runtime changes are reported for a human decision. Use when the user asks for maintenance / dependency updates / security check (例:「メンテナンスして」「依存を更新」「脆弱性チェック」), or when the weekly security-audit issue is open. Optional argument --dry-run (audit + report only)."
argument-hint: [--dry-run]
allowed-tools: Bash, Read, Edit, Write, Glob, Grep, mcp__github__issue_read, mcp__github__issue_write, mcp__github__list_issues, mcp__github__list_pull_requests, mcp__github__pull_request_read, mcp__github__create_pull_request, mcp__github__merge_pull_request, mcp__github__add_issue_comment
---

# /maintenance — Dependency & Security Maintenance Pass

Policy: `.claude/rules/dev/maintenance-policy.md`. Runbook: `docs/maintenance.md`.
Owner: `yamakii`, repo: `garmin-performance-analysis` (all `mcp__github__*` calls).

The automated layer (Dependabot + `security-audit.yml` + `dependabot-auto-merge.yml`) handles
routine bumps by itself. This skill is the **catch-all pass** for what automation cannot decide:
audit the current state, apply everything that is safe, and hand the human a short list of
decisions (majors, upper-bound pins, runtime versions).

## Step 1 — Sync and audit (read-only)

1. `git fetch origin && git rev-list --count HEAD..origin/main`; if behind, `git merge --ff-only origin/main`.
2. Open automation state (GitHub MCP):
   - `list_issues(state="OPEN", labels=["security-audit"])` — open audit issue?
   - `list_pull_requests(state="open")` — Dependabot PRs waiting (majors need a decision; minors stuck = check `ci-guard`).
3. Python:
   ```bash
   uv lock --upgrade --dry-run                      # what would change (look for major bumps)
   uv export --frozen --no-hashes --all-packages --no-emit-workspace \
     --format requirements-txt -o "$CLAUDE_JOB_DIR/tmp/req.txt" 2>/dev/null \
     || uv export --frozen --no-hashes --all-packages --no-emit-workspace --format requirements-txt -o /tmp/req.txt
   uvx pip-audit -r <req.txt> --no-deps --desc off -f columns
   ```
4. npm (frontend): `npm --prefix packages/garmin-web/frontend outdated` and `npm --prefix packages/garmin-web/frontend audit --audit-level=high`.
5. Tooling drift: compare `.pre-commit-config.yaml` revs (ruff / black / pre-commit-hooks) with the locked
   versions in `uv.lock`; note GitHub Actions majors in `.github/workflows/*.yml` vs latest releases;
   note `.nvmrc` vs current Node LTS and `requires-python` vs current Python.

Classify every finding as **security** / **minor-patch** / **major** / **runtime** (Python, Node).
With `--dry-run`, stop here and report (Step 6 format).

## Step 2 — Issue

Create (or reuse an open) `chore(deps)` Issue via `issue_write` listing the security findings and the
planned minor/patch set, with `Validation Level: L2`. Majors go in an "out of scope — decision needed"
section, not in the plan.

## Step 3 — Apply in a worktree

`git worktree add .worktrees/deps-update-<YYYY-MM> -b chore/deps-update-<YYYY-MM> origin/main`, then:

1. **Security first.** If a fix requires crossing a major, still apply it and flag it explicitly.
2. Python: `uv lock --upgrade` (respects pyproject bounds). If the dry-run showed an unwanted major
   under a `>=`-only constraint, add an upper bound **with a reason comment** and re-lock.
   Upper bounds are exceptions, not defaults — re-evaluate each existing one (`grep -n '<[0-9]' packages/*/pyproject.toml`).
3. npm: `npm --prefix packages/garmin-web/frontend ci --no-audit` then `npm audit fix` and `npm update`
   (both stay inside `package.json` ranges; majors are never applied here).
4. pre-commit: set `ruff-pre-commit` rev = locked ruff version, `black` rev = locked black version,
   `pre-commit-hooks` rev = latest release.
5. Do **not** change `.nvmrc`, `requires-python`, or `python_version` — those are runtime decisions.

## Step 4 — Verify (sequential, never parallel)

```bash
uv run --directory <worktree> bash scripts/ci-check.sh
```
Exit 0 is the completion gate. With `UV_PROJECT_ENVIRONMENT` set (Docker sandbox), every worktree and
package shares ONE venv: never run server and web `uv sync` concurrently (the web sync removes the
server dev extras → mypy/pytest-xdist break). Re-run pip-audit / npm audit on the worktree to confirm 0 findings.

If `ruff`/`black`/`mypy` bumps introduce new violations, fix them in a **separate commit** (`style:`/`fix:`),
keeping the lockfile commit single-purpose.

## Step 5 — Ship

Commits (Conventional Commits, single concern each, Co-Authored-By trailer): e.g.
`chore(deps): upgrade Python lockfile (security: cryptography, mcp)`, `chore(deps): npm audit fix + minor updates`,
`chore(pre-commit): sync ruff/black revs`.
Push (`git -C <worktree> push -u origin <branch>`; if HTTPS auth fails and `GITHUB_TOKEN` is set, use the
inline credential helper), `create_pull_request` with `Closes #<issue>` and a `## Verification` section
(ci-check exit 0, pip-audit 0, npm audit 0). Poll `pull_request_read(method="get_check_runs")` until
`ci-guard` completes. Merge via `merge_pull_request(merge_method="merge")` when ci-guard = success and
mergeable (permanent approval #886 — L2 PASS + ci-guard green). Any other state → report, do not merge.

## Step 6 — Report

Short and decision-oriented:

| section | content |
|---------|---------|
| Fixed | security advisories closed (package, from → to, advisory id) |
| Updated | count of minor/patch bumps per ecosystem + notable ones |
| Decision needed | each major / runtime / upper-bound-pin item with 1-line impact and a link to the changelog |
| Automation health | Dependabot PRs open/stuck, security-audit issue state, anything the workflows could not do |

Never present a major or runtime change as done unless the human asked for it in this session.
