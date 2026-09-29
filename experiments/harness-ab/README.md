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
  `duration_ms`, `duration_api_ms`, `total_cost_usd`, `usage` (input/output/
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
  doesn't leak nested-session state into the child; `ANTHROPIC_*` is kept;
  `MCP_TIMEOUT=300000` is set.
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
# 1. Confirm auth, cost, and headless plugin loading work at all (spends a few cents).
python3 experiments/harness-ab/run.py --preflight --model claude-sonnet-5

# 2. Validate fixture + reference_solution + hidden_tests are internally consistent
#    (no claude calls; must exit 0).
python3 experiments/harness-ab/run.py --selftest

# 3. Prepare arm clones, print exact commands, and sanity-check the UNMODIFIED
#    fixture fails acceptance (no claude calls).
python3 experiments/harness-ab/run.py --dry-run --model claude-sonnet-5

# 4. Full run: 3 arms x 3 trials = 9 agent invocations, each capped at
#    --max-budget-usd (default $5) and --timeout-min (default 45).
#    Real cost/time depend entirely on the task and those caps.
python3 experiments/harness-ab/run.py --trials 3 --model claude-sonnet-5 \
  --budget-usd 5 --timeout-min 45 --seed 42

# 5. Aggregate.
python3 experiments/harness-ab/analyze.py experiments/harness-ab/results/<stamp> --csv --md
```

Re-run an interrupted full run with `--resume <stamp>` to skip completed
runs (matched by `run_id` already present in `runs.jsonl`).

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
