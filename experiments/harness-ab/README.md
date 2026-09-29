# harness-ab

A/B/control experiment comparing a headless Claude Code agent on one fixed
coding task under three arms:

| arm | description |
|---|---|
| `baseline` | SWE plugin at git ref `23ec65d` (v1.2.82) |
| `v5` | SWE plugin at git ref `harness-v5-prototype` |
| `control` | no plugin |

Arm definitions live in `arms.json`.

## Task

See `task.md` for the exact prompt text given to the agent. The starting
codebase is `fixture/`; for plugin arms, `overlays/swe/` is copied on top
(adds the SWE plugin's CLAUDE.md prefix / setup files). Acceptance is graded
by `hidden_tests/`, which the harness copies into each run directory as
`_acceptance/` after the agent finishes and runs from the run root:

```
python3 -m unittest discover -s _acceptance -t . -p 'test_*.py'
```

`reference_solution/` is an overlay that should make acceptance 100% —
used by `--selftest` to validate the fixture/tests/reference triad itself.

## Metrics

Per run, parsed from `transcript.jsonl` (the `stream-json` output of
`claude -p`):

- From the final `result` event: `subtype`, `is_error`, `num_turns`,
  `duration_ms`, `duration_api_ms`, `est_cost_usd` (read from the raw
  transcript's `total_cost_usd` field — Claude Code's notional cost estimate,
  not an actual charge), `usage` (input/output/
  cache-creation/cache-read token counts), and count of distinct models in
  `modelUsage` (subagent-model-use indicator).
- From `assistant` events: assistant message count, tool calls by name,
  total tool calls, subagent (`Agent`/`Task`) launch count.
- From `user` events: `tool_result` blocks with `is_error: true` (count),
  and among those, ones whose text matches a hook-denial pattern
  (`hook error|PreToolUse|BLOCKED|permissionDecision|denied by hook|...`) →
  `hook_denials`; text blocks mentioning "Stop hook" → `stop_hook_blocks`.
- From the `system`/`init` event: loaded MCP servers + plugins, used to
  assert isolation (control arm shows no `swe` plugin/servers; plugin arms
  do).
- `total_tokens` = sum of the four `usage` fields.

For plugin arms, `run.py` additionally reads `.serena/streams/*.jsonl` in
the run's work directory and counts events by their `type` field (see
`hooks/swe_hooks/core/stream.py`), plus the final workflow state from
`.serena/swe-state/*.state` (JSON, key `current_state`), when present.

Post-run scoring: hidden tests copied to `_acceptance/` and run (5 min
timeout), plus the fixture's own regression tests
(`python3 -m unittest discover -s tests` from run root, 5 min timeout).
Unittest output is parsed for `Ran N tests`, `OK`/`OK (skipped=K)`, and
`FAILED (failures=A, errors=B, skipped=C)` into passed/total.

Everything is appended as one JSON line per run to `<out>/<stamp>/runs.jsonl`
(resumable: re-invoking with `--resume <stamp>` skips runs whose `run_id`
already has a line), plus a `meta.json` with args, arm resolution (commit SHA
+ plugin version from `.claude-plugin/plugin.json`), machine info, and
`claude --version`.

## Isolation design

- Each plugin arm is prepared as a **full `git clone --no-hardlinks`** of the
  repo root into `experiments/harness-ab/.work/arms/<name>/` — never a
  worktree, never an archive. The SWE plugin's SessionStart self-update takes
  a destructive marketplace path if `.git` is not a real directory, so a
  worktree (`.git` as a gitfile pointer) is unsafe here. `run.py` asserts
  `.git` is a directory after preparing each arm.
- Each clone is checked out to `exp-<name>` at the arm's ref, then its
  `origin` remote is removed, so self-update can never fetch anything.
- Runs invoke `claude -p ... --setting-sources project,local
  --dangerously-skip-permissions ... [--plugin-dir <armdir>]`.
  `--setting-sources project,local` excludes user settings, so the
  operator's own installed SWE plugin and user hooks never load; a plugin
  arm loads the plugin *only* via `--plugin-dir`.
