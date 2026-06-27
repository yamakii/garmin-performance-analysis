export const meta = {
  name: 'analyze-activity',
  description:
    'Ingest one activity, prefetch context once, analyze 5 sections in parallel (CONTEXT passed inline), proofread, then merge into DuckDB',
  phases: [
    { title: 'Fetch', detail: 'catch-up ingest + ingest activity + prefetch CONTEXT (returned inline)' },
    { title: 'Analyze', detail: 'efficiency/phase/environment/split in parallel, then summary (siblings inline)' },
    { title: 'Finalize', detail: 'proofread JSON, merge into DuckDB' },
  ],
}

// ── args ──────────────────────────────────────────────────────────────
// "YYYY-MM-DD" (bare string) | { date: "YYYY-MM-DD" } | undefined (=> today)
//
// CONTEXT handoff: workflow agentTypes only reliably receive their declared MCP
// tools + Write (built-in Read/Bash are NOT granted to the unified analyst), so
// CONTEXT is fetched ONCE by the Fetch agent and passed INLINE into each section
// prompt. The section agents never read files; the merge dir (temp_dir) holds
// only {section}.json outputs.
//
// ── pure logic (side-effect-free; extracted & unit-tested in CI) ─────────
// The block between the markers below is evaluated by
// .claude/workflows/tests/analyze-activity.test.mjs (node --test, run by the
// CI meta-checks job). Keep it free of top-level side effects / workflow
// globals so the test can extract and exercise it directly.
// >>> testable
// The harness may deliver `args` as a JSON string, a bare date string, an
// object, or undefined. Normalize to { date: string | null }.
function normalizeArgs(raw) {
  if (typeof raw === 'string') {
    const s = raw.trim()
    if (!s) return { date: null }
    try {
      const parsed = JSON.parse(s)
      if (parsed && typeof parsed === 'object') return { date: parsed.date ?? null }
      return { date: String(parsed) }
    } catch {
      return { date: s } // bare date string like "2025-10-09"
    }
  }
  if (raw && typeof raw === 'object') return { date: raw.date ?? null }
  return { date: null }
}

// has_run gate: only run the analysis phases when the day had a running activity.
function shouldAnalyze(fetch) {
  return !!(fetch && fetch.has_run)
}

// The 4 unified sections split into an independent group (run in parallel) and
// one dependent section (summary, needs the other three for cross-section
// consistency, derived from the shared CONTEXT). All four unified sections plus
// `split` run in ONE parallel barrier — summary no longer waits for siblings, so
// the previously-serial summary (the long pole) is hidden behind the barrier.
function sectionPlan() {
  return {
    unified: ['efficiency', 'phase', 'environment', 'summary'],
    extra: 'split',
  }
}

function fetchPrompt(date) {
  const d = date ? `"${date}"` : 'today（実行日の YYYY-MM-DD）'
  return (
    `あなたは分析パイプラインの fetch ステージです。対象日 ${date ?? 'today'} のランニング activity を取り込み、` +
    `分析用 CONTEXT を取得して**返却値 context_json に格納**します。\n\n` +
    `1. mcp__garmin-db__catch_up_ingest(end_date=${date ? `"${date}"` : '省略（内部既定 today）'}) で ` +
    `ランニング・体重・補強の差分を取り込む。短い要約を catch_up_summary に（例「ラン1/体重0/補強0」「差分なし」）。\n` +
    `2. mcp__garmin-db__ingest_activity(date=${d}) で当日ランを取り込み、activity_id と activity_date を取得。\n` +
    `   - ランニング activity が無い（activity_id が返らない）→ has_run=false で即返す。\n` +
    `3. ランがある場合のみ has_run=true。Bash で次を実行し、出力（1行 JSON）を取得する:\n` +
    `   TS=$(date +%s); TD=/tmp/analysis_<activity_id>_$TS; mkdir -p "$TD"   # セクション JSON の出力先\n` +
    `   uv run --directory packages/garmin-mcp-server python -m garmin_mcp.scripts.prefetch_activity_context <activity_id>\n` +
    `   - 出力が非空かつ "error" を含まないことを確認（含む/空なら fail として報告）。\n` +
    `4. schema で {activity_id, activity_date, has_run, temp_dir, context_json, catch_up_summary} を返す。\n` +
    `   **context_json には手順3の prefetch 出力（1行 JSON 文字列）を「一字一句そのまま」格納すること**` +
    `（要約・整形・キー削除をしない。後段のセクション分析がこの実データのみを使う）。temp_dir=$TD。`
  )
}

function buildSectionPrompt(section, ctx) {
  return (
    `Activity ID ${ctx.activityId} (${ctx.activityDate}) の **${section}** セクションのみを分析してください。\n` +
    `CONTEXT（prefetch バンドル, JSON）は以下です。この実データのみに基づき、推定値・fixture 値で代替しないこと:\n` +
    `<CONTEXT>\n${ctx.contextJson}\n</CONTEXT>\n` +
    `ONLY ${section}: ${section}.json だけを生成・validate・保存し、他セクションは一切生成しないこと。\n` +
    `保存先: ${ctx.tempDir}/${section}.json`
  )
}

