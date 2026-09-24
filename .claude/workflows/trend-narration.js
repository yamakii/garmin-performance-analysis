export const meta = {
  name: 'trend-narration',
  description:
    'Prefetch a period-keyed longitudinal trend CONTEXT, generate coach narration (inline sonnet), proofread, and save into trend_analyses',
  phases: [
    { title: 'Analyze', detail: 'inline sonnet: prefetch CONTEXT to a file, narrate → trend.json' },
    { title: 'Finalize', detail: 'proofread prose, save into trend_analyses' },
  ],
}

// ── args ──────────────────────────────────────────────────────────────
// { period_start, period_end, granularity?, user_id? } (object or JSON string).
// granularity defaults to 'week'. Invoked by cron (after scheduled_sync detects
// a pending period via find_pending_trend_period) or manually for backfill.
//
// CONTEXT handoff is FILE-BASED (#1023): the deterministic layer
// (prefetch_trend_context, #790) is ~60KB (fitness_curve alone is ~43KB), so the
// narration agent redirects it into <temp_dir>/context.json with one Bash
// command and Reads it from there; the bundle never passes through a model's
// output. The temp dir is built here from the period (buildTrendTempDir), so no
// agent is needed just to create it. All accuracy-sensitive values (deltas,
// trend direction, fusion flags, headline_metrics incl. the deload prescription)
// are precomputed in the CONTEXT — the LLM only writes prose, so no fabricated
// "load is up 12%" verdicts (#714 ADR §4).
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

// The period dates go into a shell command, so only plain ISO dates are accepted.
const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

// Deterministic temp dir for one period (resume-safe: a re-run reuses the path
// and overwrites context.json / trend.json). Throws on anything that is not a
// plain ISO date or a known granularity, so an unexpanded shell expression or a
// missing arg fails before any agent runs.
function buildTrendTempDir(a) {
  for (const key of ['period_start', 'period_end']) {
    const v = a?.[key]
    if (typeof v !== 'string' || !ISO_DATE_PATTERN.test(v))
      throw new Error(`invalid ${key} ${JSON.stringify(v ?? null)}: expected YYYY-MM-DD`)
  }
  if (a.granularity !== 'week' && a.granularity !== 'month')
    throw new Error(`invalid granularity ${JSON.stringify(a.granularity ?? null)}: expected week | month`)
  return `/tmp/trend_${a.granularity}_${a.period_start}`
}