- The subprocess environment is a scrubbed copy of `os.environ`: every key
  starting with `CLAUDE` or `SWE_` is removed (except `CLAUDE_CONFIG_DIR`,
  kept if set) so a harness invoked from inside a Claude Code session itself
  doesn't leak nested-session state into the child; every `ANTHROPIC_*` key
  (including `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`,
  `ANTHROPIC_BASE_URL`, `ANTHROPIC_MODEL`) and `AWS_BEARER_TOKEN_BEDROCK` are
  stripped unconditionally, so a stray key in the ambient environment can
  never switch the child to API billing — the harness is meant to run on a
  claude.ai Max subscription, never API billing; `MCP_TIMEOUT=300000` is set.
- Before any `claude -p` call (full run and `--preflight`), `run.py` runs
  `claude auth status` with the cleaned env and requires
  `loggedIn: true` and `authMethod: "claude.ai"` (i.e. logged into a
  claude.ai subscription, not an API key). If that check fails, the run
  aborts with a clear message unless `--allow-api-billing` is passed. The
  parsed status (`authMethod`, `subscriptionType`, `apiProvider` — no
  email/orgId) is recorded in `meta.json` under `auth`. `--dry-run` also
  runs `claude auth status` (read-only, no model call) and reports the
  result without aborting.
- Each `claude` subprocess starts a new process group
  (`start_new_session=True`). On timeout the harness kills the *whole group*
  (SIGTERM, then SIGKILL after 10s) — plugin arms spawn MCP servers (uv/
  python) as children that would otherwise be orphaned.
- Trial ordering interleaves arms (each trial shuffles arm order with a
  seeded RNG) rather than blocking by arm, to spread any environmental
  drift across arms evenly instead of concentrating it in one.

## Usage

Run in order:

```bash
# 1. Confirm auth (claude.ai subscription, not API key) and headless plugin
#    loading work at all.
python3 experiments/harness-ab/run.py --preflight --model claude-sonnet-5

# 2. Validate fixture + reference_solution + hidden_tests are internally consistent
#    (no claude calls; must exit 0).
python3 experiments/harness-ab/run.py --selftest

# 3. Prepare arm clones, print exact commands, run the auth check, and
#    sanity-check the UNMODIFIED fixture fails acceptance (no claude calls).
python3 experiments/harness-ab/run.py --dry-run --model claude-sonnet-5

# 4. Full run: 3 arms x 3 trials = 9 agent invocations, each capped at
#    --timeout-min (default 45). No cost cap is applied by default — see
#    "Cost and budget" below.
python3 experiments/harness-ab/run.py --trials 3 --model claude-sonnet-5 \
  --timeout-min 45 --seed 42

# 5. Aggregate.
python3 experiments/harness-ab/analyze.py experiments/harness-ab/results/<stamp> --csv --md
```

Re-run an interrupted full run with `--resume <stamp>` to skip completed
runs (matched by `run_id` already present in `runs.jsonl`).

## Cost and budget

This harness is meant to run on a **claude.ai Max subscription**, never API
billing. `run.py` enforces this before any `claude -p` call: it runs `claude
auth status` with the scrubbed subprocess env and aborts (unless
`--allow-api-billing` is passed) if the account isn't logged in via
`authMethod: "claude.ai"`.

`--budget-usd` defaults to `None`, meaning **no `--max-budget-usd` flag is
passed to `claude -p` at all** — there's no dollar figure to enforce on a
flat-rate subscription. The `est_cost_usd` figure recorded per run (renamed
from `total_cost_usd` in the raw transcript) is Claude Code's own **notional
cost estimate**, the same number it would compute if you were on API
billing — it is not an actual charge against the subscription. Pass
`--budget-usd <n>` if you want an optional runaway-cost guard anyway (e.g.
to catch a pathological loop early); it's off by default.

### Mandatory spend caps when `--allow-api-billing` is passed

`--allow-api-billing` switches the auth guard off and lets the run proceed
even on API-key/non-subscription billing, where cost is a real charge, not
a notional estimate. When that flag is passed, two caps become **mandatory**
and `run.py` validates them up front (`validate_billing_args`), aborting
with a clear message before any `claude -p` call if either is missing or
not `> 0`:

- **`--budget-usd <n>` (per-run cap, required, must be `> 0`)** — passed as
  `--max-budget-usd <n>` to *every* `claude -p` invocation while API billing
  is allowed, including `--preflight`'s two probe calls and every run in a
  full experiment. On subscription auth this same flag stays optional (only
  passed at all if you supply it, as the runaway-cost guard described above).