function buildSummaryPrompt(ctx) {
  return (
    `Activity ID ${ctx.activityId} (${ctx.activityDate}) の **summary** セクションのみを分析してください。\n` +
    `CONTEXT（prefetch バンドル, JSON）は以下です。この実データのみに基づき、推定値・fixture 値で代替しないこと:\n` +
    `<CONTEXT>\n${ctx.contextJson}\n</CONTEXT>\n` +
    `summary は他セクションと並列生成されるため兄弟JSONは渡されません。整合は CONTEXT から取ること:` +
    `HR/ゾーン評価は CONTEXT の zone_distribution_rating / form_evaluation を権威的ソースとし、` +
    `それと矛盾する評価（強度不足・過負荷等）を独自に作らないこと。\n` +
    `ONLY summary: summary.json だけを生成・validate・保存すること。\n` +
    `保存先: ${ctx.tempDir}/summary.json`
  )
}

function buildSplitPrompt(ctx) {
  return (
    `Activity ID ${ctx.activityId} (${ctx.activityDate}) の全スプリットを詳細分析してください。\n` +
    `結果は ${ctx.tempDir}/split.json に保存してください。`
  )
}

function proofreadPrompt(ctx) {
  return (
    `${ctx.tempDir} 配下の *.json の日本語散文フィールドを校正してください。` +
    `崩れ（誤字・誤変換・活用崩れ）のみを Edit で最小修正し、数値・★・キー・構造・意味は変えないでください。`
  )
}

function mergePrompt(ctx) {
  return (
    `分析結果を DuckDB に登録します。Bash で次を実行し、その JSON 出力をそのまま schema で返してください:\n` +
    `uv run --directory packages/garmin-mcp-server python -m garmin_mcp.scripts.merge_section_analyses ${ctx.tempDir}\n` +
    `出力は {succeeded:[...], failed:[...], errors:[...]} 形式。failed が空なら temp は自動削除されます。`
  )
}

// <<< testable

const ARGS = normalizeArgs(args)

// ── schemas ───────────────────────────────────────────────────────────
const FETCH_SCHEMA = {
  type: 'object',
  required: ['has_run'],
  properties: {
    activity_id: { type: ['integer', 'null'] },
    activity_date: { type: ['string', 'null'] },
    has_run: { type: 'boolean' },
    temp_dir: { type: ['string', 'null'] },
    context_json: { type: ['string', 'null'] },
    catch_up_summary: { type: 'string' },
  },
}

const MERGE_SCHEMA = {
  type: 'object',
  required: ['succeeded', 'failed'],
  properties: {
    succeeded: { type: 'array', items: { type: 'string' } },
    failed: { type: 'array', items: { type: 'string' } },
    errors: { type: 'array', items: { type: 'string' } },
  },
}

// ── Phase Fetch: ingest + prefetch CONTEXT once (returned inline) ──
phase('Fetch')
const fetched = await agent(fetchPrompt(ARGS.date), {
  label: 'fetch',
  phase: 'Fetch',
  effort: 'low',
  schema: FETCH_SCHEMA,
})

if (!shouldAnalyze(fetched)) {
  log('ランニング activity なし。catch_up_ingest の差分取込のみで終了')
  return { status: 'no_run', catch_up_summary: fetched?.catch_up_summary ?? null }
}

const ctx = {
  tempDir: fetched.temp_dir,
  contextJson: fetched.context_json,
  activityId: fetched.activity_id,
  activityDate: fetched.activity_date,
}
const plan = sectionPlan()

// ── Phase Analyze: all 4 unified sections + split in ONE parallel barrier ──
// summary uses CONTEXT-only consistency (no sibling JSONs), so it no longer
// runs serially after the others — wall-clock collapses to the slowest section.
phase('Analyze')
await parallel([
  ...plan.unified.map((s) => () =>
    agent(s === 'summary' ? buildSummaryPrompt(ctx) : buildSectionPrompt(s, ctx), {
      label: s,
      phase: 'Analyze',
      // summary uses a focused, leaner agent (just summary rules) instead of
      // loading the full unified def; efficiency/phase/environment stay on unified.
      agentType: s === 'summary' ? 'summary-section-analyst' : 'unified-section-analyst',
    })
  ),
  () => agent(buildSplitPrompt(ctx), { label: plan.extra, phase: 'Analyze', agentType: 'split-section-analyst' }),
])

// ── Phase Finalize: proofread Japanese prose, then merge into DuckDB ──
phase('Finalize')
await agent(proofreadPrompt(ctx), { label: 'proofread', phase: 'Finalize', agentType: 'proofreader' })
const merge = await agent(mergePrompt(ctx), { label: 'merge', phase: 'Finalize', schema: MERGE_SCHEMA })

const succeeded = merge?.succeeded ?? []
const failed = merge?.failed ?? []
log(`merge 完了: ${succeeded.length} 登録 / ${failed.length} 失敗`)

return {
  status: 'done',
  activity_id: fetched.activity_id,
  activity_date: fetched.activity_date,
  succeeded,
  failed,
  errors: merge?.errors ?? [],
}
