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

test('test_narration_prompt_embeds_context', () => {
  const ctx = {
    tempDir: '/tmp/trend_week_2026-06-15_1',
    contextJson: '{"headline_metrics":{"load_delta_pct":12.0}}',
    periodStart: '2026-06-15',
    periodEnd: '2026-06-21',
    granularity: 'week',
  }
  const out = narrationPrompt(ctx)
  assert.match(out, /<CONTEXT>/)
  assert.match(out, /2026-06-15/)
  assert.match(out, /"load_delta_pct":12\.0/) // real data inlined
  assert.match(out, /trend\.json/)
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
  assert.match(out, /一字一句そのまま/) // verbatim CONTEXT handoff
})
