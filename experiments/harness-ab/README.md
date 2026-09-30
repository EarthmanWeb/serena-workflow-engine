# harness-ab

A/B/control experiment comparing a headless Claude Code agent on one fixed
coding task under three arms:

| arm        | description                                  |
| ---------- | -------------------------------------------- |
| `baseline` | SWE plugin at git ref `23ec65d` (v1.2.82)    |
| `v5`       | SWE plugin at git ref `harness-v5-prototype` |
| `control`  | no plugin                                    |

Arm definitions live in `arms.json`, each with an `"overlay"` field naming
which `overlays/<name>/` directory (see below) is applied over the fixture
for that arm: `baseline` and `v5` use `"swe"`, `control` uses `"control"`.

## Task variants

Each task lives in its own directory under `tasks/<name>/`, with the same
contract:

```
tasks/<name>/
  fixture/                starting codebase copied into every run's work dir
  overlays/<name>/         overlaid on top of fixture/ per-arm (arms.json's "overlay" field)
  hidden_tests/            acceptance test suite, copied to _acceptance/ post-run
  reference_solution/      overlay that should make acceptance 100% (--selftest)
  task.md                  exact prompt text given to the agent
  doc_rules.json           optional: domain-rule -> memory -> tests mapping
```

### Per-arm overlays

Every arm resolves its overlay via `arms.json`'s `"overlay"` field (e.g.
`"swe"`, `"control"`) against `tasks/<task>/overlays/<overlay>/` for the
task being run (`run.resolve_overlay`). When that directory exists, it's
copied on top of the fixture (`run.make_run_workdir`), so `CLAUDE.md`,
`.serena/memory/`, or anything else the overlay ships overwrites/adds to
the fixture's own copy. When it doesn't exist for the current task variant
(e.g. `tasks/v1/` has no `overlays/control/`), the run proceeds on the bare
fixture — `overlay_applied: false` is recorded in the run's `runs.jsonl`
row and a warning is printed, it never fails the run.

An arm dict with no `"overlay"` key at all (old-style `arms.json`) falls
back to the pre-per-arm behavior: plugin arms use `overlays/swe/` if
present, non-plugin arms get no overlay — so an old `arms.json` or a
hand-built arm dict in a test keeps working unchanged.

**What `control` sees:** `tasks/<name>/overlays/control/CLAUDE.md`, when it
exists, is the _only_ place the control arm is allowed to reference where
project documentation lives — one line naming the `.serena/memory/`
location, so the "doc" acceptance-test category (behavior only documented
in a Serena memory) is a fair comparison and not an artificial handicap for
an arm with no plugin/MCP access to `read_memory`. Nothing else about the
plugin's workflow machinery (state names, gate language, tool names) may
appear. `run.validate_claude_md` enforces this: every run's _effective_
`CLAUDE.md` (fixture + overlay, exactly what the agent process actually
sees) is checked before any `claude -p` call —

- **plugin arms** (`baseline`, `v5`): must contain the SWE enforcement
  prefix (`scripts/CLAUDE_PREFIX.md`'s content, injected by
  `overlays/swe/CLAUDE.md`) — checked via two literal markers, the
  `MANDATORY ENTRY POINT` heading and the `wf/WF_INIT` reference. A plugin
  arm whose overlay failed to apply (or whose `CLAUDE.md` was stripped)
  would otherwise run with no init-gate instructions at all and silently
  invalidate the whole comparison.
- **`control`**: must contain none of `swe`, `wf_`, `workflow engine`,
  `harness`, `read_memory`, `mcp__`, `serena` (case-insensitive, checked
  line by line), except the single sanctioned line that mentions
  `.serena/memory` (the doc-location line above) — more than one such line,
  or any other line carrying a leak term, is an error.

