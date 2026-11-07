#!/usr/bin/env node
// Re-grade the deterministic metrics of existing rows with the current
// grade.mjs and check_run_note - no model calls unless --rejudge. Use after a
// change to the deterministic graders or to a case's deterministic `expect`
// fields, so every row in a comparison is scored by one version.
//
//   node .claude/hillclimb/coach-review/regrade.mjs <variant> [--rejudge]
//
// Reads <variant>/out/<id>_rep<k>.{run_note.json,report.json,answer.md,judge_context.json}.
// Without --rejudge the judge's must / must_not results are carried over.
// --rejudge re-runs the judge on every row (one judge call per row).
import { existsSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { casePass, combine, deterministicChecks, judge } from './grade.mjs'
import { checkRunNoteCli, loadCases } from './run-eval.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const [variant, ...rest] = process.argv.slice(2)
if (!variant) {
  console.error('usage: regrade.mjs <variant> [--rejudge]')
  process.exit(2)
}
const rejudge = rest.includes('--rejudge')

const cases = new Map(loadCases(HERE).cases.map((c) => [c.id, c]))
const vdir = join(HERE, variant)
const outDir = join(vdir, 'out')
const resultsPath = join(vdir, 'results.jsonl')
const rows = readFileSync(resultsPath, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l))
const readJson = (p) => (existsSync(p) ? JSON.parse(readFileSync(p, 'utf8')) : null)

let changed = 0
const out = []
for (const r of rows) {
  const kase = cases.get(r.prompt_id)
  if (!kase) throw new Error(`no case ${r.prompt_id} in the loaded cases file`)
  const stem = `${r.prompt_id}_rep${r.rep}`
  let output = null
  let report = null
  let pyCheck = null
  if (kase.kind === 'run_note') {
    output = readJson(join(outDir, `${stem}.run_note.json`))
    report = readJson(join(outDir, `${stem}.report.json`))
    if (output && report)
      pyCheck = await checkRunNoteCli(join(outDir, `${stem}.report.json`), join(outDir, `${stem}.run_note.json`))
  } else {
    const p = join(outDir, `${stem}.answer.md`)
    output = existsSync(p) ? readFileSync(p, 'utf8') : null
  }
  const det = deterministicChecks(kase, output, report, { pyCheck })
  let judged = null
  let judgeMeta = {}
  if (rejudge) {
    judged = await judge(kase, output, readJson(join(outDir, `${stem}.judge_context.json`)))
    judgeMeta = { judge_model: judged.judge_model, judge_usage: judged.judge_usage }
  }
  const { explanation, ...grade } = combine(det, judged)
  if (!rejudge) {
    // Judge results carried over exactly; case_pass recomputed over them.
    for (const k of ['must_ok', 'must_not_ok', 'judge_notes']) explanation[k] = r.explanation?.[k]
    grade.must_ok = r.grade?.must_ok ?? null
    grade.must_not_ok = r.grade?.must_not_ok ?? null
    grade.case_pass = casePass(grade)
  }
  if (JSON.stringify(grade) !== JSON.stringify(r.grade)) changed++
  console.error(`  ${stem}: case_pass ${r.grade?.case_pass} -> ${grade.case_pass}`)
  out.push({
    ...r, ...judgeMeta, grade, explanation,
    meta: { ...r.meta, ...(rejudge ? { rejudged: new Date().toISOString(), judge_cost_usd: judged.judge_cost_usd ?? null } : { regraded: new Date().toISOString() }) },
  })
}
writeFileSync(`${resultsPath}.tmp`, out.map((r) => JSON.stringify(r)).join('\n') + '\n')
renameSync(`${resultsPath}.tmp`, resultsPath)
console.error(`[${variant}] regraded ${rows.length} rows, ${changed} changed`)
