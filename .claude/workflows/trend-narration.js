export const meta = {
  name: 'trend-narration',
  description:
    'Prefetch a period-keyed longitudinal trend CONTEXT, generate coach narration (inline sonnet), proofread, and save into trend_analyses',
  phases: [
    { title: 'Fetch', detail: 'prefetch_trend_context for the period (returned inline)' },
    { title: 'Analyze', detail: 'inline sonnet narration → trend.json' },
    { title: 'Finalize', detail: 'proofread prose, save into trend_analyses' },
  ],
}

// ── args ──────────────────────────────────────────────────────────────
// { period_start, period_end, granularity?, user_id? } (object or JSON string).
// granularity defaults to 'week'. Invoked by cron (after scheduled_sync detects
// a pending period via find_pending_trend_period) or manually for backfill.
//
// CONTEXT handoff mirrors analyze-activity: the deterministic layer
// (prefetch_trend_context, #790) is fetched ONCE by the Fetch agent and passed
// INLINE into the narration prompt. All accuracy-sensitive values (deltas, trend
// direction, fusion flags, headline_metrics) are precomputed in the CONTEXT — the
// LLM only writes prose, so no fabricated "load is up 12%" verdicts (#714 ADR §4).
//
// ── pure logic (side-effect-free; extracted & unit-tested in CI) ─────────
// The block between the markers is evaluated by
// .claude/workflows/tests/trend-narration.test.mjs (node --test, meta-checks job).
// Keep it free of top-level side effects / workflow globals.
// >>> testable
// Normalize the harness arg (object | JSON string | undefined) to a stable shape.
// granularity is clamped to 'week' | 'month' ('week' default); user_id defaults.
function normalizeTrendArgs(raw) {
  const base = { period_start: null, period_end: null, granularity: 'week', user_id: 'default' }
  const fromObj = (o) => ({
    period_start: o.period_start ?? null,
    period_end: o.period_end ?? null,
    granularity: o.granularity === 'month' ? 'month' : 'week',
    user_id: o.user_id ?? 'default',
  })
  if (typeof raw === 'string') {
    const s = raw.trim()
    if (!s) return base
    try {
      const parsed = JSON.parse(s)
      if (parsed && typeof parsed === 'object') return fromObj(parsed)
    } catch {
      return base
    }
    return base
  }
  if (raw && typeof raw === 'object') return fromObj(raw)
  return base
}

function fetchTrendPrompt(a) {
  return (
    `あなたはトレンド分析パイプラインの fetch ステージです。期間 ${a.period_start} 〜 ${a.period_end}` +
    `（granularity=${a.granularity}）の縦断トレンド CONTEXT を取得し、**返却値 context_json に格納**します。\n\n` +
    `1. Bash で次を実行し、出力（1行 JSON）を取得する:\n` +
    `   TS=$(date +%s); TD=/tmp/trend_${a.granularity}_${a.period_start}_$TS; mkdir -p "$TD"   # trend.json の出力先\n` +
    `   uv run --directory packages/garmin-mcp-server python -m garmin_mcp.scripts.prefetch_trend_context ` +
    `--period-start ${a.period_start} --period-end ${a.period_end} --granularity ${a.granularity}\n` +
    `   - 出力が非空かつ "error" を含まないことを確認（含む/空なら fail として報告）。\n` +
    `2. schema で {period_start, period_end, granularity, temp_dir, context_json} を返す。\n` +
    `   **context_json には手順1の prefetch 出力（1行 JSON 文字列）を「一字一句そのまま」格納すること**` +
    `（要約・整形・キー削除をしない。後段のナレーションがこの実データのみを使う）。temp_dir=$TD。`
  )
}

