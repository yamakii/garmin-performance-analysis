export const meta = {
  name: 'analyze-activity',
  description:
    'Ingest one activity, write the single coach-review section (run_note) from the deterministic run report + CONTEXT, proofread it, then merge into DuckDB',
  phases: [
    { title: 'Fetch', detail: 'catch-up ingest + ingest activity' },
    { title: 'Analyze', detail: 'run-note-analyst reads get_run_note_inputs and writes the one run_note section' },
    { title: 'Finalize', detail: 'proofread run_note.json, merge into DuckDB' },
  ],
}

// ── args ──────────────────────────────────────────────────────────────
// "YYYY-MM-DD" (bare string) | { date: "YYYY-MM-DD" } | undefined (=> today)
//
// Input handoff: workflow agentTypes only reliably receive their declared MCP
// tools + Write (built-in Read/Bash are NOT granted to the run-note analyst), so
// the analyst fetches both inputs — the deterministic run report and the coach
// subset of the CONTEXT bundle — itself, in ONE declared MCP call
// (get_run_note_inputs). The Fetch agent used to prefetch them and re-type both
// JSON payloads into its structured output, which was ~40 s of every run
// (#1362); now it only ingests. The analyst never reads files; the merge dir
// (built here by buildTempDir, not supplied by the agent) holds only
// run_note.json.
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

// The section JSON must land in the SAME directory the merge reads, or the merge
// sees an empty dir and drops the whole analysis. The fetch agent has returned an
// unexpanded shell expression (`/tmp/analysis_<id>_$(cat ... || true)`) and a
// literal "placeholder" for that path before (#871): Bash-using agents expanded
// it and Write-using agents did not, scattering the outputs across directories.
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

// One analysis task (Epic #1247): everything a number can decide is rendered
// deterministically by the run report, so the only LLM-written section left is
// the coach review. The plan stays a list so the Analyze phase keeps its shape.
function sectionPlan() {
  return ['run_note']
}

function fetchPrompt(date) {
  const d = date ? `"${date}"` : 'today（実行日の YYYY-MM-DD）'
  return (
    `あなたは分析パイプラインの fetch ステージです。対象日 ${date ?? 'today'} のランニング activity を取り込み、` +
    `その activity_id を返します（ランレポートと CONTEXT は後段の分析エージェントが自分で取得するので、ここでは取得しない）。\n\n` +
    `1. mcp__garmin-db__catch_up_ingest(end_date=${date ? `"${date}"` : '省略（内部既定 today）'}) で ` +
    `ランニング・体重・補強の差分を取り込む。短い要約を catch_up_summary に（例「ラン1/体重0/補強0」「差分なし」）。\n` +
    `2. mcp__garmin-db__ingest_activity(date=${d}) で当日ランを取り込み、activity_id と activity_date を取得。\n` +
    `   - ランニング activity が無い（activity_id が返らない）→ has_run=false で即返す。\n` +
    `3. ランがある場合のみ has_run=true。Bash で \`date +%s\` を実行する（10桁の epoch）。\n` +
    `4. schema で {activity_id, activity_date, has_run, temp_suffix, catch_up_summary} を返す。\n` +
    `   **temp_suffix には実際に実行した \`date +%s\` の出力（数字のみ）を格納すること**。` +
    `\`$(...)\` のような未展開シェル式や "placeholder" 等の仮値は禁止（数字以外はワークフローが拒否して中断する）。` +
    `出力先ディレクトリはワークフローが組み立てるため、mkdir は不要。`
  )
}

// The analyst's inputs come from one MCP call it makes itself: the report
// carries the run (plan verdict, signals, scenes, conditions) and the context
// carries why the day was prescribed, how the athlete woke up and the previous
// same-type run. The coach subset is cut in Python (build_run_note_context).
function buildRunNotePrompt(ctx) {
  return (
    `Activity ID ${ctx.activityId} (${ctx.activityDate}) の **run_note**（コーチレビュー）セクションを作成してください。\n` +
    `最初に mcp__garmin-db__get_run_note_inputs(activity_id=${ctx.activityId}) を1回だけ呼び、` +
    `返り値の report を REPORT、context を CONTEXT（処方・週内の位置・当日朝の回復・前回同種ラン・シューズ）として使うこと。` +
    `数値・判定・シーンはすべて REPORT から転記し、計算し直さないこと。` +
    `返り値に error があるときは JSON を書かずにその error を報告して終了すること。\n` +
    `evidence キー・moment_id・signal 名は REPORT に実在するものだけを使うこと` +
    `（merge 時の grounding ゲートが解決できないキーを拒否します）。\n` +
    `ONLY run_note: run_note.json だけを生成・validate・保存し、他セクションは一切生成しないこと。\n` +
    `保存先: ${ctx.tempDir}/run_note.json`
  )
}

