export const meta = {
  name: 'implement-tier',
  description:
    'Implement one tier of design-approved issues: parallel worktree implementation, parallel L1/L2 validation, then auto-merge PRs that pass validation + ci-guard (human gate only on the exceptions)',
  phases: [
    { title: 'Implement', detail: 'one worktree developer agent per issue (parallel)' },
    { title: 'Validate', detail: 'L1/L2 validation per implementation (parallel, subprocess)', model: 'sonnet' },
    { title: 'Ship', detail: 'push, create PR, poll ci-guard', model: 'sonnet' },
    { title: 'Merge', detail: 'auto-merge on validation pass + ci green; else escalate', model: 'sonnet' },
  ],
}

// ── args ──────────────────────────────────────────────────────────────
// {
//   owner: string, repo: string,
//   issues: [{ number: int, title: string }],   // one tier; deps already resolved by caller
//   tierName?: string,
// }
// ── pure logic (side-effect-free; extracted & unit-tested in CI) ─────────
// The block between the markers below is evaluated by
// .claude/workflows/tests/implement-tier.test.mjs (node --test, run by the
// CI meta-checks job). Keep it free of top-level side effects / workflow
// globals so the test can extract and exercise it directly.
// >>> testable
// The harness may deliver `args` as a JSON string rather than a parsed object,
// so normalize before reading fields (accept string, object, or undefined).
function normalizeArgs(raw) {
  if (typeof raw === 'string') {
    try {
      return JSON.parse(raw)
    } catch {
      return {}
    }
  }
  return raw && typeof raw === 'object' ? raw : {}
}

// Decide auto-merge purely (deterministic). Returns { ok, reason }.
function mergeDecision(acc) {
  const v = acc.validation ?? {}
  const s = acc.ship ?? {}
  if (v.level === 'L3') return { ok: false, reason: 'L3 (agent 定義変更) はメインセッション担当。auto-merge 対象外' }
  if (v.status === 'fail') return { ok: false, reason: `検証 FAIL: ${v.details ?? ''}` }
  if (v.status === 'warning') return { ok: false, reason: `内容チェック WARNING: ${v.details ?? ''} — 人間判断へ` }
  if (s.ci_conclusion !== 'success') return { ok: false, reason: `ci-guard が ${s.ci_conclusion}` }
  if (!s.mergeable) return { ok: false, reason: 'コンフリクト / mergeable=false' }
  if (!s.pr_number) return { ok: false, reason: 'PR 未作成' }
  return { ok: true, reason: '検証 PASS + ci-guard success + mergeable' }
}

// Build the push command for the ship prompt. Worktrees have no credential
// helper, so bare `git push https://github.com` fails with "could not read
// Username" → pr_number=null → misleading "PR 未作成" escalation. Inject an
// inline helper feeding GITHUB_TOKEN (token never touches the URL / process
// args, so it stays out of `ps` output).
function pushCmd(worktreePath, branch) {
  return (
    `git -C ${worktreePath} ` +
    `-c credential.helper='!f(){ echo username=x-access-token; echo password=$GITHUB_TOKEN; };f' ` +
    `push -u origin ${branch}`
  )
}

// Resolve the Merge-stage outcome purely. On success the green decision reason
// is kept; on failure the merge agent's actual `error` is surfaced (instead of
// the stale success sentence) so the human reading the escalation sees the real
// cause. Returns { merged, reason, merge_sha }.
function mergeResult(decisionReason, mg) {
  const merged = mg?.merged === true
  const reason = merged ? decisionReason : (mg?.error ?? 'merge_pull_request 失敗')
  return { merged, reason, merge_sha: mg?.merge_sha ?? null }
}
// <<< testable

const ARGS = normalizeArgs(args)
const OWNER = ARGS.owner ?? 'yamakii'
const REPO = ARGS.repo ?? 'garmin-performance-analysis'
const ISSUES = ARGS.issues ?? []

