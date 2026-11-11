// Unit tests for the stored-run_note rubric sample (#1570):
// .claude/hillclimb/coach-review/sample-stored.mjs and weeklyRubricMeans in indicators.mjs.
// Synthetic data only - no athlete data, no model calls.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { judgeUserPrompt } from '../../hillclimb/coach-review/grade.mjs'
import { weeklyRubricMeans } from '../../hillclimb/coach-review/indicators.mjs'
import { doneIds, isoWeek, sampleCase, sampleContext, storedRow, storedVariant } from '../../hillclimb/coach-review/sample-stored.mjs'

const row = (week, rubric, status = 'ok') => ({ variant: `stored-${week}`, kind: 'run_note', id: '1', status, grade: { rubric } })

test('test_weekly_means_ignore_null_scores', () => {
  const rows = [
    row('2026-W46', { O1: 2, O2: 1 }),
    row('2026-W46', { O1: null, O2: 2 }),
    row('2026-W46', { O1: 1, O2: null }),
  ]
  const w = weeklyRubricMeans(rows)['2026-W46']
  assert.equal(w.O1, 1.5)
  assert.equal(w.O2, 1.5)
  assert.equal(w.n, 3)
})

test('weeklyRubricMeans splits weeks and skips non-stored rows', () => {
  const r = weeklyRubricMeans([
    row('2026-W45', { O1: 0 }),
    row('2026-W46', { O1: 2 }),
    { variant: 'baseline', grade: { rubric: { O1: 0 } } },
    row('2026-W46', { O3: null }),
  ])
  assert.deepEqual(Object.keys(r), ['2026-W45', '2026-W46'])
  assert.equal(r['2026-W45'].O1, 0)
  assert.equal(r['2026-W46'].O1, 2)
  assert.equal(r['2026-W46'].O3, null)
  assert.equal(r['2026-W46'].n, 2)
})

test('isoWeek follows ISO-8601 (Thursday decides the year)', () => {
  assert.equal(isoWeek('2026-11-12'), '2026-W46')
  assert.equal(isoWeek('2026-11-09'), '2026-W46') // Monday
  assert.equal(isoWeek('2026-11-15'), '2026-W46') // Sunday
  assert.equal(isoWeek('2021-01-03'), '2020-W53')
  assert.equal(isoWeek('2024-12-30'), '2025-W01')
  assert.equal(storedVariant('2026-W46'), 'stored-2026-W46')
})

test('sampleCase asks the judge for the rubric only', () => {
  const s = { activity_id: 42, date: '2026-11-10', run_note: { story: 'x' }, report: { a: 1 }, context: { b: 2 } }
  const c = sampleCase(s)
  assert.equal(c.kind, 'run_note')
  assert.deepEqual(c.expect, {})
  const prompt = judgeUserPrompt(c, s.run_note, sampleContext(s))
  assert.match(prompt, /MUST \(0 items/)
  assert.match(prompt, /MUST_NOT \(0 items/)
  assert.match(prompt, /O4 one thing to carry/)
  assert.doesNotMatch(prompt, /O7 intent/)
})

test('storedRow carries the rubric and its reasons; doneIds resumes a week', () => {
  const judged = { rubric: { O1: 2 }, reasons: { rubric: { O1: 'ok' } }, notes: 'n', judge_model: 'm', judge_cost_usd: 0.01 }
  const r = storedRow({ activity_id: 7, date: '2026-11-10', training_type: 'long' }, judged, 'stored-2026-W46')
  assert.equal(r.variant, 'stored-2026-W46')
  assert.equal(r.kind, 'run_note')
  assert.equal(r.id, '7')
  assert.deepEqual(r.grade.rubric, { O1: 2 })
  assert.deepEqual(r.explanation.rubric, { O1: 'ok' })
  assert.deepEqual([...doneIds([r, { ...r, variant: 'stored-2026-W45', id: '8' }], 'stored-2026-W46')], ['7'])
})
