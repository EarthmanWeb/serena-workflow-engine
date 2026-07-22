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

## Hook Inventory (15 scripts)

### Session (`session/`)

| Hook | Event | Purpose |
| ---- | ----- | ------- |
| `swe_session_start.py` | SessionStart | Initialize workflow state, auto-update |
| `swe_session_end.py` | SessionEnd | Clean up sentinels, mark WM abandoned |

### Prompt (`prompt/`)

| Hook | Event | Purpose |
| ---- | ----- | ------- |
| `swe_user_prompt_workflow.py` | UserPromptSubmit | WF_INIT gate, intent analysis, state transitions |
| `swe_user_prompt_swarm.py` | UserPromptSubmit | Detect swarm keywords in prompts |

### Pre-Tool (`pre/`) — gatekeepers

| Hook | Event | Purpose |
| ---- | ----- | ------- |
| `swe_pre_tool_init_gate.py` | PreToolUse | Block ALL tools until WF_INIT chain complete |
| `swe_pre_edit_validate.py` | PreToolUse (Edit/Write/Serena) | Block edits in planning states (WF_VERIFY is edit-allowed); flag staleness at 10 edits |
| `swe_pre_bash_test_gate.py` | PreToolUse (Bash) | Validate test commands against WF_DEBUG_TDD |
| `swe_pre_swarm_feature_gate.py` | PreToolUse (ruflo swarm) | Feature gate: FEATURE_SWARM |

### Post-Tool (`post/`) — observers/learners

| Hook | Event | Purpose |
| ---- | ----- | ------- |
| `swe_post_read_state.py` | PostToolUse (read_memory) | Pure read/display: log "ON STEP" + continuation for CURRENT state — NO transition |
| `swe_post_edit_checkpoint.py` | PostToolUse (Edit/Write/Serena) | Edit counting, checkpoint at 10 edits |
| `swe_post_write_continue.py` | PostToolUse (write_memory) | Post-write continuation |
| `swe_post_todo_wm_sync.py` | PostToolUse (TodoWrite) | WM sync reminder on todo changes |
| `swe_post_memory_index.py` | PostToolUse (write_memory) | Enforce MEMORY.md index update |
| `swe_post_tool_failure.py` | PostToolUseFailure | Flailing detection, failure logging |

> **Reads do NOT transition.** Reading a `WF_*` memory NEVER advances the FSM. `swe_post_read_state.py` only logs "ON STEP" and emits a continuation for the CURRENT state. Transition ONLY via explicit `set_state` — the dedicated tool or the prompt-intent hook (`swe_user_prompt_workflow.py`).

### Stop (`stop/`)

| Hook | Event | Purpose |
| ---- | ----- | ------- |
| `swe_stop_continue_working.py` | Stop | Block unnecessary stops, continue-working |

## Prompt Intent Routing (`swe_user_prompt_workflow.py`)

`swe_user_prompt_workflow.py` classifies each user prompt by pattern match, then routes:

| Intent | Detection | Action |
| ------ | --------- | ------ |
| continuation | "yes", "okay, do X", "any other issues?", "let me know if", status checks | Stay in current state; brief reminder |
| addition | "also", "remove/change/update the", "while you're at it" | Stay in state; incorporate addition |
| new_task | "help me build", "create", "fix", "implement"; action verb at start | Transition to WF_CLASSIFY |
| unknown | No pattern match AND message >120 chars in non-active state | Provide full workflow instructions |

Pattern rules:
- NEVER anchor continuation patterns with `$` — "okay, you should have the latest" must match, not only bare "okay".
- Determine intent solely by pattern match. NEVER use message length as a heuristic (except the >120-char unknown fallback above).

Session-reset rules:
- Compute `should_reset` from WM filename + state-data existence. NEVER parse WM markdown for this.
- WM filename `WM_{session_id}.md` already carries session_id — do NOT parse content to recover it.

State-aware responses:
- WF_INIT → emit MANDATORY instruction to read WF_INIT (blocking gate).
- WF_CLASSIFY + continuation → emit MANDATORY instruction to read WF_CLASSIFY.
- Active state + continuation → emit brief "Continue with workflow".
- new_task detected → transition to WF_CLASSIFY regardless of current state.
- First transition into WF_CLASSIFY with no WM → create WM + sentinel here.
- Valid WM but missing sentinel → recreate sentinel before routing (prevents init-gate deadlock).
- Same-session new_task from WF_DONE → include previous feature keys for fast-path to WF_ARCH_REVIEW.

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
