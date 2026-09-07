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
const { normalizeTrendArgs, fetchTrendPrompt, narrationPrompt, mergeTrendPrompt } = new Function(
  `${m[1]}\nreturn { normalizeTrendArgs, fetchTrendPrompt, narrationPrompt, mergeTrendPrompt }`,
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

test('test_merge_prompt_references_save_script', () => {
  const ctx = { tempDir: '/tmp/trend_week_x' }
  const out = mergeTrendPrompt(ctx)
  assert.match(out, /save_trend_narration/)
  assert.match(out, /\/tmp\/trend_week_x/)
})

test('test_fetch_prompt_invokes_prefetch_trend_context', () => {
  const out = fetchTrendPrompt({ period_start: '2026-06-15', period_end: '2026-06-21', granularity: 'week' })
  assert.match(out, /prefetch_trend_context/)
  assert.match(out, /--period-start 2026-06-15 --period-end 2026-06-21 --granularity week/)
})

test('test_fetch_prompt_writes_context_to_file', () => {
  const out = fetchTrendPrompt({ period_start: '2026-06-15', period_end: '2026-06-21', granularity: 'week' })
  // stdout is redirected into the temp dir; the model must never transcribe the
  // ~60KB bundle into its return value (#1023 — that stalled the Fetch stage).
  assert.match(out, /> "\$TD\/context\.json"/)
  assert.doesNotMatch(out, /一字一句そのまま/)
  assert.doesNotMatch(out, /context_json/)
})

test('test_fetch_schema_drops_context_json', () => {
  // The schema lives outside the testable block, so assert on the source text.
  const schema = src.match(/const FETCH_SCHEMA = \{[\s\S]*?\n\}/)
  assert.ok(schema, 'FETCH_SCHEMA not found in trend-narration.js')
  assert.doesNotMatch(schema[0], /context_json/)
  assert.match(schema[0], /required: \['temp_dir'\]/)
})
