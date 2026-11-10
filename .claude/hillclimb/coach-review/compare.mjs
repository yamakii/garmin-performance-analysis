#!/usr/bin/env node
// Per-variant summary for the coach-review eval: every metric's pass rate over
// the cases where it applies (true = 1), cost / latency, errors, a per-pattern
// case_pass breakdown, and the paired case_pass difference against baseline.
//
//   node .claude/hillclimb/coach-review/compare.mjs [.claude/hillclimb/coach-review]
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { OUTCOMES } from './grade.mjs'

const flow = process.argv[2] ?? dirname(fileURLToPath(import.meta.url))
const state = JSON.parse(readFileSync(join(flow, '_state.json'), 'utf8'))
const metricIds = state.metrics.map((m) => m.id)
const readJsonl = (p) =>
  existsSync(p) ? readFileSync(p, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l)) : []
const num = (x) => (typeof x === 'boolean' ? (x ? 1 : 0) : typeof x === 'number' ? x : null)

const variants = readdirSync(flow)
  .filter((d) => /^(baseline|v[1-9]\d*)$/.test(d))
  .sort((a, b) => (a === 'baseline' ? -1 : b === 'baseline' ? 1 : Number(a.slice(1)) - Number(b.slice(1))))

const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null)
const median = (xs) => {
  if (!xs.length) return null
  const s = [...xs].sort((a, b) => a - b)
  return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2
}
const fmt = (x, d = 2) => (x == null ? '-' : x.toFixed(d))

const byVariant = {}
for (const v of variants) {
  const cfg = existsSync(join(flow, v, 'config.json')) ? JSON.parse(readFileSync(join(flow, v, 'config.json'), 'utf8')) : {}
  const rows = readJsonl(join(flow, v, 'results.jsonl')).filter((r) => r.status === 'ok')
  byVariant[v] = { cfg, rows, errors: readJsonl(join(flow, v, 'errors.jsonl')) }
}

console.log('| variant | config | n | errors | ' + metricIds.join(' | ') + ' | cost_usd med | cost_usd sum | judge_usd sum | latency_s med |')
console.log('|' + ' --- |'.repeat(metricIds.length + 8))
for (const v of variants) {
  const { cfg, rows, errors } = byVariant[v]
  const cells = metricIds.map((id) => {
    const xs = rows.map((r) => num(r.grade?.[id])).filter((x) => x !== null)
    return xs.length ? `${fmt(mean(xs))} (${xs.length})` : '-'
  })
  const cost = rows.map((r) => r.cost_usd).filter((x) => typeof x === 'number')
  const judge = rows.map((r) => r.meta?.judge_cost_usd).filter((x) => typeof x === 'number')
  const lat = rows.map((r) => r.latency_s).filter((x) => typeof x === 'number')
  const tag = cfg.synthetic ? ' (synthetic cases)' : ''
  console.log(
    `| ${v} | ${cfg.model ?? '?'}/${cfg.effort ?? 'settings'}${tag} | ${rows.length} | ${errors.length} | ${cells.join(' | ')} | ` +
      `${fmt(median(cost))} | ${fmt(cost.reduce((a, b) => a + b, 0))} | ${fmt(judge.reduce((a, b) => a + b, 0))} | ${fmt(median(lat), 0)} |`,
  )
}

console.log('\ncase_pass by pattern:')
for (const v of variants) {
  const byPattern = {}
  for (const r of byVariant[v].rows) {
    const x = num(r.grade?.case_pass)
    if (x === null) continue
    ;(byPattern[r.pattern ?? '?'] ??= []).push(x)
  }
  const cells = Object.keys(byPattern).sort().map((p) => `${p} ${fmt(mean(byPattern[p]))} (${byPattern[p].length})`)
  console.log(`  ${v}: ${cells.join(', ') || '-'}`)
}

// Outcome rubric (#1546): mean score 0-2 per outcome over the rows that scored it.
console.log('\noutcome rubric (mean 0-2, n scored):')
console.log('| variant | ' + OUTCOMES.map((o) => `${o.id} ${o.label}`).join(' | ') + ' |')
console.log('|' + ' --- |'.repeat(OUTCOMES.length + 1))
for (const v of variants) {
  const cells = OUTCOMES.map((o) => {
    const xs = byVariant[v].rows.map((r) => r.grade?.rubric?.[o.id]).filter((x) => typeof x === 'number')
    return xs.length ? `${fmt(mean(xs))} (${xs.length})` : '-'
  })
  console.log(`| ${v} | ${cells.join(' | ')} |`)
}

const base = byVariant.baseline
if (base) {
  const key = (r) => `${r.prompt_id}\0${r.rep}`
  const baseMap = new Map(base.rows.map((r) => [key(r), r]))
  for (const v of variants.filter((x) => x !== 'baseline')) {
    const pairs = byVariant[v].rows.filter((r) => baseMap.has(key(r))).map((r) => [baseMap.get(key(r)), r])
    const worse = pairs.filter(([b, r]) => b.grade.case_pass === true && r.grade.case_pass === false)
    const better = pairs.filter(([b, r]) => b.grade.case_pass === false && r.grade.case_pass === true)
    const costRatio = median(pairs.filter(([b, r]) => b.cost_usd && r.cost_usd).map(([b, r]) => r.cost_usd / b.cost_usd))
    console.log(
      `\n${v} vs baseline on ${pairs.length} paired cases: case_pass worse on ${worse.length}, better on ${better.length}; ` +
        `median cost ratio ${fmt(costRatio)}`,
    )
    for (const [, r] of worse) console.log(`  worse: ${r.prompt_id} — ${r.explanation?.case_pass}`)
    for (const [b] of better) console.log(`  better: ${b.prompt_id} — baseline failed ${b.explanation?.case_pass}`)
  }
}
