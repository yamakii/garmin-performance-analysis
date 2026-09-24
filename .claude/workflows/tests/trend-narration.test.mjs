// Automated tests for trend-narration.js pure logic (run by `node --test`).
//
// Workflow scripts run in a sandbox (top-level await/return, injected globals)
// and can't be imported directly, so we extract the side-effect-free block
// between the `// >>> testable` / `// <<< testable` markers and evaluate it.
// This exercises the ACTUAL source (single source of truth).
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const src = readFileSync(new URL('../trend-narration.js', import.meta.url), 'utf8')
const m = src.match(/\/\/ >>> testable\n([\s\S]*?)\n\s*\/\/ <<< testable/)
assert.ok(m, 'testable block markers not found in trend-narration.js')
// eslint-disable-next-line no-new-func
const { normalizeTrendArgs, buildTrendTempDir, narrationPrompt, mergeTrendPrompt } = new Function(
  `${m[1]}\nreturn { normalizeTrendArgs, buildTrendTempDir, narrationPrompt, mergeTrendPrompt }`,
)()

test('test_normalize_defaults_granularity_week', () => {
  assert.deepEqual(
    normalizeTrendArgs({ period_start: '2026-06-15', period_end: '2026-06-21' }),
    { period_start: '2026-06-15', period_end: '2026-06-21', granularity: 'week', user_id: 'default' },
  )
})

test('test_normalize_preserves_month', () => {
  const out = normalizeTrendArgs({ period_start: '2026-06-01', period_end: '2026-06-30', granularity: 'month' })
  assert.equal(out.granularity, 'month')
  // JSON-string form is accepted too and an unknown granularity clamps to 'week'.
  assert.equal(normalizeTrendArgs('{"granularity":"month","period_start":"2026-06-01"}').granularity, 'month')
  assert.equal(normalizeTrendArgs({ granularity: 'day' }).granularity, 'week')
  assert.deepEqual(normalizeTrendArgs(undefined), {
    period_start: null,
    period_end: null,
    granularity: 'week',
    user_id: 'default',
  })
})

test('test_narration_prompt_reads_context_file', () => {
  const ctx = {
    tempDir: '/tmp/trend_week_2026-06-15_1',
    periodStart: '2026-06-15',
    periodEnd: '2026-06-21',
    granularity: 'week',
  }
  const out = narrationPrompt(ctx)
  // The ~60KB bundle is handed over as a file, never inlined into the prompt (#1023).
  assert.match(out, /\/tmp\/trend_week_2026-06-15_1\/context\.json/)
  assert.match(out, /Read/)
  assert.doesNotMatch(out, /<CONTEXT>/)
  assert.match(out, /2026-06-15/)
  assert.match(out, /trend\.json/)
})

test('narrationPrompt includes small-N guard', () => {
  const ctx = {
    tempDir: '/tmp/trend_week_2026-06-15_1',
    periodStart: '2026-06-15',
    periodEnd: '2026-06-21',
    granularity: 'week',
  }
  const out = narrationPrompt(ctx)
  // insufficient_data / small-N components must not be narrated as trends,
  // and an underpowered "stable" is 判定不能, not 安定 (#813).
  assert.match(out, /insufficient_data/)
  assert.match(out, /判定不能/)
  assert.match(out, /descriptive/) // weekly metric_trends are descriptive
})

test('narrationPrompt includes durability decoupling-ranking guard', () => {
  const ctx = {
    tempDir: '/tmp/trend_week_2026-06-15_1',
    periodStart: '2026-06-15',
    periodEnd: '2026-06-21',
    granularity: 'week',
  }
  const out = narrationPrompt(ctx)
  // durability quality is judged by decoupling and transcribed from best_run,
  // NOT derived from raw signed values (#823).
  assert.match(out, /best_run/)
  assert.match(out, /decoupling/)
  // pace_fade is a pacing-strategy descriptor, not a quality axis.
  assert.match(out, /pace_fade/)
  assert.match(out, /優劣軸ではない/)
})

test('narrationPrompt includes long-run cutback guard', () => {
  const ctx = {
    tempDir: '/tmp/trend_week_2026-06-15_1',
    periodStart: '2026-06-15',
    periodEnd: '2026-06-21',
    granularity: 'week',
  }
  const out = narrationPrompt(ctx)
  // The cutback gate is decided deterministically and only transcribed (#1110).
  assert.match(out, /cutback_due_long_run/)
  assert.match(out, /long_run_build_weeks/)
  // A due cutback must be stated as a deload, not softened to a hold.
  assert.match(out, /ディロード/)
  assert.match(out, /据え置く/)
})

test('test_merge_prompt_references_save_script', () => {
  const ctx = { tempDir: '/tmp/trend_week_x' }
  const out = mergeTrendPrompt(ctx)
  assert.match(out, /save_trend_narration/)
  assert.match(out, /\/tmp\/trend_week_x/)
})

test('test_build_trend_temp_dir_is_deterministic', () => {
  const a = { period_start: '2026-09-14', period_end: '2026-09-20', granularity: 'week' }
  assert.equal(buildTrendTempDir(a), '/tmp/trend_week_2026-09-14')
  assert.equal(buildTrendTempDir({ ...a, granularity: 'month' }), '/tmp/trend_month_2026-09-14')
})

test('test_build_trend_temp_dir_rejects_bad_period', () => {
  const ok = { period_start: '2026-09-14', period_end: '2026-09-20', granularity: 'week' }
  for (const bad of [null, '2026/09/14', '$(date)', '']) {
    assert.throws(() => buildTrendTempDir({ ...ok, period_start: bad }), /period_start/)
  }
  assert.throws(() => buildTrendTempDir({ ...ok, period_end: '$(rm -rf x)' }), /period_end/)
  assert.throws(() => buildTrendTempDir({ ...ok, granularity: 'day' }), /granularity/)
})

test('test_narration_prompt_runs_prefetch_into_temp_dir', () => {
  const out = narrationPrompt({
    tempDir: '/tmp/trend_week_2026-06-15',
    periodStart: '2026-06-15',
    periodEnd: '2026-06-21',
    granularity: 'week',
  })
  // The ~60KB bundle is redirected to a file by one Bash command and Read back;
  // it is never transcribed through a model's output (#1023).
  assert.match(out, /prefetch_trend_context/)
  assert.match(out, /--period-start 2026-06-15 --period-end 2026-06-21 --granularity week/)
  assert.match(out, /> "\$TD\/context\.json"/)
  assert.match(out, /TD=\/tmp\/trend_week_2026-06-15/)
  // A failed prefetch must not leave a stale trend.json for the save step.
  assert.match(out, /rm -f "\$TD\/trend\.json"/)
})

test('test_narration_prompt_cites_deload_prescription', () => {
  const out = narrationPrompt({
    tempDir: '/tmp/trend_week_2026-06-15',
    periodStart: '2026-06-15',
    periodEnd: '2026-06-21',
    granularity: 'week',
  })
  // The deload numbers come from the CONTEXT, not a copy in the prompt.
  assert.match(out, /deload_prescription/)
  assert.doesNotMatch(out, /−30〜40%/)
  assert.doesNotMatch(out, /−20〜30%/)
})

test('test_workflow_has_no_fetch_agent', () => {
  // The temp dir is built in JS; no agent exists just to create it.
  assert.doesNotMatch(src, /FETCH_SCHEMA/)
  assert.doesNotMatch(src, /phase\('Fetch'\)/)
})