- **`--total-budget-usd <n>` (cumulative cap across the whole experiment,
  required, must be `> 0`)** — enforced only when `--allow-api-billing` is
  set; on subscription auth it is accepted but **ignored**, with a note
  printed to stderr, since there's no dollar figure to enforce on a
  flat-rate plan. Before starting each run, `run.py` sums `est_cost_usd`
  across the runs already completed in this experiment's `runs.jsonl`
  (including ones from a prior `--resume`d session) and compares
  `spent + per_run_cap` against the total cap
  (`budget_allows_next(spent, per_run_cap, total_cap)`). Once one more run
  at its worst case (spending the full per-run cap) would exceed the total,
  scheduling stops — remaining runs in the trial matrix are skipped — and
  `meta.json` records `"stopped_for_budget": true`. Re-running with
  `--resume <stamp>` after raising `--total-budget-usd` (or after actual
  spend came in under the per-run cap) picks up where it left off, same as
  any other `--resume`.

Example:

```bash
python3 experiments/harness-ab/run.py --trials 3 --model claude-sonnet-5 \
  --allow-api-billing --budget-usd 2.00 --total-budget-usd 15.00
```

The practical constraint on a Max plan is **usage limits within a rolling
5-hour window**, not dollars. Runs are sequential by default
(`--parallel` is currently unused by `cmd_full_run`'s loop), which keeps
concurrent usage predictable; running many trials back-to-back can still
exhaust a 5-hour window, in which case `claude -p` calls will start failing
until the window rolls over — use `--resume <stamp>` to pick a run back up
after that happens.

## Caveats

- Sonnet output is stochastic; `n=3` trials per arm is directional, not
  statistically powered — treat deltas as hypotheses, not conclusions.
- The `control` arm has no SWE plugin/MCP servers loaded, but it can still
  read `.serena/memory/` files as plain text if the fixture happens to
  contain them — "no plugin" is not the same guarantee as "no visible
  workflow artifacts."
- Plugin arms start Serena (via `uv`) on first use of that arm's clone;
  expect extra first-run latency the first time each arm directory is
  prepared, not on every trial.

## Report

`report.py` renders one self-contained HTML file comparing all runs of an
experiment: a header with a plain-language verdict, a KPI row per arm, five
chart sections (per-metric dot/strip plots, token composition, acceptance
pass rate, harness friction + stream events, tool mix), a sortable per-run
table, and a method/caveats section. Stdlib only — no build step, no
external JS. It imports `analyze.py`'s `aggregate()` by path (read-only) for
per-arm summary stats and adds the per-run chart data `aggregate()` doesn't
compute.

```bash
python3 experiments/harness-ab/report.py experiments/harness-ab/results/<stamp> \
  --out report.html --title "Harness A/B Results"
```

Arm colors are fixed and identical everywhere: **baseline = blue, v5 =
orange, control = green** (never aqua/teal/cyan). The green step is a
re-stepped value within the default palette's green hue family — the
documented-default `#008300` step fails CVD separation against orange under
`--pairs all`, so light uses `#006300` and dark uses `#008f00`, both
re-validated with `scripts/validate_palette.js` from the `dataviz` skill.
Light mode clears every hard gate; dark mode's blue/orange/green trio clears
every hard gate too, with CVD separation for green vs. orange landing in the
6–8 "floor" WARN band (ΔE 6.3) — legal only with secondary encoding, which
every chart in this report already carries (direct row labels, a legend,
hover/focus tooltips, and a `<details>` data-table fallback). Regression
failures and timeouts are marked with an icon + label (never color alone),
so the reserved status-critical red is never reused as arm identity. Token
composition and tool-mix charts use a single neutral blue sequential ramp,
never the arm colors.

Tests live in `tests/test_harness_report.py` (repo root) and cover the pure
scale-math helpers (`linear_scale`, `nice_ticks`, `median`), the data
extraction helpers, and a full render against a synthetic 3-arm dataset
(including a timed-out run and a run with missing metrics) — asserting the
output file is written, every chart section has an `<svg>`, every arm name
and run row appears, missing fields render as an em dash rather than
`NaN`/`None`, and tooltip `data-tip` attributes are present. Run with:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```
