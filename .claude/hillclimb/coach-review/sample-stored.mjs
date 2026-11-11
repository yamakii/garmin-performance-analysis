#!/usr/bin/env node
// Weekly rubric check on stored run_notes (#1570, Epic #1564).
//
// The case eval only sees a failure someone has already written down. This
// script samples a few run_notes already stored in section_analyses (through
// the read-only garmin_mcp.scripts.export_run_note_samples) and scores each on
// the outcome rubric with the same judge as the cases (grade.mjs), rubric only:
// no must / must_not, no coach model run. Rows land in <flow>/stored/results.jsonl
// (gitignored, athlete data) and indicators.mjs prints the weekly mean per
// outcome, so a narrowing or a regression shows as a trend.
//
//   node .claude/hillclimb/coach-review/sample-stored.mjs [--flow DIR] [--n 3]
//        [--since YYYY-MM-DD] [--samples PATH] [--week YYYY-Www]
//
// Spends Max usage: one judge call per sample (about n calls a week).
import { spawn } from 'node:child_process'
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { cleanEnv, judge } from './grade.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(HERE, '../../..')
const SERVER_DIR = join(REPO, 'packages/garmin-mcp-server')

// >>> testable
// ISO-8601 week of a YYYY-MM-DD date, as YYYY-Www (the week's Thursday decides the year).
export function isoWeek(day) {
  const d = new Date(`${day}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + 3 - ((d.getUTCDay() + 6) % 7))
  const year = d.getUTCFullYear()
  const week = Math.ceil(((d - Date.UTC(year, 0, 1)) / 86_400_000 + 1) / 7)
  return `${year}-W${String(week).padStart(2, '0')}`
}

export const storedVariant = (week) => `stored-${week}`

// The case the judge reads for one stored sample: a run_note with no must /
// must_not items, so only the outcome rubric is scored.
export function sampleCase(sample) {
  return { id: String(sample.activity_id), kind: 'run_note', activity_id: sample.activity_id, date: sample.date, expect: {} }
}

export const sampleContext = (sample) => ({ report: sample.report ?? null, context: sample.context ?? null, report_source: 'stored-sample' })

// One results.jsonl row for a judged sample.
export function storedRow(sample, judged, variant) {
  return {
    variant,
    kind: 'run_note',
    id: String(sample.activity_id),
    date: sample.date ?? null,
    training_type: sample.training_type ?? null,
    status: 'ok',
    judge_model: judged?.judge_model ?? null,
    judge_cost_usd: judged?.judge_cost_usd ?? null,
    grade: { rubric: judged?.rubric ?? null },
    explanation: { rubric: judged?.reasons?.rubric ?? null, judge_notes: judged?.notes ?? null },
  }
}

// Sample ids already scored in this variant (a re-run of the same week resumes).
export function doneIds(rows, variant) {
  return new Set(rows.filter((r) => r?.variant === variant).map((r) => String(r.id)))
}
// <<< testable

const readJsonl = (p) =>
  existsSync(p) ? readFileSync(p, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l)) : []

function parseArgs(argv) {
  const a = { flow: HERE, n: 3, since: null, samples: null, week: null }
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i]
    const v = () => {
      if (argv[i + 1] === undefined) throw new Error(`missing value for ${k}`)
      return argv[++i]
    }
    if (k === '--flow') a.flow = v()
    else if (k === '--n') a.n = Number(v())
    else if (k === '--since') a.since = v()
    else if (k === '--samples') a.samples = v()
    else if (k === '--week') a.week = v()
    else throw new Error(`unknown argument: ${k}`)
  }
  if (!Number.isInteger(a.n) || a.n < 1) throw new Error('--n must be a positive integer')
  if (a.since != null && !/^\d{4}-\d{2}-\d{2}$/.test(a.since)) throw new Error('--since must be YYYY-MM-DD')
  if (a.week != null && !/^\d{4}-W\d{2}$/.test(a.week)) throw new Error('--week must be YYYY-Www')
  return a
}

function exportSamples(n, since, out) {
  return new Promise((res, rej) => {
    const args = ['run', '--directory', SERVER_DIR, 'python', '-m', 'garmin_mcp.scripts.export_run_note_samples',
      '--n', String(n), '--since', since, '--out', out]
    const p = spawn('uv', args, { cwd: REPO, env: cleanEnv(), stdio: ['ignore', 'inherit', 'inherit'] })
    p.on('close', (code) => (code === 0 ? res() : rej(new Error(`export_run_note_samples exit ${code}`))))
    p.on('error', rej)
  })
}

async function main(argv) {
  let args
  try { args = parseArgs(argv) } catch (e) {
    console.error(`${e.message}\nusage: node sample-stored.mjs [--flow DIR] [--n 3] [--since YYYY-MM-DD] [--samples PATH] [--week YYYY-Www]`)
    return 2
  }
  const today = new Date().toISOString().slice(0, 10)
  const variant = storedVariant(args.week ?? isoWeek(today))
  let samplesPath = args.samples
  let scratch = null
  if (!samplesPath) {
    const d = new Date(`${today}T00:00:00Z`)
    d.setUTCDate(d.getUTCDate() - 7)
    scratch = mkdtempSync(join(tmpdir(), 'coach-review-stored-'))
    samplesPath = join(scratch, 'samples.json')
    await exportSamples(args.n, args.since ?? d.toISOString().slice(0, 10), samplesPath)
  }
  const samples = JSON.parse(readFileSync(samplesPath, 'utf8'))
  if (scratch) rmSync(scratch, { recursive: true, force: true })

  const outDir = join(args.flow, 'stored')
  mkdirSync(outDir, { recursive: true })
  const resultsPath = join(outDir, 'results.jsonl')
  const done = doneIds(readJsonl(resultsPath), variant)
  let fail = 0
  for (const s of samples) {
    if (done.has(String(s.activity_id))) continue
    try {
      const judged = await judge(sampleCase(s), s.run_note, sampleContext(s))
      appendFileSync(resultsPath, JSON.stringify(storedRow(s, judged, variant)) + '\n')
      console.error(`[${variant}] ${s.activity_id}: ${JSON.stringify(judged.rubric)}`)
    } catch (e) {
      fail += 1
      console.error(`[${variant}] ${s.activity_id} FAILED: ${e?.message || e}`)
    }
  }
  console.error(`[${variant}] ${samples.length} sample(s), ${fail} failed -> ${resultsPath}`)
  return fail ? 1 : 0
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main(process.argv.slice(2)).then((c) => process.exit(c))