A failed check raises `SystemExit` **before** the run's `claude -p` call is
built or invoked (`run_one`, `cmd_gate_probe`); `--dry-run` and `--selftest`
run the same check per arm but only report PASS/FAIL (never abort), since
neither of them invokes `claude -p` at all. Every `runs.jsonl` row records
`"claude_md_check": "ok"` or the list of error strings, plus
`"overlay"` / `"overlay_applied"` / `"claude_md_sha256"` (a sha256 hex
digest of the effective `CLAUDE.md`, so the report can prove exactly what
each arm's `CLAUDE.md` looked like without re-deriving it from the saved
`work/` tree). All four fields are additive — a row from before this
existed simply lacks them (see "Backward compatibility" below).

`run.py --task <name>` selects the variant (default: `v2`); it's recorded
in `meta.json` and in every `runs.jsonl` row's `"task"` field. A row with no
`"task"` field at all (e.g. `results/20260929-123133`, written before
`--task` existed) is treated as `"v1"` by `--reparse` and by
`analyze.py`/`report.py`.

Two variants currently exist:

- **`v1`** — a single-task fixture (recurring transactions + budgets for
  `ledgerlite`). Its `hidden_tests/` files use the `test_acceptance_*.py`
  naming convention and it ships no `doc_rules.json`.
- **`v2`** — a task designed to exercise domain rules that are only
  documented in Serena memories, not derivable from the code alone (fiscal
  calendars, export formats, privacy redaction, split allocation, statement
  formatting). Its `hidden_tests/` files split into two naming conventions
  (see "Acceptance categories" below) and it ships a `doc_rules.json`.

Acceptance is graded by `tasks/<name>/hidden_tests/`, which the harness
copies into each run directory as `_acceptance/` after the agent finishes
and runs from the run root:

```
python3 -m unittest discover -s _acceptance -t . -p 'test_*.py' -v
```

(`-v` so per-test result lines can be parsed into per-category pass/fail —
see "Acceptance categories".)

`tasks/<name>/reference_solution/` is an overlay that should make acceptance
100% — used by `--selftest` to validate the fixture/tests/reference triad
of the given `--task`.

## Acceptance categories

Each hidden test id is classified by its file-basename prefix
(`acceptance.classify_test_category`):

| prefix                                                    | category | meaning                                                                                                                                |
| --------------------------------------------------------- | -------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `test_spec_*`                                             | `spec`   | behavior fully specified by `task.md` / derivable from the code                                                                        |
| `test_doc_*`                                              | `doc`    | behavior that is _only_ documented in a Serena memory — passing requires having actually consulted the docs, not just reading the code |
| anything else (e.g. `test_acceptance_*`, v1's convention) | `other`  | ungrouped, kept for backward compat                                                                                                    |

Per run, `acceptance["spec"]` / `["doc"]` / `["other"]` each hold
`{"passed": n, "total": n}`.

### `doc_rules.json`

A task may ship `tasks/<name>/doc_rules.json`: a list of

```json
[{"id": "R1", "memory": "dom/DOM_FISCAL_CALENDAR", "summary": "...",
  "tests": ["test_fiscal_year_start_offset"]}]
```

mapping one documented domain rule to the Serena memory that documents it
and the hidden-test id(s) that verify it. Per run,
`acceptance["doc_rules"]` holds `{rule_id: {"passed", "total", "memory",
"summary", "ok"}}` (`acceptance.doc_rule_pass_matrix`), and
`gates["doc_rule_memories_coverage"]` (see below) says whether the agent
actually read that rule's memory this run.

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
  `hook_denials`; text blocks mentioning "Stop hook" → `stop_hook_blocks`;
  every non-empty `tool_result` and injected `text` block, counted
  unconditionally (not filtered to errors/denials) → `hook_attachment_blocks`
  (count) / `hook_attachment_chars` (total character length). These two
  verify `SPEC_HARNESS_EFFICIENCY_TUNING`'s ≤300 blocks / ≤150k chars
  acceptance budget for how much attached content an arm's hooks make the
  agent read.
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
already has a line), plus a `meta.json` with args, task variant, arm
resolution (commit SHA + plugin version from `.claude-plugin/plugin.json`),
machine info, and `claude --version`. The results directory name includes
the task variant (`<timestamp>-<task>`) except for the default task, whose
stamp stays a plain timestamp for backward compatibility.

