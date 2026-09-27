---
name: DOM_SWE_HOOKS
description: Python hook architecture — inventory, output contract, init gate, prompt-intent routing, state storage.
metadata:
  type: domain
---

# DOM_SWE_HOOKS — Python Hook Architecture

## Output Contract

- Write JSON to STDOUT. NEVER write to stderr.
- Exit code MUST be 0 always. NEVER exit 1.
- Emit user-visible text via `hookSpecificOutput.additionalContext`.
- Block operations via `hookSpecificOutput.permissionDecision = "deny"` (PreToolUse only).
- All hooks are Python 3, following the Anthropic `hookify` plugin pattern.

## Package Structure

```
hooks/
├── swe_hooks/
│   ├── __init__.py
│   ├── bootstrap.py              # Import fallback, path setup
│   ├── core/
│   │   ├── output.py             # HookOutput class, helpers
│   │   ├── input.py              # Input parsing helpers
│   │   ├── config.py             # Path helpers, state loading
│   │   ├── session.py            # Session ID, WM management
│   │   ├── state_manager.py      # State machine logic
│   │   ├── stream.py             # Append-only JSONL event log
│   │   └── wm_validator.py       # Working Memory validation
│   ├── mcp/
│   │   └── wm_server.py          # swe-wm MCP server
│   └── tools/
│       └── set_state.py          # State manipulation utility
├── session/ prompt/ pre/ post/ stop/
└── hooks.json
```

## Hook Inventory (20 scripts)

### Session (`session/`)

| Hook | Event | Purpose |
| ---- | ----- | ------- |
| `swe_session_start.py` | SessionStart | Initialize workflow state, auto-update. Appends `session_boot` (with `src`: startup/resume/clear/compact) BEFORE the self-update and `selfupdate` (ok/old/new or err) after it — a `session_boot` with no following `selfupdate` = update killed by the hook timeout (30s) |
| `swe_session_end.py` | SessionEnd | Clean up sentinels, mark WM abandoned |

### Prompt (`prompt/`)

| Hook | Event | Purpose |
| ---- | ----- | ------- |
| `swe_user_prompt_workflow.py` | UserPromptSubmit | WF_INIT gate, intent analysis, state transitions |
| `swe_prompt_format_reminder.py` | UserPromptSubmit | Pre-emptive format-budget reminder: when `swe_stop_response_format.py` blocked the prior turn, surface the budget on the next turn + clear the sentinel. Same enabled/bypass guards |

### Pre-Tool (`pre/`) — gatekeepers

