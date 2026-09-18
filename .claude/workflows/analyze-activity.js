export const meta = {
  name: 'analyze-activity',
  description:
    'Ingest one activity, prefetch the CONTEXT bundle + the deterministic run report, write the single coach-review section (run_note), proofread it, then merge into DuckDB',
  phases: [
    { title: 'Fetch', detail: 'catch-up ingest + ingest activity + prefetch CONTEXT and run report (returned inline)' },
    { title: 'Analyze', detail: 'run-note-analyst writes the one run_note section' },
    { title: 'Finalize', detail: 'proofread run_note.json, merge into DuckDB' },
  ],
}

// ── args ──────────────────────────────────────────────────────────────
// "YYYY-MM-DD" (bare string) | { date: "YYYY-MM-DD" } | undefined (=> today)
//
// CONTEXT handoff: workflow agentTypes only reliably receive their declared MCP
// tools + Write (built-in Read/Bash are NOT granted to the run-note analyst), so
// both inputs — the prefetch CONTEXT bundle and the deterministic run report —
// are fetched ONCE by the Fetch agent and passed INLINE into the analysis
// prompt. The analyst never reads files; the merge dir (built here by
// buildTempDir, not supplied by the agent) holds only run_note.json.
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
    `分析用 CONTEXT と決定論的ランレポートを取得して**返却値に格納**します。\n\n` +
    `1. mcp__garmin-db__catch_up_ingest(end_date=${date ? `"${date}"` : '省略（内部既定 today）'}) で ` +
    `ランニング・体重・補強の差分を取り込む。短い要約を catch_up_summary に（例「ラン1/体重0/補強0」「差分なし」）。\n` +
    `2. mcp__garmin-db__ingest_activity(date=${d}) で当日ランを取り込み、activity_id と activity_date を取得。\n` +
    `   - ランニング activity が無い（activity_id が返らない）→ has_run=false で即返す。\n` +
    `3. ランがある場合のみ has_run=true。Bash で次の3コマンドを実行し、それぞれの出力を取得する:\n` +
    `   date +%s   # 10桁の epoch。出力された数字をそのまま temp_suffix に入れる\n` +
    `   uv run --directory packages/garmin-mcp-server python -m garmin_mcp.scripts.prefetch_activity_context <activity_id>\n` +
    `   uv run --directory packages/garmin-mcp-server python -m garmin_mcp.scripts.prefetch_run_report <activity_id>\n` +
    `   - 2つの prefetch 出力がいずれも非空かつ "error" を含まないことを確認（含む/空なら fail として報告）。\n` +
    `4. schema で {activity_id, activity_date, has_run, temp_suffix, context_json, report_json, catch_up_summary} を返す。\n` +
    `   **context_json / report_json には手順3の各出力（1行 JSON 文字列）を「一字一句そのまま」格納すること**` +
    `（要約・整形・キー削除をしない。後段の分析がこの実データのみを使う）。\n` +
    `   **temp_suffix には実際に実行した \`date +%s\` の出力（数字のみ）を格納すること**。` +
    `\`$(...)\` のような未展開シェル式や "placeholder" 等の仮値は禁止（数字以外はワークフローが拒否して中断する）。` +
    `出力先ディレクトリはワークフローが組み立てるため、mkdir は不要。`
  )
}

// The run report carries the run itself (plan verdict, signals, scenes,
// conditions); what it does NOT carry is why the day was prescribed, how the
// athlete woke up and what the previous same-type run looked like. Only those
// keys are forwarded — the full bundle would double the prompt with numbers the
// page already renders (form baselines, zone percentages, star scores).
function buildRunNoteContext(contextJson) {
  let bundle
  try {
    bundle = JSON.parse(contextJson)
  } catch {
    return ''
  }
  if (bundle == null || typeof bundle !== 'object') return ''

  const p = bundle.prescription_for_run
  const similar = bundle.similar_workouts && bundle.similar_workouts.similar_activities
  return JSON.stringify({
    training_type: bundle.training_type ?? null,
    week_position: bundle.week_position ?? null,
    prescription_for_run: p
      ? {
          title: p.title ?? null,
          session_type: p.session_type ?? null,
          target_km: p.target_km ?? null,
          target_minutes: p.target_minutes ?? null,
          hr_low: p.hr_low ?? null,
          hr_high: p.hr_high ?? null,
          rationale: p.rationale ?? null,
        }
      : null,
    prescription_verdict: bundle.prescription_verdict ?? null,
    morning_wellness: bundle.morning_wellness ?? null,
    vs_previous: bundle.vs_previous ?? null,
    previous_same_type: bundle.previous_same_type ?? null,
    // Top 3 only: the comparison is context for one sentence, not a table.
    similar_workouts: Array.isArray(similar) ? similar.slice(0, 3) : null,
    gear: bundle.gear ?? null,
    long_run_gate: bundle.long_run_gate ?? null,
  })
}

function buildRunNotePrompt(ctx) {
  const contextSubset = buildRunNoteContext(ctx.contextJson)
  const contextBlock = contextSubset
    ? `補助 CONTEXT（処方・週内の位置・当日朝の回復・前回同種ラン・シューズ, JSON）:\n` +
      `<CONTEXT>\n${contextSubset}\n</CONTEXT>\n`
    : ''
  return (
    `Activity ID ${ctx.activityId} (${ctx.activityDate}) の **run_note**（コーチレビュー）セクションを作成してください。\n` +
    `決定論的ランレポート（REPORT, JSON）は以下です。数値・判定・シーンはすべてここから転記し、計算し直さないこと:\n` +
    `<REPORT>\n${ctx.reportJson}\n</REPORT>\n` +
    contextBlock +
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
    context_json: { type: ['string', 'null'] },
    report_json: { type: ['string', 'null'] },
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
  // ── Phase Fetch: ingest + prefetch CONTEXT and run report (inline) ──
  phase('Fetch')
  const fetched = await agent(fetchPrompt(date), {
    label: 'fetch',
    phase: 'Fetch',
    effort: 'low',
    // orchestration (MCP/bash calls + JSON echo), but context_json / report_json
    // must be copied verbatim ("一字一句そのまま") — haiku is unreliable at
    // transcribing the large prefetch JSON, so pin sonnet. Pins the model
    // instead of inheriting the session's.
    model: 'sonnet',
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
    contextJson: fetched.context_json,
    reportJson: fetched.report_json,
    activityId: fetched.activity_id,
    activityDate: fetched.activity_date,
  }
  if (!ctx.reportJson || !String(ctx.reportJson).trim()) {
    // Without the report there is nothing to ground the review against, and the
    // merge gate would reject it after the expensive analysis. Stop here.
    throw new Error('fetch returned no report_json (prefetch_run_report failed)')
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
