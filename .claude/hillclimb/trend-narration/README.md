# trend-narration eval

Measures the narration stage of `.claude/workflows/trend-narration.js` (the one LLM
step that writes `trend.json`) so a model / effort / prompt change can be judged by
cost per period **and** rule adherence instead of by feel.

## What it runs

- **Cases** (`cases.json`): 26 periods, stratified by the rule each one exercises —
  `sparse` (6 weeks with insufficient data / durability n<3), `cutback` (6 weeks
  where `cutback_due_long_run=true`, two with a fragile worsening durability slope),
  `steady` (9 weeks), `month` (5 months). Only period ids live here; the CONTEXT is
  regenerated at run time by `prefetch_trend_context` from the local DuckDB, so no
  athlete data is committed.
- **App under test**: the workflow's own `narrationPrompt` (extracted from its
  `// >>> testable` block), run as a headless Claude Code session in the repo root
  (`claude -p --model <m> [--effort <e>]`) with Bash/Read/Write/Edit, exactly the
  path the workflow's `agent()` takes. Omitting `--effort` lets the user settings
  decide, as production does.
- **Graders** (`grade.mjs`), all against the `context.json` the model actually read:
  - programmatic — `format_ok`, `transcription_ok` (headline_metrics / fusion_flags
    equal the CONTEXT), `cutback_ok` (cutback=true quotes the deload prescription;
    null when false), `num_grounded` (share of prose numbers that are a rounding of a
    CONTEXT or prompt value);
  - judge (`claude-fable-5-1`, not a model under test) — `small_n_ok`,
    `descriptive_ok` (weekly only), `durability_ok`, `consistent` (incl. no deload
    when cutback=false), `explains_why` (0/0.5/1), `actionable`.
  - `rule_pass` (headline) = every applicable rule metric passes. null = not applicable.

## Running

From the repo root. Spends model usage (Claude Code login); the first run after any
harness change must be started by a human with `--approve-harness`.

```bash
F=.claude/hillclimb/trend-narration
node $F/run-eval.mjs --flow $F --variant baseline --model sonnet --reps 1
node $F/run-eval.mjs --flow $F --variant v1 --model opus --effort medium --reps 1
node $F/compare.mjs                 # every metric, cost, latency, paired rule_pass vs baseline
node <claude-api skill>/shared/evals/report/build-report-lite.mjs $F/
```

`--only id,id` runs a subset (pilot); `--no-judge` skips the model-graded metrics.
Runs resume at the (case, rep) key. A variant directory is one configuration
(`config.json`); the runner refuses to mix another into it. After changing the
programmatic graders, `node $F/regrade.mjs <variant>` re-scores stored outputs
without model calls.

Variant naming is fixed by the report builder (`baseline`, `v1`, `v2`, ...); the
mapping to configurations is in `_state.json` → `variants`.

Outputs (`<variant>/`: results, traces, model outputs and CONTEXT copies) are
gitignored — they contain athlete data.