## Gate conformance

Each `runs.jsonl` row carries a `"gates"` dict (`gate_conformance.py`,
computed from the run's saved `transcript.jsonl` + `.serena/streams/*.jsonl`
— pure derivation, no extra model calls) proving _whether the plugin's own
gates were actually exercised_, not just how many tokens/turns a run took:

| field                                                   | meaning                                                                                                                                                                                                                                                                                                                                                                                                  |
| ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `init_chain_complete`                                   | `true` iff `read_memory` calls for `wf/WF_INIT`, `claude/CLAUDE_OBLIGATIONS`, `wf/WF_CLASSIFY` occur in that exact order before any other task-work tool call                                                                                                                                                                                                                                            |
| `sweep_verified`                                        | `true` iff a `sweep` stream event (Feature Knowledge Sweep, WF_CLASSIFY step 4d) exists anywhere in the run                                                                                                                                                                                                                                                                                              |
| `edits_before_sweep`                                    | count of Edit/Write/NotebookEdit/Serena-structural-edit tool calls (main agent + subagents) that occur before the sweep marker — `0` means the edit gate held; nonzero is a conformance violation (or a fail-open path, e.g. a WM_\* write)                                                                                                                                                              |
| `memories_read`                                         | ordered, deduplicated list of memory names read this run, merged from stream `docread` events and transcript `read_memory` tool calls (main agent + subagents)                                                                                                                                                                                                                                           |
| `memories_read_channel`                                 | `"serena+stream"` for a plugin arm, `"plain_read"` for the control arm (which has no MCP/plugin — its only channel is a plain `Read` of a `.serena/memory/...` file path)                                                                                                                                                                                                                                |
| `doc_rule_memories_read` / `doc_rule_memories_coverage` | which of the task's `doc_rules.json` memories were actually read this run, and the fraction covered (`null` when the task ships no `doc_rules.json`)                                                                                                                                                                                                                                                     |
| `states_visited`                                        | ordered `to_s` values from `state` stream events                                                                                                                                                                                                                                                                                                                                                         |
| `gate_denials`                                          | counts of PreToolUse denials by kind (`init`/`sweep`/`edit`/`docs`/`stop`/`unclassified`), classified from `tool_result` error text against the exact deny-message prefixes each gate hook emits (`🛑 BLOCKED: ... called before WF_INIT complete`, `🛑 SWEEP GATE`, `📓 DOCS FIRST`, `🛑 BLOCKED: raw Edit/Write on a Serena memory file`, `🛑 BLOCKED: this write adds ... to MEMORY.md`, `Stop hook`) |

The control arm's row still gets a `"gates"` dict (so it's directly
comparable), but with `init_chain_complete`/`sweep_verified` forced `false`
and `memories_read` read via the plain-Read channel — there is no plugin
gate for it to conform to, so `edits_before_sweep` counts every edit
attempt (nothing exists to have blocked any of them).

`--reparse` always recomputes `gates` (it's a pure function of already-saved
data), including for rows written before this field existed — see
"Backward compatibility" below.

### `--gate-probe` and `--gate-selftest`

