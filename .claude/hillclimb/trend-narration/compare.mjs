#!/usr/bin/env node
// Per-variant summary for the trend-narration eval: every metric's mean over
// the cases where it applies, cost / latency, errors, and the paired
// rule_pass difference against baseline on the cases both variants completed.
//
//   node .claude/hillclimb/trend-narration/compare.mjs [.claude/hillclimb/trend-narration]
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const flow = process.argv[2] ?? dirname(fileURLToPath(import.meta.url))
const state = JSON.parse(readFileSync(join(flow, '_state.json'), 'utf8'))
const metricIds = state.metrics.map((m) => m.id)
const readJsonl = (p) =>
  existsSync(p) ? readFileSync(p, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l)) : []

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
    const xs = rows.map((r) => r.grade?.[id]).filter((x) => typeof x === 'number')
    return xs.length ? `${fmt(mean(xs))} (${xs.length})` : '-'
  })
  const cost = rows.map((r) => r.cost_usd).filter((x) => typeof x === 'number')
  const judge = rows.map((r) => r.meta?.judge_cost_usd).filter((x) => typeof x === 'number')
  const lat = rows.map((r) => r.latency_s).filter((x) => typeof x === 'number')
  console.log(
    `| ${v} | ${cfg.model ?? '?'}/${cfg.effort ?? 'settings'} | ${rows.length} | ${errors.length} | ${cells.join(' | ')} | ` +
      `${fmt(median(cost))} | ${fmt(cost.reduce((a, b) => a + b, 0))} | ${fmt(judge.reduce((a, b) => a + b, 0))} | ${fmt(median(lat), 0)} |`,
  )
}

// Paired comparison on rule_pass: cases (and reps) present in both variants.
const base = byVariant.baseline
if (base) {
  const key = (r) => `${r.prompt_id}\0${r.rep}`
  const baseMap = new Map(base.rows.map((r) => [key(r), r]))
  for (const v of variants.filter((x) => x !== 'baseline')) {
    const pairs = byVariant[v].rows.filter((r) => baseMap.has(key(r))).map((r) => [baseMap.get(key(r)), r])
    const worse = pairs.filter(([b, r]) => b.grade.rule_pass === 1 && r.grade.rule_pass === 0)
    const better = pairs.filter(([b, r]) => b.grade.rule_pass === 0 && r.grade.rule_pass === 1)
    const costRatio = median(pairs.filter(([b, r]) => b.cost_usd && r.cost_usd).map(([b, r]) => r.cost_usd / b.cost_usd))
    console.log(
      `\n${v} vs baseline on ${pairs.length} paired cases: rule_pass worse on ${worse.length}, better on ${better.length}; ` +
        `median cost ratio ${fmt(costRatio)}`,
    )
    for (const [, r] of worse) console.log(`  worse: ${r.prompt_id} — ${r.explanation?.rule_pass}`)
    for (const [b] of better) console.log(`  better: ${b.prompt_id} — baseline failed ${b.explanation?.rule_pass}`)
    const shaMismatch = pairs.filter(([b, r]) => b.meta?.context_sha !== r.meta?.context_sha).map(([, r]) => r.prompt_id)
    if (shaMismatch.length) console.log(`  note: CONTEXT differed from baseline on ${shaMismatch.join(', ')}`)
  }
}