function proofreadPrompt(ctx) {
  return (
    `${ctx.tempDir}/run_note.json の日本語散文フィールドを校正してください。` +
    `崩れ（誤字・誤変換・活用崩れ）のみを Edit で最小修正し、数値・キー・構造・意味、` +
    `および evidence / moment_id / signal の値は変えないでください。`
  )
}

function mergePrompt(ctx) {
  return (
    `分析結果を DuckDB に登録します。Bash で次を順に実行し、merge の JSON 出力をそのまま schema で返してください:\n` +
    `ls -1 ${ctx.tempDir}\n` +
    `uv run --directory packages/garmin-mcp-server python -m garmin_mcp.scripts.merge_section_analyses ${ctx.tempDir}\n` +
    `ls -1 の一覧に run_note.json があるか確認し、無い場合（およびディレクトリ自体が無い場合）はその旨を errors に列挙してください。\n` +
    `出力は {succeeded:[...], failed:[...], errors:[...]} 形式。failed が空なら temp は自動削除されます。`
  )
}

// Fold the merge output into the workflow's return value. run_note either lands
// or it does not: there is no partial-success mode left to report (#1253).
function summarizeRun(fetched, merge) {
  return {
    status: 'done',
    activity_id: fetched?.activity_id ?? null,
    activity_date: fetched?.activity_date ?? null,
    succeeded: merge?.succeeded ?? [],
    failed: merge?.failed ?? [],
    errors: merge?.errors ?? [],
  }
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
  // ── Phase Fetch: ingest only; the analyst fetches its own inputs ──
  phase('Fetch')
  const fetched = await agent(fetchPrompt(date), {
    label: 'fetch',
    phase: 'Fetch',
    effort: 'low',
    // pure orchestration (two MCP calls + `date +%s`, a few short fields back):
    // nothing large is transcribed any more (#1362), so haiku suffices.
    model: 'haiku',
    schema: FETCH_SCHEMA,
  })

  if (!shouldAnalyze(fetched)) {
    log(`ランニング activity なし（${date ?? 'today'}）。catch_up_ingest の差分取込のみ`)
    return { status: 'no_run', activity_date: fetched?.activity_date ?? date ?? null, catch_up_summary: fetched?.catch_up_summary ?? null }
  }

  // Path is derived here (not taken from the agent) so the analyst, the
  // proofreader and the merge all address the exact same directory (#871).
  const ctx = {
    tempDir: buildTempDir(fetched.activity_id, fetched.temp_suffix),
    activityId: fetched.activity_id,
    activityDate: fetched.activity_date,
  }
  const plan = sectionPlan()

  // ── Phase Analyze: the one coach-review section ──
  phase('Analyze')
  await agent(buildRunNotePrompt(ctx), {
    label: plan[0],
    phase: 'Analyze',
    agentType: 'run-note-analyst',
  })

  // ── Phase Finalize: proofread Japanese prose, then merge into DuckDB ──
  phase('Finalize')
  await agent(proofreadPrompt(ctx), { label: 'proofread', phase: 'Finalize', agentType: 'proofreader' })
  // pure orchestration (runs the merge script, echoes its JSON) — haiku suffices.
  const merge = await agent(mergePrompt(ctx), {
    label: 'merge',
    phase: 'Finalize',
    model: 'haiku',
    schema: MERGE_SCHEMA,
  })

  const result = summarizeRun(fetched, merge)
  log(`merge 完了（${result.activity_date}）: ${result.succeeded.length} 登録 / ${result.failed.length} 失敗`)
  return result
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
