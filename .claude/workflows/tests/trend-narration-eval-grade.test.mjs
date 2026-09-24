// Unit tests for the programmatic graders of the trend-narration eval
// (.claude/hillclimb/trend-narration/grade.mjs). Synthetic CONTEXT only - no
// athlete data. The judge (a model call) is not exercised here.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  checkCutback,
  checkFormat,
  checkNumberGrounding,
  checkTranscription,
  combine,
  judgeContext,
  proseNumbers,
} from '../../hillclimb/trend-narration/grade.mjs'

const kase = { id: 'week_2026-01-05', granularity: 'week', period_start: '2026-01-05', period_end: '2026-01-11' }

function ctxWith(cutback) {
  return {
    headline_metrics: {
      load_delta_pct: 12.5,
      long_run_build_weeks: cutback ? 3 : 1,
      cutback_due_long_run: cutback,
      deload_prescription: cutback
        ? { long_run_reduction_pct: [30, 40], weekly_volume_reduction_pct: [20, 30], quality_sessions: 0 }
        : null,
      fusion_flags: { high_load_low_recovery: false },
    },
    fusion_flags: { high_load_low_recovery: false },
    load_trend: { weekly_km: 36.02, acwr: 1.18 },
  }
}

function trendWith(ctx, recs, narrative = '今週は 36.02 km で、前週比 +12.5% でした。ACWR は 1.18 で optimal に収まっています。') {
  return {
    ...kase,
    analysis_data: {
      narrative,
      key_learnings: ['週間量 36.02 km'],
      recommendations: recs,
      headline_metrics: ctx.headline_metrics,
      fusion_flags: ctx.fusion_flags,
    },
  }
}

const DELOAD = '来週はディロード週にしてください。ロング走は 30〜40% 削減、週間量は 20〜30% 削減、質セッションは 0 本です。'

test('test_cutback_true_quotes_prescription_passes', () => {
  const ctx = ctxWith(true)
  assert.equal(checkCutback(trendWith(ctx, [DELOAD]), ctx).ok, 1)
})

test('test_cutback_true_without_numbers_fails', () => {
  const ctx = ctxWith(true)
  const r = checkCutback(trendWith(ctx, ['来週はカットバックのタイミングです。距離と量を落としてください。']), ctx)
  assert.equal(r.ok, 0)
  assert.match(r.why, /long_run_reduction_pct=30/)
})

test('test_cutback_date_is_not_a_reduction_number', () => {
  // "9/20週" must not satisfy weekly_volume_reduction_pct=20
  const ctx = ctxWith(true)
  const r = checkCutback(trendWith(ctx, ['来週(9/20週)はカットバックです。ロング走 30〜40% 減、質セッションなし。']), ctx)
  assert.equal(r.ok, 0)
  assert.match(r.why, /weekly_volume_reduction_pct=20/)
})

test('test_cutback_false_is_not_applicable', () => {
  const ctx = ctxWith(false)
  assert.equal(checkCutback(trendWith(ctx, ['カットバック効果を活かしてください。']), ctx).ok, null)
})

test('test_transcription_detects_missing_key', () => {
  const ctx = ctxWith(true)
  const t = trendWith(ctx, [DELOAD])
  assert.equal(checkTranscription(t, ctx).ok, 1)
  const { deload_prescription: _, ...partial } = ctx.headline_metrics
  t.analysis_data.headline_metrics = partial
  assert.equal(checkTranscription(t, ctx).ok, 0)
})

test('test_format_rejects_three_recommendations_and_empty_narrative', () => {
  const ctx = ctxWith(false)
  assert.equal(checkFormat(trendWith(ctx, ['a', 'b']), kase).ok, 1)
  assert.equal(checkFormat(trendWith(ctx, ['a', 'b', 'c']), kase).ok, 0)
  assert.equal(checkFormat(trendWith(ctx, ['a'], ''), kase).ok, 0)
  assert.equal(checkFormat(null, kase).ok, 0)
})