| Hook | Event | Purpose |
| ---- | ----- | ------- |
| `swe_pre_tool_init_gate.py` | PreToolUse | Block ALL tools until WF_INIT chain complete |
| `swe_pre_edit_validate.py` | PreToolUse (Edit/Write/Serena) | Block edits in planning states (WF_VERIFY is edit-allowed); in execution states DENY until the per-task sweep sentinel exists (WF_CLASSIFY 4d/4e verified); test-artifact edits additionally require dev/DEV_TESTS + feature/FEATURE_TESTS docreads when those memories exist |
| `swe_pre_memory_index_gate.py` | PreToolUse (Edit/Write/write_memory/edit_memory) | HARD-DENY spec/report/research/project links entering MEMORY.md (state-independent; the post-hook only advises) |
| `swe_pre_bash_test_gate.py` | PreToolUse (Bash) | Validate test commands against WF_DEBUG_TDD |
| `swe_pre_search_docs_gate.py` | PreToolUse (Grep/Glob/search_for_pattern/Bash-inspection; `Read` is matched in hooks.json but NEVER gated — opening a known file is not surfing) | DOCS-FIRST blocking gate. Bash classification is by the PRIMARY (first pipe stage) command of each `;`/`&&`/newline group: work commands (test runners, builds, formatters, git commit) are NOT gated even when piped through head/tail/grep output filters; a sequenced `cat`/`grep` after a build IS gated (standalone recon). BUDGET model: one docs consult (`docread`) clears the next 5 gated calls (`GATED_CALL_BUDGET`); each allowed call appends a `gated` event; deny when the budget is spent or no `docread` exists. Clearance survives turn boundaries. Budget refill requires a FRESH docread (re-reads don't refill; credited memory searches always do). Deny message: budget refill ≠ completed research; lists pending related docs (docpending) as designated next reads; instructs write_memory backfill when discovery was required. Spawned agents are NEVER gated: the gate exempts them BEFORE any sentinel/budget check. PRIMARY signal `core.session.is_spawned_agent(input)` — a non-empty `agent_id`/`agent_type` in the hook payload (Claude Code stamps these ONLY on subagent tool calls; `session_id` is the SAME parent id for main + subagent, so it cannot discriminate). FALLBACK `core.session.is_subagent_transcript(transcript_path)` — the `<session>/subagents/agent-*.jsonl` shape, used when the payload carries the subagent's own path. The transcript-shape check ALONE was insufficient: in practice the hook receives the PARENT transcript path for a subagent tool call, so `is_subagent_transcript` missed it and the subagent got gated on the parent's spent budget — hence the agent_id-first check. Undocumented area (no reasonable feature memories from both searches): deny message routes to a FOREGROUND Agent running /swe-feature-onboard (new area) or /swe-feature-update (stale docs) — no run_in_background, WAIT for completion, then read the memories it wrote to clear the gate; continued manual grepping is explicitly NOT the remedy |
| `swe_pre_question_consent_gate.py` | PreToolUse (AskUserQuestion) | Deny questions while `auto_approve`/`blanket_consent` is set in WM (override tag for destructive/scope changes) |
| `swe_pre_agent_model_gate.py` | PreToolUse (Agent/Task) | Enforces orchestrator + swarm delegation with complexity-based model tiers. Three independent DENY checks: (1) missing `model` param — required for every subagent_type except fixed-model built-ins (`claude-code-guide`, `statusline-setup`); (2) prompt lacks the subagent bypass marker ("BYPASS WF_INIT" / "you are a subagent" / "swarm agent") — without it the spawned agent re-runs the init chain; (3) `model: "opus"` on a routine-keyword prompt (tests/lint/grep/inventory/read-only audit) with no design/architecture keyword — override via literal `[opus-justified: <reason>]` tag in the prompt. Pure functions `missing_model_reason`/`missing_bypass_marker_reason`/`opus_on_routine_reason` are independently unit-tested |

### Post-Tool (`post/`) — observers/learners

| Hook | Event | Purpose |
| ---- | ----- | ------- |
| `swe_post_read_state.py` | PostToolUse (read_memory/list_memories/search_memories_by_name/search_memories_by_front_matter) | Pure read/display: log "ON STEP" + continuation for CURRENT state — NO transition. Appends a `docread` event WITH the memory name (resets the wide-search streak, refills the docs-first gate budget, feeds sweep verification). Memory searches get credit ONLY when they surface no unread names; new names → `docsearch` event + instruction to read them first. Reads surface their own `mem:`/`[[…]]` links: unread linked docs → `docpending` event + read-these instruction (wf/claude/spec/report/research/project/templates excluded) |
| `swe_post_edit_checkpoint.py` | PostToolUse (Edit/Write/Serena) | Edit counting, checkpoint at 10 edits (`CHECKPOINT_THRESHOLD`) |
| `swe_post_search_docs_hint.py` | PostToolUse (Grep/Glob/search_for_pattern) | Counts CONSECUTIVE wide searches; at 3 in a row (`SEARCH_HINT_THRESHOLD`) reminds to check memories/docs first. `docread`/`state`/`checkpoint` events reset the streak |
| `swe_post_write_continue.py` | PostToolUse (write_memory) | Post-write continuation |
| `swe_post_todo_wm_sync.py` | PostToolUse (TodoWrite) | WM sync reminder on todo changes |
| `swe_post_memory_index.py` | PostToolUse (write_memory) | Enforce MEMORY.md index update |
| `swe_post_memory_style.py` | PostToolUse (write_memory/edit_memory) | Enforce terse-imperative memory style (REF_MEMORY_STYLE) |
| `swe_post_tool_failure.py` | PostToolUseFailure | Flailing detection, failure logging |
| `swe_post_orchestrator_drift.py` | PostToolUse (Edit/Write/NotebookEdit/Bash/Serena edit tools/Agent/Task/Workflow) | Orchestrator-drift nudge: counts consecutive main-agent task-work calls since the last Agent/Workflow delegation (`task_work` events, reset by a `delegation` event this same hook appends on Agent/Task/Workflow calls). At `DRIFT_THRESHOLD` (6) emits "split remaining work into parallel subagents (see FEATURE_SUBAGENTS)". Advisory only — never blocks. Exempt for spawned-agent tool calls (subagents are expected to do direct work, not delegate further) |

> **Reads do NOT transition.** Reading a `WF_*` memory NEVER advances the FSM. `swe_post_read_state.py` only logs "ON STEP" and emits a continuation for the CURRENT state. Transition ONLY via explicit `set_state` — the dedicated tool or the prompt-intent hook (`swe_user_prompt_workflow.py`).

## Sentinel Pattern (stream-counted nudges)

Sentinels are non-blocking PostToolUse nudges driven by the append-only JSONL stream (`core/stream.py`). Each fires when a threshold count of same-type events accumulates since a resetting marker. They NEVER block (PostToolUse cannot deny) and always exit 0.

| Sentinel | Counts | Threshold | Reset markers | Reminder |
| -------- | ------ | --------- | ------------- | -------- |
| Edit checkpoint (`swe_post_edit_checkpoint.py`) | `edit` events | 10 (`CHECKPOINT_THRESHOLD`) | `state`, `checkpoint` | Update Working Memory progress |
| Docs-first search (`swe_post_search_docs_hint.py`) | `search` events | 3 (`SEARCH_HINT_THRESHOLD`) | `state`, `checkpoint`, `docread` | Check memories/docs before grepping again |
| Orchestrator drift (`swe_post_orchestrator_drift.py`) | `task_work` events | 6 (`DRIFT_THRESHOLD`) | `state`, `checkpoint`, `delegation` | Split remaining work into parallel subagents |

### Mechanism (shared)

1. On the matched tool, append a typed event: `append_event(stream, '<type>', …)`.
2. Count since the last resetting marker: `count_events_since_last(stream, marker_types=(…), count_type='<type>')` (thin wrappers `count_edits_since_checkpoint` / `count_searches_since_docread`).
3. At threshold, emit a `HookOutput` message; under threshold, emit a concise `output_status`.

### Docs-first search sentinel specifics

- Matches `Grep`, `Glob`, `mcp__*serena__search_for_pattern` (registered in `hooks.json`).
- "In a row" = consecutive: any doc read resets the streak. `swe_post_read_state.py` appends a `docread` event on EVERY `read_memory` / `list_memories` / `search_memories_by_name` / `search_memories_by_front_matter`, so consulting a memory clears the counter — the reminder fires only when the agent greps repeatedly WITHOUT checking docs.
- Unrelated tools (edits, bash, file reads) do NOT reset the streak; only `docread` / `state` / `checkpoint` do. This is the "any doc read resets" semantics — the nudge is specifically about searching instead of reading documentation.

### Adding a New Sentinel

1. Create `hooks/post/swe_post_{name}.py` — append the event, count since markers, nudge at threshold. Model on `swe_post_edit_checkpoint.py`. Always exit 0.
2. If a new reset marker is needed, append that event type from the appropriate hook (e.g. `docread` from `swe_post_read_state.py`).
3. Add a thin counter wrapper in `core/stream.py` if the marker set is reused.
4. Register the PostToolUse matcher in `hooks/hooks.json` with `${CLAUDE_PLUGIN_ROOT}` + a short timeout.
5. Document the sentinel in the table above and in `FEATURE_SWE`.

### Stop (`stop/`)

| Hook | Event | Purpose |
| ---- | ----- | ------- |
| `swe_stop_continue_working.py` | Stop | Block unnecessary stops, continue-working |
| `swe_stop_response_format.py` | Stop | Terse-format gate: block replies over the word budget or emitting recap/summary/self-congratulation scaffolding. ON by default; config from `CLAUDE_PLUGIN_OPTION_RESPONSE_FORMAT_*` env (`core.config.get_response_format_config`). Silent when SWE bypassed / project uninitialized / disabled. Writes a per-session `.format-gate-block-<session>` sentinel (read by `swe_prompt_format_reminder.py`) + a `response-format-offenders.log`, both under `.serena/streams/` |

## Prompt Intent Routing (`swe_user_prompt_workflow.py`)

`swe_user_prompt_workflow.py` classifies each user prompt by pattern match, then routes:

| Intent | Detection | Action |
| ------ | --------- | ------ |
| continuation | "yes", "okay, do X", "any other issues?", "let me know if", status checks | Stay in current state; brief reminder |
| addition | "also", "remove/change/update the", "while you're at it" | Stay in state; incorporate addition |
| new_task | UNAMBIGUOUS openers only: "new task", "switch to", "let's work on", "help me build", "i need you to" (`NEW_TASK_PATTERNS`). Bare imperative verb at start ("fix", "add", "create" — `BARE_VERB_TASK_PATTERNS`) is new_task ONLY when NO task is in flight (state ∈ WF_CLASSIFY/WF_INIT/UNINITIALIZED/WF_DONE/None) | Transition to WF_CLASSIFY (the one verified-pivot path) |
| possible_pivot | Bare imperative verb at start WHILE in an active task state | Stay in current state; inject `pivot_analysis_note` — model judges pivot vs. feedback from full context, self-runs `/swe-goto WF_CLASSIFY` only on a genuine pivot |
| unknown | No pattern match | Active state → stay + `pivot_analysis_note`. WF_CLASSIFY/WF_INIT → emit classify instruction |

`analyze_prompt(prompt, current_state)` is STATE-AWARE — the same bare-verb prompt is `new_task` before work starts but `possible_pivot` mid-task.

⛔ **The deterministic hook does NOT force-decide ambiguous pivots in an active state.** Unknown- and `possible_pivot`-intent prompts in an active state STAY in the current state — the hook emits `pivot_analysis_note` and the MODEL judges pivot-vs-feedback from full conversation context (which a regex cannot), self-transitioning with `/swe-goto WF_CLASSIFY` only on a genuine brand-new task or complete pivot. Ordinary mid-task feedback ("that didn't work", "fix the spacing too", "no, do it differently") therefore keeps working in place. Only two paths auto-`transition_to('WF_CLASSIFY')` from an active state: an unambiguous `new_task` opener, and (post-completion) same-session re-entry from WF_DONE. `NEW_TASK_CUE_RE` ("instead", "now", "new task", "switch to", …) is a HINT surfaced in `pivot_analysis_note`, NEVER the decider. Default is STAY. Rationale: `WF_EXECUTE → WF_CLASSIFY` is not a valid transition-matrix edge, so an active-state re-classification is a forced bypass — reserve it for verified pivots.

Pattern rules:
- NEVER anchor continuation patterns with `$` — "okay, you should have the latest" must match, not only bare "okay".
- Determine intent solely by pattern match + `current_state`. NEVER use message length as a heuristic. Only unambiguous openers or a no-active-task bare verb may auto-transition; everything else defers to the model.

Session-reset rules:
- Compute `should_reset` from WM filename + state-data existence. NEVER parse WM markdown for this.
- WM filename `WM_{session_id}.md` already carries session_id — do NOT parse content to recover it.

State-aware responses:
- WF_INIT → emit MANDATORY instruction to read WF_INIT (blocking gate).
- WF_CLASSIFY + continuation → emit MANDATORY instruction to read WF_CLASSIFY.
- Active state + continuation → emit brief "Continue with workflow".
- Active state + unknown/possible_pivot → STAY; emit `pivot_analysis_note` (model decides pivot vs. feedback, self-transitions only on a true pivot).
- new_task (unambiguous opener) → transition to WF_CLASSIFY regardless of current state.
- First transition into WF_CLASSIFY with no WM → create WM + sentinel here.
- Valid WM but missing sentinel → recreate sentinel before routing (prevents init-gate deadlock).
- Same-session new_task from WF_DONE → include previous feature keys for fast-path to WF_ARCH_REVIEW.

Task-boundary stamping (sweep verification):
- `events_since_task_start()` bounds the current task at the LAST `session_start` event or `state` event with `to_s=WF_CLASSIFY`. Emit those ONLY at genuine task starts.
- `events_since_task_start(since_sweep=True)` ALSO treats the last `sweep` marker as a boundary. `_check_memory_sweep` stamps a `sweep` event on every SUCCESSFUL sweep and accounts docpending links ONLY since that marker — so once a sweep passes, its links are settled and a later sweep in the same session never re-demands them (fixes cross-task docpending accumulation, where continuation/pivot prompts that DON'T re-stamp a task boundary pooled every prior task's links into one window). `docread`/`loaded` verification still uses the full task window.
- Docpending link tokens are sanitized via `is_valid_memory_name()` (core/stream.py): a truncated hook string (e.g. a literal `ref/ref_...`) names no real memory and is dropped before it can be demanded read/defer.
- Genuine new task (new_task intent from an active state, same-session re-entry after WF_DONE) → `append_task_boundary()` (core/stream.py) stamps the boundary after a SUCCESSFUL `transition_to('WF_CLASSIFY')`.
- Continuation / addition / unknown / possible_pivot prompts NEVER stamp — they stay in-state (no transition), so the in-flight task's docreads must keep counting for sweep verification. A boundary is stamped only when the model itself pivots via `/swe-goto WF_CLASSIFY`.
- Slash-command FAST TRACK: `create_wm_and_sentinel(..., stamp_session_start=False)` when the session already has a state file — a mid-task command invocation (e.g. `/swe-wm-update`) re-creates the WM WITHOUT advancing the boundary. ⛔ Re-stamping mid-task drops every prior docread and makes the sweep an unwinnable re-read loop.
- Tests: `tests/test_sweep_gate.py::TestTaskBoundaryStamping`.

## Init Gate (`swe_pre_tool_init_gate.py`)

Block ALL tool calls until the full init chain completes (sentinel created on entry to WF_CLASSIFY).

- Allowed pre-init: `read_memory` (wf/* and init-chain), `write_memory`, `edit_memory`, `list_memories`, swe_wm tools, `ToolSearch`, Serena project-setup tools.
- Blocked pre-init: `Bash`, `Grep`, `Glob`, `Edit`, `Write` (non-WM), `find_symbol`, `get_symbols_overview`, all other tools.
- Sentinel on entry to WF_CLASSIFY unlocks all tools for the session.

### Sentinel Recovery (self-healing)

Recreate a missing sentinel automatically when a valid WM exists for the session — prevents deadlock on mid-session pivots where the daemon blocks re-running the init chain but the gate demands it.

Recovery points, checked in order:
1. `swe_user_prompt_workflow.py` — create sentinel when WM valid but sentinel missing, before any tool call.
2. `swe_pre_tool_init_gate.py` — WM-based fallback when the prompt hook did not fire or failed.

### Manual Reset

```bash
# Reset sentinel for one session
python3 hooks/pre/swe_pre_tool_init_gate.py --reset-sentinel <session_id>

# Clear ALL sentinels (next init chain recreates them)
python3 hooks/pre/swe_pre_tool_init_gate.py --reset-sentinel
```

## Instruction File Strategy

- Hooks NEVER read and echo instruction-file contents.
- Hooks point the agent to `mcp__serena__read_memory("wf/WF_*")`.
- Instruction files are copied to `.serena/swe/` during `/swe-init`.

## Output Formats

Allow (silent):
```json
{}
```

Show message:
```json
{ "hookSpecificOutput": { "hookEventName": "PostToolUse", "additionalContext": "Your message here" } }
```

Block (PreToolUse only):
```json
{ "hookSpecificOutput": { "hookEventName": "PreToolUse", "permissionDecision": "deny", "additionalContext": "Reason for blocking" } }
```

Stop event:
```json
{ "hookSpecificOutput": { "hookEventName": "Stop", "additionalContext": "Warning message" } }
```

## Core Module Usage

### HookOutput (`swe_hooks.core.output`)

```python
from swe_hooks.core.output import HookOutput, output_empty, output_block, output_message

output = HookOutput(event_name="PostToolUse")
output.add_message("Info message")
output.output_and_exit()          # always exits 0

output = HookOutput(event_name="PreToolUse")
output.block("Reason for blocking")   # block PreToolUse only
output.output_and_exit()

output_empty()                        # {} and exit 0
output_message("Info", "PostToolUse") # message and exit 0
output_block("Reason")                # block PreToolUse and exit 0
```

### StateManager (`swe_hooks.core.state_manager`)

Session-isolated state. Store state in WM files, NEVER a global state file — enables concurrent sessions without conflict. Each session's state lives in the `## Workflow Context` section of its WM.

```python
from swe_hooks.core.state_manager import StateManager

state_mgr = StateManager(cwd)                              # finds most recent WM
state_mgr = StateManager(cwd, wm_filename="WM_20260120_my_task")
state_mgr.get_current_state()      # "WF_CLASSIFY" — read from WM
state_mgr.transition_to("WF_EXECUTE")  # updates WM file
state_mgr.get_working_memory()     # WM filename
state_mgr.increment_edits()        # in-memory only (session-local)
state_mgr.should_checkpoint()      # True if >= 3 edits
```

State storage in WM:
```markdown
## Workflow Context

- **Calling Step**: WF_EXECUTE   ← current state stored here
- **Feature Key(s)**: BUILDER
- **Session ID**: 20260120_143052
- **Return Step**: WF_VERIFY
- **Invocation Mode**: workflow
```

### Session (`swe_hooks.core.session`)

```python
from swe_hooks.core.session import get_session_id, find_wm_file, create_wm_file

session_id = get_session_id()   # e.g., "250125a3"
wm_path = find_wm_file(cwd)     # most recent WM
create_wm_file(cwd, session_id, initial_state="WF_INIT")
```

### WM Validator (`swe_hooks.core.wm_validator`)

```python
from swe_hooks.core.wm_validator import validate_wm_structure, get_wm_section

is_valid, errors = validate_wm_structure(wm_content)
section_content = get_wm_section(wm_content, "Workflow Context")
```

## Hook Loading

- SWE hooks load automatically from the plugin folder. Do NOT copy to settings.json.
- `hooks/hooks.json` uses `${CLAUDE_PLUGIN_ROOT}`, resolved by the plugin system.

Verify loading:
```bash
jq '.hooks | keys' .claude/plugins/serena-workflow-engine/hooks/hooks.json
# Expected: ["PostToolUse","PostToolUseFailure","PreToolUse","SessionEnd","SessionStart","Stop","UserPromptSubmit"]
```

## Diagnostic Checklist

1. `which python3` — Python 3 available.
2. `chmod +x hooks/**/*.py` — hooks executable.
3. hooks.json uses `python3` commands.
4. Each hook has an appropriate timeout.
5. All hooks exit 0.
6. `jq '.enabledPlugins' .claude/settings.local.json` — SWE plugin enabled.