function narrationPrompt(ctx) {
  return (
    `期間 ${ctx.periodStart} 〜 ${ctx.periodEnd}（${ctx.granularity}）の縦断トレンドを、ランニングコーチとして解説してください。\n` +
    `**最初に Bash で CONTEXT をファイルへ書き出す**（数十 KB になるので、出力を自分で読み上げたり転記したりしない）:\n` +
    `   TD=${ctx.tempDir}; mkdir -p "$TD" && rm -f "$TD/trend.json" && ` +
    `uv run --directory packages/garmin-mcp-server python -m garmin_mcp.scripts.prefetch_trend_context ` +
    `--period-start ${ctx.periodStart} --period-end ${ctx.periodEnd} --granularity ${ctx.granularity} > "$TD/context.json"\n` +
    `**続けて Read で ${ctx.tempDir}/context.json を読むこと**。空・JSON でない・"error" キーを含むときは、` +
    `trend.json を書かずにそのエラーを報告して終了する。\n` +
    `これが CONTEXT（prefetch バンドル, JSON）で、` +
    `トレンド値・回帰・融合フラグ・headline_metrics は全て決定的に計算済みです。` +
    `この実データのみに基づき、値の再計算・捏造をしないこと。CONTEXT の全文を出力へ書き写す必要はありません:\n` +
    `散文フィールドのみを書く: narrative（なぜトレンドが動いているか・シグナル相互関係）, ` +
    `key_learnings（配列）, recommendations（最大2件、具体的な次アクション）。\n` +
    `CONTEXT はすべての判定（direction、best/worst_run、band、caveat、cutback フラグ、insufficient_data）を決定的に持つ。` +
    `散文はそれを転記・解釈し、再導出しない。\n` +
    `【小Nガード（統計的誠実性）】status="insufficient_data" もしくは data_points < 3 の成分は、` +
    `トレンドとして語らないこと。検出力不足の "stable" は「安定」ではなく「判定不能（検出力不足）」と表現する。\n` +
    `週次の metric_trends は mode="descriptive"（回帰ではなく median と前週比 delta_pct）。回帰・傾き・p値を語らず、` +
    `「今週の median を前週と比べた記述」として扱うこと。\n` +
    `週次の durability_trend / heat_adjusted_trend はトレーリング窓（8週 / 12週）で当てたトレンドで、` +
    `in_period_activity_ids が今週の該当ラン。今週の値をそのトレーリングトレンド上に位置づけて語り、週内で回帰を主張しないこと。\n` +
    `【durability の優劣判断】どのロングランが最も「粘れた」かは decoupling（心拍ドリフト, 低いほど良, ` +
    `ペーシング戦略に依存しない）で判断し、durability_trend の best_run / worst_run（決定的に算出済み）を転記すること。` +
    `生の符号付き値から自分で優劣を導出しない（0 に近い＝良い、ではない）。\n` +
    `pace_fade は遂行の記述（負＝後半が速い/ネガティブスプリット）であって優劣軸ではない。大きな負値を無条件に「良い」「粘れた」と表現しない。` +
    `理想かどうかは training_type の意図（steady aerobic か progression/fast-finish か）と併記し、意図が不明なら断定しないこと。\n` +
    `【durability の傾き判定は絶対水準・頑健性と併せて語る】durability_trend.trend には ` +
    `absolute_assessment（band=strong/moderate/poor, all_within_strong_band, recent_decoupling_pct）と ` +
    `fragile / direction_caveat が決定的に付与されている。direction は傾き（slope）の記述にすぎず、それ単独で` +
    `「粘りが落ちた」と断じないこと。次のように扱う:\n` +
    `  ・direction="worsening" でも all_within_strong_band=true なら「絶対的な粘りは優秀レンジ（decoupling<5%）を維持」と明記する。\n` +
    `  ・direction_caveat が非null なら、その内容（頑健性・レバレッジ点・絶対水準）を散文に反映して緩衝する。\n` +
    `  ・fragile=true の direction は「単一点のレバレッジに依存し統計的に頑健でない（例外的に良い初回ロング走がアンカーになっている等）」ものとして扱い、` +
    `absolute_assessment.band が poor でない限り、worsening を根拠にロング走の距離制限・ペース抑制などの強い介入を推奨しないこと。\n` +
    `【カットバック判定】headline_metrics.cutback_due_long_run は、ロング走の連続延伸が` +
    `カットバック閾値に達したかを決定的に判定済みのフラグ。true のときは recommendations に次週のディロードを、` +
    `headline_metrics.deload_prescription の値（ロング走の削減率 long_run_reduction_pct・週間量の削減率 ` +
    `weekly_volume_reduction_pct・質セッション数 quality_sessions）を引用して具体的な数値で明記すること。` +
    `「距離を据え置く」「増加を +10% 以内に抑える」といった、より弱い代替で置き換えないこと。` +
    `false のときはディロードを推奨しない。long_run_build_weeks / cutback_due_long_run は CONTEXT の値を転記し、` +
    `自分で数え直さないこと。\n` +
    `fitness_curve は 90 日窓の指標で、今週はその曲線上の現在位置として扱うこと（1週で崩壊/急伸したと解釈しない）。\n` +
    `headline_metrics / fusion_flags は CONTEXT の値をそのまま analysis_data に転記し、それと矛盾する主張をしないこと。\n` +
    `出力 JSON 構造:\n` +
    `{"granularity":"${ctx.granularity}","period_start":"${ctx.periodStart}","period_end":"${ctx.periodEnd}",` +
    `"analysis_data":{"narrative":"...","key_learnings":[...],"recommendations":[...],` +
    `"headline_metrics":{...転記...},"fusion_flags":{...転記...}}}\n` +
    `これを ${ctx.tempDir}/trend.json に保存すること（context.json と trend.json 以外のファイルは作らない）。`
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
const SAVE_SCHEMA = {
  type: 'object',
  required: ['saved'],
  properties: {
    saved: { type: 'boolean' },
    granularity: { type: ['string', 'null'] },
    period_start: { type: ['string', 'null'] },
  },
}

const ctx = {
  tempDir: buildTrendTempDir(A),
  periodStart: A.period_start,
  periodEnd: A.period_end,
  granularity: A.granularity,
}

// ── Phase Analyze: inline sonnet — prefetch CONTEXT to a file, narrate → trend.json ──
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
