// Unit tests for the Epic #1544 indicators (.claude/hillclimb/coach-review/indicators.mjs).
// Synthetic cases only - no athlete data.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { coverage, evalRegressions, incidentIndicators, logProblem, uncoveredSurfaces, weekOf } from '../../hillclimb/coach-review/indicators.mjs'

const CASES = [
  { id: 'a', logged: '2026-11-03', source: 'owner', triage: 'principle' },
  { id: 'b', logged: '2026-11-05', source: 'self', triage: 'code' },
  { id: 'c', logged: '2026-11-10', source: 'owner', triage: 'principle', recurs_of: 'a' },
  { id: 'd', logged: '2026-11-11', source: 'eval', triage: 'variance' },
  { id: 'e' },
]

test('weekOf returns the ISO Monday', () => {
  assert.equal(weekOf('2026-11-11'), '2026-11-09') // Wednesday
  assert.equal(weekOf('2026-11-09'), '2026-11-09') // Monday
  assert.equal(weekOf('2026-11-15'), '2026-11-09') // Sunday
})

test('incidentIndicators counts owner corrections per week and the recurrence rate', () => {
  const r = incidentIndicators(CASES)
  assert.equal(r.logged, 4)
  assert.equal(r.unlogged, 1)
  assert.deepEqual(r.weeks, {
    '2026-11-02': { incidents: 2, owner: 1, recurrences: 0 },
    '2026-11-09': { incidents: 2, owner: 1, recurrences: 1 },
  })
  assert.equal(r.recurrence_rate, 0.25)
  assert.deepEqual(r.by_triage, { code: 1, principle: 2, missing_principle: 0, variance: 1 })
})

test('incidentIndicators honours --since', () => {
  const r = incidentIndicators(CASES, '2026-11-09')
  assert.equal(r.logged, 2)
  assert.equal(r.recurrence_rate, 0.5)
})

test('logProblem rejects bad fields and dangling recurs_of', () => {
  const ids = new Set(['a', 'b'])
  assert.equal(logProblem({ id: 'a' }, ids), null)
  assert.match(logProblem({ id: 'a', logged: '11/10' }, ids), /logged/)
  assert.match(logProblem({ id: 'a', source: 'coach' }, ids), /source/)
  assert.match(logProblem({ id: 'a', triage: 'rule' }, ids), /triage/)
  assert.match(logProblem({ id: 'a', recurs_of: 'zz' }, ids), /not a case id/)
  assert.match(logProblem({ id: 'a', recurs_of: 'a' }, ids), /itself/)
})

test('test_coverage_counts_surface_by_pattern', () => {
  const cases = [
    { id: 'a', surface: 'coach', pattern: 'C' },
    { id: 'b', surface: 'coach', pattern: 'C' },
    { id: 'c', surface: 'run_note', pattern: 'A' },
    { id: 'd', pattern: 'B', legacy: true }, // no surface: not counted
  ]
  assert.deepEqual(coverage(cases), { coach: { C: 2 }, run_note: { A: 1 } })
})

test('test_coverage_reports_missing_surfaces', () => {
  const missing = uncoveredSurfaces([{ id: 'a', surface: 'coach', pattern: 'F' }])
  assert.deepEqual(missing, ['run_note', 'run-debrief', 'daily-checkin', 'weekly-review', 'plan-block', 'schedule-workout'])
  assert.ok(!missing.includes('coach'))
  assert.equal(coverage([{ id: 'a', surface: 'coach', pattern: 'F' }])['plan-block'], undefined)
})

test('evalRegressions flags a case that passed earlier and fails in its latest variant', () => {
  const row = (id, pass) => ({ prompt_id: id, grade: { case_pass: pass } })
  const variants = [
    { name: 'v2', rows: [row('x', true), row('y', false), row('z', true)] },
    { name: 'v3', rows: [row('x', true), row('y', true)] },
    { name: 'v4', rows: [row('x', false), row('x', true), row('y', true), row('z', true)] },
  ]
  assert.deepEqual(evalRegressions(variants), [
    { id: 'x', last_variant: 'v4', last_pass_rate: 0.5, last_passed_in: 'v3' },
  ])
})

test('evalRegressions ignores ungraded rows and single-variant cases', () => {
  const variants = [
    { name: 'v1', rows: [{ prompt_id: 'x', grade: { case_pass: null } }] },
    { name: 'v2', rows: [{ prompt_id: 'x', grade: { case_pass: false } }, { prompt_id: 'w', grade: { case_pass: false } }] },
  ]
  assert.deepEqual(evalRegressions(variants), [])
})
