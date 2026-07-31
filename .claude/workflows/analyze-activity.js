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
// prompt. The section agents never read files; the merge dir (built here by
// buildTempDir, not supplied by the agent) holds only {section}.json outputs.
//
// ── pure logic (side-effect-free; extracted & unit-tested in CI) ─────────
// The block between the markers below is evaluated by
// .claude/workflows/tests/analyze-activity.test.mjs (node --test, run by the
// CI meta-checks job). Keep it free of top-level side effects / workflow
// globals so the test can extract and exercise it directly.
// >>> testable
// Per-run cap on backfill days so a wide catch-up window can't fan out into an
// unbounded number of serial analyses. Overflow is reported (no silent caps).
const MAX_BACKFILL_DATES = 5

// The harness may deliver `args` as a JSON string, a bare date string, an
// object, or undefined. Normalize to { date: string | null, dates: string[] | null }.
// `dates` (backfill mode) takes precedence when a non-empty array is supplied.
function normalizeArgs(raw) {
  const fromObj = (o) => {
    if (Array.isArray(o.dates) && o.dates.length > 0) {
      return { date: null, dates: o.dates.map(String) }
    }
    return { date: o.date ?? null, dates: null }
  }
  if (typeof raw === 'string') {
    const s = raw.trim()
    if (!s) return { date: null, dates: null }
    try {
      const parsed = JSON.parse(s)
      if (parsed && typeof parsed === 'object') return fromObj(parsed)
      return { date: String(parsed), dates: null }
    } catch {
      return { date: s, dates: null } // bare date string like "2025-10-09"
    }
  }
  if (raw && typeof raw === 'object') return fromObj(raw)
  return { date: null, dates: null }
}

// Split a backfill date list into the days to run now (capped) and the count of
// deferred days. `remaining > 0` is surfaced via log so overflow is never silent.
function planBackfill(dates, cap = MAX_BACKFILL_DATES) {
  const toRun = dates.slice(0, cap)
  const remaining = Math.max(0, dates.length - cap)
  return { toRun, remaining }
}

// has_run gate: only run the analysis phases when the day had a running activity.
function shouldAnalyze(fetch) {
  return !!(fetch && fetch.has_run)
}

// The 5 section JSONs must all land in ONE directory or the merge sees an empty
// dir and drops the whole analysis. The fetch agent has returned an unexpanded
// shell expression (`/tmp/analysis_<id>_$(cat ... || true)`) and a literal
// "placeholder" for that path before (#871): Bash-using agents expanded it and
// Write-using agents did not, scattering the outputs across three directories.
// So the workflow — not the agent — builds the path; the agent only supplies a
// plain epoch suffix, and anything else fails fast BEFORE the expensive analysis.
const TEMP_SUFFIX_PATTERN = '^[0-9]{6,}$'

function buildTempDir(activityId, tempSuffix) {
  const id = String(activityId ?? '')
  if (!/^[0-9]+$/.test(id)) {
    throw new Error(`invalid activity_id for temp dir: ${JSON.stringify(activityId ?? null)}`)
  }
  const suffix = String(tempSuffix ?? '')
  if (!new RegExp(TEMP_SUFFIX_PATTERN).test(suffix)) {
    throw new Error(
      `invalid temp_suffix ${JSON.stringify(tempSuffix ?? null)}: expected the digits printed by ` +
        `\`date +%s\`, not a shell expression or placeholder`
    )
  }
  return `/tmp/analysis_${id}_${suffix}`
}