test('test_number_grounding_counts_context_and_prompt_numbers', () => {
  const ctx = ctxWith(false)
  assert.equal(checkNumberGrounding(trendWith(ctx, ['a']), ctx).score, 1)
  // narrative 36.02, 1.18, 12, 99.9 + key_learnings 36.02: 99.9 is not a rounding of any value
  // (long_run_build_weeks=1 → 100 as a percentage must not absorb it)
  const t = trendWith(ctx, ['a'], '今週は 36.02 km、ACWR 1.18、12 週窓では 99.9 でした。')
  const r = checkNumberGrounding(t, ctx, '12週のトレーリング窓')
  assert.equal(r.score, 0.8)
  assert.match(r.why, /99\.9/)
})

test('test_number_grounding_accepts_roundings_only', () => {
  const ctx = { load_trend: { weekly_km: 36.02, pace_s: 446.3 } }
  const t = (s) => ({ analysis_data: { narrative: s, key_learnings: [], recommendations: [] } })
  assert.equal(checkNumberGrounding(t('36 km, 36.0 km, 7:26/km'), ctx).score, 1)
  assert.equal(checkNumberGrounding(t('36.1 km'), ctx).score, 0)
})

test('test_prose_numbers_skip_dates_and_read_paces', () => {
  const nums = proseNumbers('7/5 のロング走は 2026-07-05 で 7:26/km、decoupling 0.39%')
  assert.deepEqual(nums.map((n) => n.vals[0]), [446, 0.39])
})

test('test_combine_null_outputs_fail_rule_pass', () => {
  const ctx = ctxWith(true)
  for (const t of [null, { ...kase, analysis_data: {} }]) assert.equal(combine(kase, ctx, t, null).grade.rule_pass, 0)
})

test('test_combine_without_judge_leaves_judge_metrics_null', () => {
  const ctx = ctxWith(true)
  const { grade } = combine(kase, ctx, trendWith(ctx, [DELOAD]), null)
  assert.equal(grade.rule_pass, 1)
  for (const k of ['small_n_ok', 'descriptive_ok', 'durability_ok', 'consistent', 'explains_why', 'actionable'])
    assert.equal(grade[k], null, k)
})

test('test_combine_judge_failure_fails_rule_pass', () => {
  const ctx = ctxWith(true)
  const item = (pass) => ({ applicable: true, pass, reason: 'r' })
  const verdict = {
    small_n: { applicable: false, pass: true, reason: 'n/a' },
    descriptive: item(true),
    durability: item(true),
    consistent: item(false),
    explains_why: { score: 0.5, reason: 'r' },
    actionable: { pass: true, reason: 'r' },
  }
  const { grade } = combine(kase, ctx, trendWith(ctx, [DELOAD]), { verdict })
  assert.equal(grade.consistent, 0)
  assert.equal(grade.small_n_ok, null)
  assert.equal(grade.rule_pass, 0)
  assert.equal(grade.explains_why, 0.5)
})

test('test_judge_context_cuts_fitness_curve_to_period_window', () => {
  // prefetch returns the curve up to today; the judge must see the period's points
  const day = (i) => new Date(Date.UTC(2026, 0, 1) + i * 86_400_000).toISOString().slice(0, 10)
  const curve = Array.from({ length: 300 }, (_, i) => ({ date: day(i), vdot: 30 + i / 100 }))
  const ctx = { fitness_curve: { objective_curve: curve, optimism_gap: { objective_vdot: 32.99 } } }
  const j = judgeContext({ ...kase, period_end: '2026-06-07' }, ctx)
  const dates = j.fitness_curve.objective_curve.filter((p) => typeof p === 'object').map((p) => p.date)
  assert.equal(dates.at(-1), '2026-06-07')
  assert.ok(dates.every((d) => d >= '2026-03-10' && d <= '2026-06-07'))
  assert.match(j.fitness_curve.optimism_gap_note, /latest curve date/)
  assert.equal(ctx.fitness_curve.objective_curve.length, 300) // input untouched
})