// ── schemas ───────────────────────────────────────────────────────────
const MANIFEST_SCHEMA = {
  type: 'object',
  required: ['issue_number', 'branch', 'worktree_path', 'validation_level', 'changed_files', 'commit_hash'],
  properties: {
    issue_number: { type: 'integer' },
    branch: { type: 'string' },
    worktree_path: { type: 'string' },
    server_dir: { type: 'string' },
    validation_level: { enum: ['L1', 'L2', 'L3', 'skip'] },
    change_category: { type: 'string' },
    changed_files: { type: 'array', items: { type: 'string' } },
    test_results: {
      type: 'object',
      properties: { unit: { type: 'string' }, integration: { type: 'string' } },
    },
    verification_activity_id: { type: ['integer', 'null'] },
    implemented: { type: 'boolean' },
    notes: { type: 'string' },
  },
}

const VALIDATION_SCHEMA = {
  type: 'object',
  required: ['status', 'level'],
  properties: {
    status: { enum: ['pass', 'fail', 'warning'] },
    level: { enum: ['L1', 'L2', 'L3', 'skip'] },
    details: { type: 'string' },
  },
}

const SHIP_SCHEMA = {
  type: 'object',
  required: ['pr_number', 'pr_url', 'ci_conclusion', 'mergeable'],
  properties: {
    pr_number: { type: ['integer', 'null'] },
    pr_url: { type: ['string', 'null'] },
    ci_conclusion: { enum: ['success', 'failure', 'pending', 'unknown'] },
    mergeable: { type: 'boolean' },
    head_sha: { type: ['string', 'null'] },
    notes: { type: 'string' },
  },
}

const MERGE_SCHEMA = {
  type: 'object',
  required: ['merged'],
  properties: { merged: { type: 'boolean' }, merge_sha: { type: ['string', 'null'] }, error: { type: 'string' } },
}

// ── helpers ───────────────────────────────────────────────────────────
function repoCtx() {
  return `owner="${OWNER}", repo="${REPO}"`
}

// mergeDecision / normalizeArgs / pushCmd / mergeResult are defined in the
// testable block near the top.

