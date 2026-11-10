#!/usr/bin/env node
// Epic #1544 indicators, computed from what already exists (no model calls, no
// new store):
//   - the incident log = the eval cases (coach-incident-protocol.md puts every
//     incident there), read through the optional fields logged / source /
//     triage / recurs_of (cases.schema.json);
//   - eval regressions = cases that passed in an earlier variant and fail in the
//     latest one (results.jsonl);
//   - the rule budget = `garmin_mcp.scripts.rule_budget` (printed separately).
//
//   node .claude/hillclimb/coach-review/indicators.mjs [flow dir] [--since YYYY-MM-DD]
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

// >>> testable
const SOURCES = ['owner', 'self', 'eval']
const TRIAGES = ['code', 'principle', 'missing_principle', 'variance']

// Problems with the incident-log fields of one case (null when fine or absent).
export function logProblem(c, ids) {
  if (c.logged != null && !/^\d{4}-\d{2}-\d{2}$/.test(c.logged)) return 'logged must be YYYY-MM-DD'
  if (c.source != null && !SOURCES.includes(c.source)) return `source must be one of ${SOURCES.join('/')}`
  if (c.triage != null && !TRIAGES.includes(c.triage)) return `triage must be one of ${TRIAGES.join('/')}`
  if (c.recurs_of != null && !ids.has(c.recurs_of)) return `recurs_of ${JSON.stringify(c.recurs_of)} is not a case id`
  if (c.recurs_of === c.id) return 'recurs_of points at itself'
  return null
}

// Monday (ISO week start) of a YYYY-MM-DD date, as YYYY-MM-DD.
export function weekOf(day) {
  const d = new Date(`${day}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7))
  return d.toISOString().slice(0, 10)
}

// Weekly incident counts and the recurrence rate over logged cases on/after `since`.
export function incidentIndicators(cases, since = '0000-00-00') {
  const logged = cases.filter((c) => c.logged && c.logged >= since)
  const weeks = {}
  for (const c of logged) {
    const w = (weeks[weekOf(c.logged)] ??= { incidents: 0, owner: 0, recurrences: 0 })
    w.incidents += 1
    if (c.source === 'owner') w.owner += 1
    if (c.recurs_of) w.recurrences += 1
  }
  const byTriage = Object.fromEntries(TRIAGES.map((t) => [t, logged.filter((c) => c.triage === t).length]))
  const recurrences = logged.filter((c) => c.recurs_of).length
  return {
    logged: logged.length,
    unlogged: cases.length - cases.filter((c) => c.logged).length,
    weeks: Object.fromEntries(Object.entries(weeks).sort(([a], [b]) => a.localeCompare(b))),
    by_triage: byTriage,
    recurrence_rate: logged.length ? recurrences / logged.length : null,
  }
}

// variants: [{ name, rows: [{ prompt_id, grade: { case_pass } }] }] in run order.
// A case regressed when it passed (every rep) in some earlier variant and any rep
// of it fails in the latest variant that ran it.
export function evalRegressions(variants) {
  const passRate = (rows) => {
    const graded = rows.filter((r) => typeof r.grade?.case_pass === 'boolean')
    return graded.length ? graded.filter((r) => r.grade.case_pass).length / graded.length : null
  }
  const perCase = {}
  for (const v of variants) {
    const ids = new Set(v.rows.map((r) => r.prompt_id))
    for (const id of ids) (perCase[id] ??= []).push({ variant: v.name, rate: passRate(v.rows.filter((r) => r.prompt_id === id)) })
  }
  const out = []
  for (const [id, hist] of Object.entries(perCase)) {
    const runs = hist.filter((h) => h.rate != null)
    if (runs.length < 2) continue
    const last = runs[runs.length - 1]
    const passedBefore = runs.slice(0, -1).filter((h) => h.rate === 1)
    if (last.rate < 1 && passedBefore.length)
      out.push({ id, last_variant: last.variant, last_pass_rate: last.rate, last_passed_in: passedBefore[passedBefore.length - 1].variant })
  }
  return out.sort((a, b) => a.id.localeCompare(b.id))
}
// <<< testable

const variantOrder = (a, b) => (a === 'baseline' ? -1 : b === 'baseline' ? 1 : Number(a.slice(1)) - Number(b.slice(1)))
const readJsonl = (p) =>
  existsSync(p) ? readFileSync(p, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l)) : []

function main(argv) {
  const sinceIdx = argv.indexOf('--since')
  const since = sinceIdx >= 0 ? argv[sinceIdx + 1] : '0000-00-00'
  const positional = argv.filter((a, i) => !a.startsWith('--') && argv[i - 1] !== '--since')
  const flow = positional[0] ?? dirname(fileURLToPath(import.meta.url))
  const casesPath = existsSync(join(flow, 'cases.local.json')) ? join(flow, 'cases.local.json') : join(flow, 'cases.example.json')
  const cases = JSON.parse(readFileSync(casesPath, 'utf8'))
  const ids = new Set(cases.map((c) => c.id))
  let bad = 0
  for (const c of cases) {
    const p = logProblem(c, ids)
    if (p) { console.error(`${c.id}: ${p}`); bad += 1 }
  }
  if (bad) return 1

  const inc = incidentIndicators(cases, since)
  console.log(`## Incidents (${casesPath.split('/').pop()}, logged since ${since === '0000-00-00' ? 'the start' : since})`)
  console.log(`logged ${inc.logged}, without a logged date ${inc.unlogged}; recurrence rate ${inc.recurrence_rate == null ? '-' : inc.recurrence_rate.toFixed(2)}`)
  console.log(`by triage: ${Object.entries(inc.by_triage).map(([k, v]) => `${k} ${v}`).join(', ')}`)
  console.log('\n| week | incidents | owner corrections | recurrences |\n| --- | --- | --- | --- |')
  for (const [w, s] of Object.entries(inc.weeks)) console.log(`| ${w} | ${s.incidents} | ${s.owner} | ${s.recurrences} |`)

  const variants = readdirSync(flow)
    .filter((d) => /^(baseline|v[1-9]\d*)$/.test(d))
    .sort(variantOrder)
    .map((name) => ({ name, rows: readJsonl(join(flow, name, 'results.jsonl')).filter((r) => r.status === 'ok') }))
  const reg = evalRegressions(variants)
  console.log('\n## Eval regressions (passed earlier, failing in the latest variant that ran the case)')
  if (!reg.length) console.log('none')
  for (const r of reg) console.log(`- ${r.id}: ${r.last_variant} pass ${r.last_pass_rate.toFixed(2)} (last full pass ${r.last_passed_in})`)
  console.log('\nRule budget: uv run --directory packages/garmin-mcp-server python -m garmin_mcp.scripts.rule_budget [--history]')
  return 0
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) process.exit(main(process.argv.slice(2)))