// All four unified sections (efficiency/phase/environment/summary) plus `split`
// run in ONE parallel barrier. summary derives cross-section consistency from the
// shared CONTEXT (not from sibling outputs), so it does not wait for the other
// sections — nothing here is serial.
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
    `3. ランがある場合のみ has_run=true。Bash で次の2コマンドを実行し、それぞれの出力を取得する:\n` +
    `   date +%s   # 10桁の epoch。出力された数字をそのまま temp_suffix に入れる\n` +
    `   uv run --directory packages/garmin-mcp-server python -m garmin_mcp.scripts.prefetch_activity_context <activity_id>\n` +
    `   - prefetch 出力が非空かつ "error" を含まないことを確認（含む/空なら fail として報告）。\n` +
    `4. schema で {activity_id, activity_date, has_run, temp_suffix, context_json, catch_up_summary} を返す。\n` +
    `   **context_json には手順3の prefetch 出力（1行 JSON 文字列）を「一字一句そのまま」格納すること**` +
    `（要約・整形・キー削除をしない。後段のセクション分析がこの実データのみを使う）。\n` +
    `   **temp_suffix には実際に実行した \`date +%s\` の出力（数字のみ）を格納すること**。` +
    `\`$(...)\` のような未展開シェル式や "placeholder" 等の仮値は禁止（数字以外はワークフローが拒否して中断する）。` +
    `出力先ディレクトリはワークフローが組み立てるため、mkdir は不要。`
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
    `分析結果を DuckDB に登録します。Bash で次を順に実行し、merge の JSON 出力をそのまま schema で返してください:\n` +
    `ls -1 ${ctx.tempDir}\n` +
    `uv run --directory packages/garmin-mcp-server python -m garmin_mcp.scripts.merge_section_analyses ${ctx.tempDir}\n` +
    `ls -1 の一覧に efficiency/phase/environment/summary/split の .json が揃っているか確認し、` +
    `欠けているセクション名（およびディレクトリ自体が無い場合はその旨）を errors に列挙してください。\n` +
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
    // digits only — the workflow builds the path from this (see buildTempDir).
    temp_suffix: { type: ['string', 'null'], pattern: TEMP_SUFFIX_PATTERN },
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

// Analyze a single day end-to-end (Fetch → Analyze → Finalize). Runs the same
// pipeline whether invoked once (single-date mode) or per day in a serial
// backfill loop. DuckDB is single-writer, so days must not overlap the merge.
async function runOneDay(date) {
  // ── Phase Fetch: ingest + prefetch CONTEXT once (returned inline) ──
  phase('Fetch')
  const fetched = await agent(fetchPrompt(date), {
    label: 'fetch',
    phase: 'Fetch',
    effort: 'low',
    // orchestration (MCP/bash calls + JSON echo), but context_json must be copied
    // verbatim ("一字一句そのまま") — haiku is unreliable at transcribing the large
    // prefetch JSON, so pin sonnet. Pins the model instead of inheriting the session's.
    model: 'sonnet',
    schema: FETCH_SCHEMA,
  })

  if (!shouldAnalyze(fetched)) {
    log(`ランニング activity なし（${date ?? 'today'}）。catch_up_ingest の差分取込のみ`)
    return { status: 'no_run', activity_date: fetched?.activity_date ?? date ?? null, catch_up_summary: fetched?.catch_up_summary ?? null }
  }

  // Path is derived here (not taken from the agent) so every section, the
  // proofreader and the merge all address the exact same directory (#871).
  const ctx = {
    tempDir: buildTempDir(fetched.activity_id, fetched.temp_suffix),
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
        // summary's cost is reasoning depth (4-axis eval, recs synthesis), not output
        // volume (~2KB). Cap its effort to cut that reasoning time (output/UX unchanged).
        ...(s === 'summary' ? { effort: 'medium' } : {}),
      })
    ),
    () => agent(buildSplitPrompt(ctx), { label: plan.extra, phase: 'Analyze', agentType: 'split-section-analyst' }),
  ])

  // ── Phase Finalize: proofread Japanese prose, then merge into DuckDB ──
  phase('Finalize')
  await agent(proofreadPrompt(ctx), { label: 'proofread', phase: 'Finalize', agentType: 'proofreader' })
  // pure orchestration (reads section JSONs, calls merge tool) — haiku suffices.
  const merge = await agent(mergePrompt(ctx), {
    label: 'merge',
    phase: 'Finalize',
    model: 'haiku',
    schema: MERGE_SCHEMA,
  })

  const succeeded = merge?.succeeded ?? []
  const failed = merge?.failed ?? []
  log(`merge 完了（${fetched.activity_date}）: ${succeeded.length} 登録 / ${failed.length} 失敗`)

  return {
    status: 'done',
    activity_id: fetched.activity_id,
    activity_date: fetched.activity_date,
    succeeded,
    failed,
    errors: merge?.errors ?? [],
  }
}

// ── Backfill mode: analyze a capped list of days serially (single writer) ──
if (ARGS.dates && ARGS.dates.length > 0) {
  const { toRun, remaining } = planBackfill(ARGS.dates)
  if (remaining > 0) {
    log(`backfill 上限 ${MAX_BACKFILL_DATES} 件を超過。今回は ${toRun.length} 件を分析、残り ${remaining} 件は次回以降`)
  }
  const results = []
  for (const d of toRun) {
    results.push(await runOneDay(d))
  }
  return { status: 'backfill_done', analyzed: results.length, remaining, results }
}

// ── Single-date mode (default) ──
return await runOneDay(ARGS.date)