// ── pipeline: each issue flows Implement → Validate → Ship → Merge independently ──
const results = await pipeline(
  ISSUES,

  // Stage 1 — Implement in an isolated worktree (developer agent, no push).
  (issue) =>
    agent(
      `あなたは developer エージェントです。Issue #${issue.number}（${issue.title}）を実装してください。\n\n` +
        `1. mcp__github__issue_read(method="get", ${repoCtx()}, issue_number=${issue.number}) で設計を読む。\n` +
        `2. .claude/agents/developer.md のフローに従い、worktree 内で実装 + unit/integration テスト + ruff + (変更ファイルへ) get_diagnostics_for_file。\n` +
        `3. Conventional Commits で commit（"Closes #${issue.number}" を含む）。**push はしない**。\n` +
        `4. Validation Level を dev-reference.md §3 判定表で決定。\n\n` +
        `重要: manifest を /tmp に書かず、**この呼び出しの構造化出力として返す**こと（schema 準拠）。` +
        `worktree_path はこの worktree の絶対パス、branch は作成したブランチ名、commit_hash は HEAD の短縮 SHA。` +
        `実装・commit まで完了したら implemented=true。`,
      { label: `impl:#${issue.number}`, phase: 'Implement', isolation: 'worktree', agentType: 'developer', schema: MANIFEST_SCHEMA }
    ),

  // Stage 2 — Validate (L1/L2 via subprocess; skip/L3 short-circuit in JS).
  (manifest, issue) => {
    if (!manifest || !manifest.implemented) return null
    if (manifest.validation_level === 'skip')
      return { manifest, validation: { status: 'pass', level: 'skip', details: 'skip: コードレビューのみ（CI が品質ゲート）' } }
    if (manifest.validation_level === 'L3')
      return { manifest, validation: { status: 'warning', level: 'L3', details: 'L3 はメインセッションが担当。Workflow では検証しない' } }
    return agent(
      `あなたは validation-agent です。worktree のコード変更を ${manifest.validation_level} で検証してください。\n` +
        `manifest: ${JSON.stringify(manifest)}\n` +
        `.claude/rules/dev/worktree-validation-protocol.md の L1/L2 手順（reload_server を使わず subprocess: ` +
        `uv run --directory ${manifest.worktree_path} ...）で実行する。\n` +
        `L1 = in-process import check: 下層関数を verification_activity_id で呼び、非null・型一致・値範囲・json.dumps 可能・exit 0 を確認。\n` +
        `L2 = L1 + **CI 同一ゲート**: \`uv run --directory ${manifest.worktree_path} bash scripts/ci-check.sh\` が exit 0 ` +
        `（whole-package の pytest -m "unit or integration" + black --check + mypy + doc-guard、web 変更時は web チェック）。` +
        `ci-check.sh は integration も既定で回すため、別途 integration を実行する必要はない（Issue #743）。` +
        `これにより doc-sync/unit 漏れ（README/CLAUDE のカウント、golden snapshot、count テスト等）を ci-guard 前に検出する。\n` +
        `完了条件: L1 OK かつ（L2 なら）ci-check.sh exit 0。結果を schema で返す（pass/fail/warning）。`,
      { label: `val:#${issue.number}`, phase: 'Validate', agentType: 'validation-agent', model: 'sonnet', schema: VALIDATION_SCHEMA }
    ).then((v) => ({ manifest, validation: v }))
  },

  // Stage 3 — Push, create PR, poll ci-guard to completion.
  (acc, issue) => {
    if (!acc) return null
    const m = acc.manifest
    return agent(
      `次の worktree ブランチを ship してください（merge はまだしない）。\n` +
        `worktree_path=${m.worktree_path}, branch=${m.branch}, issue=#${issue.number}。\n\n` +
        `1. ${pushCmd(m.worktree_path, m.branch)}（必要なら origin/main へ rebase してから。コンフリクト時は mergeable=false で報告）。\n` +
        `2. mcp__github__create_pull_request(${repoCtx()}, head="${m.branch}", base="main", title=コミット要約, body="Closes #${issue.number}\\nPart of the tier")。\n` +
        `3. mcp__github__pull_request_read(method="get_check_runs", ${repoCtx()}, pullNumber=PR番号) を ci-guard が completed になるまでポーリング（数回・間隔を空けて）。\n` +
        `4. ci-guard の conclusion を ci_conclusion に（success/failure/pending）。web-backend/web-frontend/lint-and-test の skipped は無視。\n` +
        `5. PR が main に対して mergeable か（コンフリクトなし）を mergeable に。\n` +
        `schema で {pr_number, pr_url, ci_conclusion, mergeable, head_sha} を返す。`,
      { label: `ship:#${issue.number}`, phase: 'Ship', model: 'sonnet', schema: SHIP_SCHEMA }
    ).then((ship) => ({ ...acc, ship }))
  },

  // Stage 4 — Auto-merge on green; otherwise escalate (no merge).
  (acc, issue) => {
    if (!acc) return null
    const decision = mergeDecision(acc)
    if (!decision.ok) return { issue: issue.number, ...acc, merge: { merged: false, reason: decision.reason } }
    return agent(
      `PR #${acc.ship.pr_number}（Issue #${issue.number}）を auto-merge してください。検証 PASS + ci-guard success + mergeable を確認済み。\n` +
        `mcp__github__merge_pull_request(${repoCtx()}, pullNumber=${acc.ship.pr_number}, merge_method="merge") を実行し、結果を schema で返す。\n` +
        `この tool が未ロードなら ToolSearch('select:mcp__github__merge_pull_request') で読み込んでから呼ぶこと。\n` +
        `禁止: sub-LLM の spawn / Anthropic API の直叩き / Bash 等での権限システム迂回。マージは必ず上記 MCP tool 経由で行う。`,
      { label: `merge:#${issue.number}`, phase: 'Merge', model: 'sonnet', effort: 'low', schema: MERGE_SCHEMA }
    ).then((mg) => ({ issue: issue.number, ...acc, merge: mergeResult(decision.reason, mg) }))
  }
)

// ── summary ───────────────────────────────────────────────────────────
const clean = results.filter(Boolean)
const merged = clean.filter((r) => r.merge?.merged)
const escalated = clean.filter((r) => !r.merge?.merged)
const dropped = ISSUES.filter((i) => !clean.some((r) => r.issue === i.number))

log(`Tier 完了: ${merged.length} auto-merged, ${escalated.length} escalated, ${dropped.length} dropped`)

return {
  tier: ARGS.tierName ?? null,
  merged: merged.map((r) => ({ issue: r.issue, pr: r.ship?.pr_number, sha: r.merge?.merge_sha })),
  escalated: escalated.map((r) => ({ issue: r.issue, pr: r.ship?.pr_number, reason: r.merge?.reason })),
  dropped: dropped.map((i) => i.number),
}