function narrationPrompt(ctx) {
  return (
    `期間 ${ctx.periodStart} 〜 ${ctx.periodEnd}（${ctx.granularity}）の縦断トレンドを、ランニングコーチとして解説してください。\n` +
    `CONTEXT（prefetch バンドル, JSON）は以下です。トレンド値・回帰・融合フラグ・headline_metrics は全て決定的に計算済みです。` +
    `この実データのみに基づき、値の再計算・捏造をしないこと:\n` +
    `<CONTEXT>\n${ctx.contextJson}\n</CONTEXT>\n` +
    `散文フィールドのみを書く: narrative（なぜトレンドが動いているか・シグナル相互関係）, ` +
    `key_learnings（配列）, recommendations（最大2件、具体的な次アクション）。\n` +
    `【小Nガード（統計的誠実性, #813）】status="insufficient_data" もしくは data_points < 3 の成分は、` +
    `トレンドとして語らないこと。検出力不足の "stable" は「安定」ではなく「判定不能（検出力不足）」と表現する。\n` +
    `週次の metric_trends は mode="descriptive"（回帰ではなく median と前週比 delta_pct）。回帰・傾き・p値を語らず、` +
    `「今週の median を前週と比べた記述」として扱うこと。\n` +
    `週次の durability_trend / heat_adjusted_trend はトレーリング窓（8週 / 12週）で当てたトレンドで、` +
    `in_period_activity_ids が今週の該当ラン。今週の値をそのトレーリングトレンド上に位置づけて語り、週内で回帰を主張しないこと。\n` +
    `【durability の優劣判断（#823）】どのロングランが最も「粘れた」かは decoupling（心拍ドリフト, 低いほど良, ` +
    `ペーシング戦略に依存しない）で判断し、durability_trend の best_run / worst_run（決定的に算出済み）を転記すること。` +
    `生の符号付き値から自分で優劣を導出しない（0 に近い＝良い、ではない）。\n` +
    `pace_fade は遂行の記述（負＝後半が速い/ネガティブスプリット）であって優劣軸ではない。大きな負値を無条件に「良い」「粘れた」と表現しない。` +
    `理想かどうかは training_type の意図（steady aerobic か progression/fast-finish か）と併記し、意図が不明なら断定しないこと。\n` +
    `fitness_curve は 90 日窓の指標で、今週はその曲線上の現在位置として扱うこと（1週で崩壊/急伸したと解釈しない）。\n` +
    `headline_metrics / fusion_flags は CONTEXT の値をそのまま analysis_data に転記し、それと矛盾する主張をしないこと。\n` +
    `出力 JSON 構造:\n` +
    `{"granularity":"${ctx.granularity}","period_start":"${ctx.periodStart}","period_end":"${ctx.periodEnd}",` +
    `"analysis_data":{"narrative":"...","key_learnings":[...],"recommendations":[...],` +
    `"headline_metrics":{...転記...},"fusion_flags":{...転記...}}}\n` +
    `これを ${ctx.tempDir}/trend.json に保存すること（他のファイルは作らない）。`
  )
}

function proofreadTrendPrompt(ctx) {
  return (
    `${ctx.tempDir}/trend.json の日本語散文フィールド（narrative / key_learnings / recommendations）を校正してください。` +
    `崩れ（誤字・誤変換・活用崩れ）のみを Edit で最小修正し、数値・キー・構造・意味は変えないでください。`
  )
}

function mergeTrendPrompt(ctx) {
  return (
    `トレンド解説を DuckDB の trend_analyses に登録します。Bash で次を実行し、その JSON 出力をそのまま schema で返してください:\n` +
    `uv run --directory packages/garmin-mcp-server python -m garmin_mcp.scripts.save_trend_narration ${ctx.tempDir}\n` +
    `出力は {saved:bool, granularity, period_start} 形式。saved=false や例外は失敗として報告すること。`
  )
}

// <<< testable

const A = normalizeTrendArgs(args)

// ── schemas ───────────────────────────────────────────────────────────
const FETCH_SCHEMA = {
  type: 'object',
  required: ['temp_dir', 'context_json'],
  properties: {
    period_start: { type: ['string', 'null'] },
    period_end: { type: ['string', 'null'] },
    granularity: { type: ['string', 'null'] },
    temp_dir: { type: 'string' },
    context_json: { type: 'string' },
  },
}

const SAVE_SCHEMA = {
  type: 'object',
  required: ['saved'],
  properties: {
    saved: { type: 'boolean' },
    granularity: { type: ['string', 'null'] },
    period_start: { type: ['string', 'null'] },
  },
}

// ── Phase Fetch: prefetch the period CONTEXT once (returned inline) ──
phase('Fetch')
const fetched = await agent(fetchTrendPrompt(A), {
  label: 'fetch',
  phase: 'Fetch',
  // orchestration (bash + JSON echo), but context_json must be copied verbatim
  // ("一字一句そのまま") — pin sonnet for reliable transcription of the large bundle.
  model: 'sonnet',
  schema: FETCH_SCHEMA,
})

const ctx = {
  tempDir: fetched.temp_dir,
  contextJson: fetched.context_json,
  periodStart: A.period_start,
  periodEnd: A.period_end,
  granularity: A.granularity,
}

// ── Phase Analyze: inline sonnet coach narration → trend.json ──
phase('Analyze')
await agent(narrationPrompt(ctx), {
  label: 'trend-narration',
  phase: 'Analyze',
  // narration is the analytical core (why the trend moves, signal interplay) —
  // sonnet, per the #792 decision to keep this inline (L2) rather than a new agent def.
  model: 'sonnet',
})

// ── Phase Finalize: proofread prose, then save into trend_analyses ──
phase('Finalize')
await agent(proofreadTrendPrompt(ctx), { label: 'proofread', phase: 'Finalize', agentType: 'proofreader' })
// pure orchestration (reads trend.json, calls save tool) — haiku suffices.
const saved = await agent(mergeTrendPrompt(ctx), {
  label: 'save',
  phase: 'Finalize',
  model: 'haiku',
  schema: SAVE_SCHEMA,
})

log(`trend-narration 保存（${A.granularity} ${A.period_start}〜${A.period_end}）: saved=${saved?.saved}`)

return {
  status: saved?.saved ? 'done' : 'failed',
  granularity: A.granularity,
  period_start: A.period_start,
  period_end: A.period_end,
  saved: saved?.saved ?? false,
}
