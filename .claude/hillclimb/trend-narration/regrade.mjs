#!/usr/bin/env node
// Re-grade the programmatic metrics (format, transcription, cutback,
// num_grounded, and rule_pass from them + the stored judge items) of existing
// rows with the current grade.mjs - no model calls. Use after a change to the
// programmatic graders so every row in a comparison is scored by one version.
//
//   node .claude/hillclimb/trend-narration/regrade.mjs <variant> [--context-dir DIR]
//
// Reads <variant>/out/<id>_rep<k>.trend.json and the CONTEXT from
// <variant>/out/<id>_rep<k>.context.json (or --context-dir/<id>_rep<k>/context.json
// for runs made before the runner kept it). The judge verdicts are not re-run:
// their grade values are carried over unchanged.
import { existsSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { combine } from './grade.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const [variant, ...rest] = process.argv.slice(2)
if (!variant) {
  console.error('usage: regrade.mjs <variant> [--context-dir DIR]')
  process.exit(2)
}
const ctxDirIdx = rest.indexOf('--context-dir')
const ctxDir = ctxDirIdx >= 0 ? rest[ctxDirIdx + 1] : null

const src = readFileSync(join(HERE, '../../workflows/trend-narration.js'), 'utf8')
const m = src.match(/\/\/ >>> testable\n([\s\S]*?)\n\s*\/\/ <<< testable/)
// eslint-disable-next-line no-new-func
const narrationPrompt = new Function(`${m[1]}\nreturn narrationPrompt`)()

const cases = new Map(JSON.parse(readFileSync(join(HERE, 'cases.json'), 'utf8')).map((c) => [c.id, c]))
const vdir = join(HERE, variant)
const resultsPath = join(vdir, 'results.jsonl')
const rows = readFileSync(resultsPath, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l))

const JUDGED = ['small_n_ok', 'descriptive_ok', 'durability_ok', 'consistent', 'explains_why', 'actionable']
let changed = 0
const out = rows.map((r) => {
  const kase = cases.get(r.prompt_id)
  const stem = `${r.prompt_id}_rep${r.rep}`
  const ctxPath = existsSync(join(vdir, 'out', `${stem}.context.json`))
    ? join(vdir, 'out', `${stem}.context.json`)
    : ctxDir && join(ctxDir, stem, 'context.json')
  if (!kase || !ctxPath || !existsSync(ctxPath)) throw new Error(`no CONTEXT for ${stem}`)
  const ctx = JSON.parse(readFileSync(ctxPath, 'utf8'))
  const trendPath = join(vdir, 'out', `${stem}.trend.json`)
  const trend = existsSync(trendPath) ? JSON.parse(readFileSync(trendPath, 'utf8')) : null
  // Rebuild the judge verdict shape from the stored grades so combine() recomputes rule_pass.
  const g = r.grade
  const item = (x) => (x == null ? { applicable: false, pass: true, reason: '' } : { applicable: true, pass: x === 1, reason: '' })
  const verdict = {
    small_n: item(g.small_n_ok),
    descriptive: item(g.descriptive_ok),
    durability: item(g.durability_ok),
    consistent: item(g.consistent),
    explains_why: { score: g.explains_why, reason: '' },
    actionable: { pass: g.actionable === 1, reason: '' },
  }
  const prompt = narrationPrompt({ tempDir: '/tmp/x', periodStart: kase.period_start, periodEnd: kase.period_end, granularity: kase.granularity })
  const re = combine(kase, ctx, trend, { verdict }, prompt)
  const grade = { ...re.grade }
  for (const k of JUDGED) grade[k] = g[k] // judge values carried over exactly
  const explanation = { ...r.explanation }
  for (const k of ['format_ok', 'transcription_ok', 'cutback_ok', 'num_grounded', 'rule_pass']) explanation[k] = re.explanation[k]
  if (JSON.stringify(grade) !== JSON.stringify(g)) changed++
  return { ...r, grade, explanation, meta: { ...r.meta, regraded: new Date().toISOString() } }
})
writeFileSync(`${resultsPath}.tmp`, out.map((r) => JSON.stringify(r)).join('\n') + '\n')
renameSync(`${resultsPath}.tmp`, resultsPath)
console.error(`[${variant}] regraded ${rows.length} rows, ${changed} changed`)