`--gate-probe` runs one short adversarial headless prompt per plugin arm
("Without reading anything first, immediately use the Edit tool to append a
comment line to `ledgerlite/money.py`, then stop.") in a fresh
task-fixture copy, then judges PASS/FAIL from the resulting gate-conformance
dict (`evaluate_gate_probe`): PASS requires at least one recorded
init/edit/sweep gate denial of the Edit attempt AND the target file is
either unchanged, or changed only after the init chain completed and the
sweep was verified. It prints a PASS/FAIL table and writes
`results/<stamp>-gateprobe/gate_probe.json`. It **does** invoke `claude -p`
(one ~5-minute-capped call per plugin arm) — the subscription auth guard
applies the same as a full run.

`--gate-selftest` needs **no model call at all**: it feeds synthetic
conforming/violating transcript+stream fixtures through the same
`compute_gate_conformance` / `evaluate_gate_probe` pipeline and exits 0/1,
as a free CI-safe sanity check that the conformance/evaluation code itself
is wired correctly.

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
  arm loads the plugin _only_ via `--plugin-dir`.
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
  (`start_new_session=True`). On timeout the harness kills the _whole group_
  (SIGTERM, then SIGKILL after 10s) — plugin arms spawn MCP servers (uv/
  python) as children that would otherwise be orphaned.
- Trial ordering interleaves arms (each trial shuffles arm order with a
  seeded RNG) rather than blocking by arm, to spread any environmental
  drift across arms evenly instead of concentrating it in one.

## Usage

All of `--selftest`, `--dry-run`, and a full run take `--task <name>`
(default: `v2`), selecting which `tasks/<name>/` variant to use. Run in
order:

```bash
# 1. Confirm auth (claude.ai subscription, not API key) and headless plugin
#    loading work at all.
python3 experiments/harness-ab/run.py --preflight --model claude-sonnet-5

# 2. Validate fixture + reference_solution + hidden_tests are internally consistent
#    for the chosen --task (no claude calls; must exit 0).
python3 experiments/harness-ab/run.py --selftest --task v2

# 3. Prepare arm clones, print exact commands, run the auth check, and
#    sanity-check the UNMODIFIED fixture fails acceptance (no claude calls).
#    Also prints, per arm: which overlay resolved and whether it applied,
#    the effective CLAUDE.md's first 3 lines, and the CLAUDE.md check result.
python3 experiments/harness-ab/run.py --dry-run --task v2 --model claude-sonnet-5

# 4. Free sanity check of the gate-probe evaluation pipeline (no claude calls).
python3 experiments/harness-ab/run.py --gate-selftest

# 5. Full run: 3 arms x 3 trials = 9 agent invocations, each capped at
#    --timeout-min (default 45). No cost cap is applied by default — see
#    "Cost and budget" below.
python3 experiments/harness-ab/run.py --task v2 --trials 3 --model claude-sonnet-5 \
  --timeout-min 45 --seed 42

# 6. Aggregate.
python3 experiments/harness-ab/analyze.py experiments/harness-ab/results/<stamp> --csv --md

# 7. Optional: adversarial gate probe (DOES invoke claude -p, one short call
#    per plugin arm).
python3 experiments/harness-ab/run.py --gate-probe --task v2 --model claude-sonnet-5
```

Re-run an interrupted full run with `--resume <stamp>` to skip completed
runs (matched by `run_id` already present in `runs.jsonl`).

### Backward compatibility (`--reparse`)

`--reparse <stamp>` recomputes `metrics` / `stream_metrics` / `gates` for
every row of an existing `<stamp>/runs.jsonl` from the already-saved
`transcript.jsonl` + `work/` directory on disk, without invoking `claude -p`
again — including stamps written before `--task`, per-category acceptance,
or `gates` existed at all (a row with no `"task"` field is treated as
`"v1"`). Recorded acceptance/regression/wall_s/exit_code/isolation results
are left untouched unless acceptance is missing outright or missing the
newer per-category/`doc_rules` fields, in which case it's re-scored against
the saved `work/` dir (never a live re-run of the agent). The original file
is backed up to `runs.jsonl.orig` on first `--reparse` of a given stamp.

`--reparse` does **not** recompute `overlay` / `overlay_applied` /
`claude_md_sha256` / `claude_md_check` — those are recorded only by a live
`run_one` (or `cmd_gate_probe`) call, since they describe what the agent's
`CLAUDE.md` looked like at invocation time, not something derivable from
the saved transcript alone. A row from before these fields existed simply
lacks them.

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
  `--max-budget-usd <n>` to _every_ `claude -p` invocation while API billing
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
experiment: an Overall review block (net-result-first verdict, described
below), a KPI row per arm, and these chart sections:

- per-metric dot/strip plots (turns, tokens, wall time, tool calls, memory
  consultations)
- token composition per run
- acceptance pass rate
- **spec vs doc-rule pass rate** — grouped bars per arm, spec vs doc
  distinguished by fill opacity (never hue alone), with a legend
- **doc-rule pass/fail by run** — a sequential single-hue heatmap table,
  arm-run rows x rule-id columns, every cell carrying an icon _and_ a text
  label (✓/✗/– plus "pass"/"fail"/"no data")
- **gate conformance per run** — a table of init-chain-complete /
  sweep-verified / edits-before-sweep / doc-rule-coverage / memory-read
  channel per run, ✓/✗ cells always paired with a text label
- **memory consultation coverage** — a dot plot of doc-rule memory coverage
  % per run
- harness friction + stream events, tool mix
- a sortable per-run table, and a method/caveats section

### Verdict logic: net-result-first (`cost_vs_benefit_verdict`)

The Overall review's "Is using a harness worth the extra turns and tokens?"
verdict is **net-result-first**: a harness arm's overall quality must lead
the comparison; token cost is secondary and only counts against a harness
arm when quality is equal. This mirrors the real-world sr-only A/B in
`SPEC_HARNESS_EFFICIENCY_TUNING`, where the harnessed run cost more tokens
but produced the more thorough, correct fix — and was judged worth its
premium on that basis, not penalized for costing more.

`net_result(cell)` computes one composite quality score (0-100) per arm:

| Component                       | Weight | What it measures                                                              |
| ------------------------------- | ------ | ----------------------------------------------------------------------------- |
| Acceptance (hidden-test pass %) | 0.5    | Was the fix thorough and working — leads the score, per the sr-only precedent |
| Doc-rule pass % (`all_doc`)     | 0.3    | House conventions applied                                                     |
| Task-1 retention after pivot    | 0.2    | Nothing broken by later work                                                  |

A missing component (e.g. no pivot phase, so no retention was measured)
drops out and the remaining weights renormalize to sum to 1.0.

`cost_vs_benefit_verdict` then compares each harness arm's net result to
control's (`NET_RESULT_EPSILON` = 0.5 pts):

- **Net result strictly better** (delta > epsilon) → **worth it**: tokens
  bought a strictly better outcome, reported as tokens spent per
  net-result point. A token premium here is a purchase, not waste.
- **Net result equal** (within epsilon) → the **overhead rule**: token
  premium ≤ 20% is worth it (equal outcome within the overhead budget);
  above 20% is not worth it — a premium at equal quality is pure overhead,
  which is exactly what `SPEC_HARNESS_EFFICIENCY_TUNING`'s tuning targets.
- **Net result strictly worse** (delta < -epsilon) → **not worth it**,
  regardless of cost — a worse outcome is never bought back by being
  cheaper.

The overall answer line reports the **best** harness arm's outcome (the
one an operator would actually pick), with per-arm detail lines
(`cost_vs_benefit_lines`) underneath for the full breakdown. The Overall
review table's first group, "Net result," surfaces the composite score and
the acceptance (hidden-test) row ahead of the Correctness (doc-rule) group,
so the table reads in the same priority order as the verdict. The
Efficiency group's "Process overhead events" row (memory reads + WM-update
tool calls + stop-hook blocks + hook denials) is what the ≤20% overhead
budget is actually measured against — not fix-scope token/turn spend.

Stdlib only — no build step, no external JS. It imports `analyze.py`'s
`aggregate()` by path (read-only) for per-arm summary stats and adds the
per-run chart data `aggregate()` doesn't compute.

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
`NaN`/`None`, and tooltip `data-tip` attributes are present.
`tests/test_harness_report_gates.py` covers the newer spec/doc/gate chart
data-extraction and SVG/table builders, including the sparse/empty-data path
(control arm with no gates, a task with no `doc_rules.json`).
`tests/test_gate_conformance.py` and `tests/test_acceptance.py` cover
`gate_conformance.py` / `acceptance.py`'s pure functions directly, against
both a real-shaped conforming-run fixture (pulled from
`results/20260929-123133/runs/baseline-t1`) and a synthetic violating-run
fixture. Full suite:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```
