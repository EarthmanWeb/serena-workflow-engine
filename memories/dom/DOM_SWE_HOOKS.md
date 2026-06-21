# DOM_SWE_HOOKS - Python Hook Architecture

## Purpose

Documents the Python-based hook system following official Claude Code patterns.

## Architecture (Python)

All hooks use Python 3 following the official Anthropic `hookify` plugin
pattern.

### Output Mechanism

- **Output to STDOUT** as JSON (not stderr)
- **Exit code always 0** - never use exit 1
- Use `hookSpecificOutput.additionalContext` for user-visible messages
- Use `hookSpecificOutput.permissionDecision = "deny"` to block operations
  (PreToolUse only)

### Package Structure

```
hooks/
├── swe_hooks/
│   ├── __init__.py
│   ├── bootstrap.py              # Import fallback, path setup
│   ├── core/
│   │   ├── __init__.py
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
├── session/
│   ├── swe_session_start.py
│   └── swe_session_end.py
├── prompt/
│   ├── swe_user_prompt_workflow.py
│   └── swe_user_prompt_swarm.py
├── pre/
│   ├── swe_pre_tool_init_gate.py
│   ├── swe_pre_edit_validate.py
│   ├── swe_pre_bash_test_gate.py
│   └── swe_pre_swarm_feature_gate.py
├── post/
│   ├── swe_post_read_state.py
│   ├── swe_post_edit_checkpoint.py
│   ├── swe_post_write_continue.py
│   ├── swe_post_todo_wm_sync.py
│   ├── swe_post_memory_index.py
│   └── swe_post_tool_failure.py
├── stop/
│   └── swe_stop_continue_working.py
└── hooks.json
```

## Hook Inventory (15 Hook Scripts)

### Session Hooks (`session/`)

| Hook                   | Event        | Purpose                                   |
| ---------------------- | ------------ | ----------------------------------------- |
| `swe_session_start.py` | SessionStart | Initialize workflow state, auto-update    |
| `swe_session_end.py`   | SessionEnd   | Clean up sentinels, mark WM abandoned     |

### User Prompt Hooks (`prompt/`)

| Hook                          | Event            | Purpose                                          |
| ----------------------------- | ---------------- | ------------------------------------------------ |
| `swe_user_prompt_workflow.py` | UserPromptSubmit | WF_INIT gate, intent analysis, state transitions |
| `swe_user_prompt_swarm.py`    | UserPromptSubmit | Detect swarm keywords in prompts                 |

### Pre-Tool Hooks (`pre/`) - Gatekeepers

| Hook                            | Event                          | Purpose                                     |
| ------------------------------- | ------------------------------ | ------------------------------------------- |
| `swe_pre_tool_init_gate.py`     | PreToolUse                     | Block ALL tools until WF_INIT chain complete |
| `swe_pre_edit_validate.py`      | PreToolUse (Edit/Write/Serena) | Block edits in planning states (WF_VERIFY now edit-allowed), staleness at 10 edits |
| `swe_pre_bash_test_gate.py`     | PreToolUse (Bash)              | Validate test commands against WF_DEBUG_TDD |
| `swe_pre_swarm_feature_gate.py` | PreToolUse (ruflo swarm)       | Feature gate: FEATURE_SWARM                 |

### Post-Tool Hooks (`post/`) - Observers/Learners

| Hook                          | Event                           | Purpose                            |
| ----------------------------- | ------------------------------- | ---------------------------------- |
| `swe_post_read_state.py`      | PostToolUse (read_memory)       | Pure read/display: logs "ON STEP" + continuation for CURRENT state — NO transition |
| `swe_post_edit_checkpoint.py` | PostToolUse (Edit/Write/Serena) | Edit counting, checkpoint at 10 edits |
| `swe_post_write_continue.py`  | PostToolUse (write_memory)      | Post-write continuation            |
| `swe_post_todo_wm_sync.py`    | PostToolUse (TodoWrite)         | WM sync reminder on todo changes   |
| `swe_post_memory_index.py`    | PostToolUse (write_memory)      | Enforce MEMORY.md index update     |
| `swe_post_tool_failure.py`    | PostToolUseFailure              | Flailing detection, failure logging |

> **Reads do NOT transition.** Reading a `WF_*` memory never advances the FSM.
> `swe_post_read_state.py` only logs "ON STEP" and emits a continuation for the
> CURRENT state. Transitions happen ONLY via explicit `set_state` — the dedicated
> tool or the prompt-intent hook (`swe_user_prompt_workflow.py`).

### Stop Hooks (`stop/`)

| Hook                              | Event | Purpose                                       |
| --------------------------------- | ----- | --------------------------------------------- |
| `swe_stop_continue_working.py`    | Stop  | Block unnecessary stops, continue-working     |

## Prompt Intent Analysis (swe_user_prompt_workflow.py)

The `swe_user_prompt_workflow.py` hook analyzes each user prompt to determine
intent:

| Intent           | Detection Patterns                                                   | Behavior                              |
| ---------------- | -------------------------------------------------------------------- | ------------------------------------- |
| **continuation** | "yes", "okay, do X", "any other issues?", "let me know if", status checks | Stay in current state, brief reminder |
| **addition**     | "also", "remove/change/update the", "while you're at it"            | Stay in state, incorporate addition   |
| **new_task**     | "help me build", "create", "fix", "implement", action verbs at start | Transition to WF_CLASSIFY              |
| **unknown**      | Doesn't match patterns AND message >120 chars in non-active state    | Provide full workflow instructions    |

**Pattern Design:**
- No `$` anchors on continuation patterns — "okay, you should have the latest" matches, not just "okay" alone
- Conversational patterns detect questions/status checks about current work
- No length-based heuristic — intent is determined solely by pattern matching, not message length

**Session Validation:**
- `should_reset` uses WM filename + state data existence, not fragile WM markdown parsing
- WM filename already contains session_id (`WM_{session_id}.md`) — no need to parse content

**State-Aware Responses:**

- In WF_INIT → MANDATORY instruction to read WF_INIT (blocking gate)
- In WF_CLASSIFY + continuation → MANDATORY instruction to read WF_CLASSIFY
- In active states + continuation → Brief "Continue with workflow" message
- New task detected → Transition to WF_CLASSIFY regardless of current state
- On first transition into WF_CLASSIFY with no WM → creates WM + sentinel here
- Valid WM but missing sentinel → Recreates sentinel before routing (prevents init gate deadlock)
- Same-session new task (WF_DONE) → Includes previous feature keys for fast-path to WF_ARCH_REVIEW

## Init Gate (swe_pre_tool_init_gate.py)

Blocks ALL tool calls until the full init chain is complete (sentinel created on entry to WF_CLASSIFY):

- Ensures workflow instructions are read before any work begins
- **Allowed pre-init:** read_memory (wf/* and init-chain), write_memory, edit_memory, list_memories, swe_wm tools, ToolSearch, Serena project setup tools
- **Blocked pre-init:** Bash, Grep, Glob, Edit, Write (non-WM), find_symbol, get_symbols_overview, and all other tools
- Sentinel created on entry to WF_CLASSIFY unlocks all tools for the session

### Sentinel Recovery (Self-Healing)

If the sentinel is missing but a valid WM exists for the session, it is recreated automatically. This prevents a deadlock on mid-session task pivots where the daemon blocks re-running the init chain but the gate demands it.

Recovery points (checked in order):
1. **Prompt hook** (`swe_user_prompt_workflow.py`) — creates sentinel when WM is valid but sentinel missing, before any tool call
2. **Init gate** (`swe_pre_tool_init_gate.py`) — WM-based fallback if prompt hook didn't fire or failed

### Manual Reset

CLI escape hatch for deadlock recovery:

```bash
# Reset sentinel for a specific session
python3 hooks/pre/swe_pre_tool_init_gate.py --reset-sentinel <session_id>

# Clear ALL sentinels (next init chain recreates them)
python3 hooks/pre/swe_pre_tool_init_gate.py --reset-sentinel
```

## Instruction File Strategy

**Changed from echoing to memory references:**

- Hooks no longer read and echo instruction file contents
- Instead, hooks point agent to use `mcp__serena__read_memory("wf/WF_*")`
- Instruction files are copied to `.serena/swe/` during `/swe-init`

**Benefits:**

- Agent uses SERENA's native memory system
- Consistent with how other memories are accessed
- Reduces hook output size
- Agent can re-read instructions as needed

## Output Formats

### Allow (silent)

```json
{}
```

### Show Message

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "Your message here"
  }
}
```

### Block Operation (PreToolUse only)

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "additionalContext": "Reason for blocking"
  }
}
```

### Stop Event Message

```json
{
  "hookSpecificOutput": {
    "hookEventName": "Stop",
    "additionalContext": "Warning message"
  }
}
```

## Core Module Usage

### HookOutput Class

```python
from swe_hooks.core.output import HookOutput, output_empty, output_block, output_message

output = HookOutput(event_name="PostToolUse")
output.add_message("Info message")
output.output_and_exit()  # Always exits 0

# For blocking (PreToolUse only):
output = HookOutput(event_name="PreToolUse")
output.block("Reason for blocking")
output.output_and_exit()

# Quick helpers:
output_empty()                    # {} and exit 0
output_message("Info", "PostToolUse")  # Message and exit 0
output_block("Reason")            # Block PreToolUse and exit 0
```

### StateManager Class

**IMPORTANT: Session-Isolated State Architecture**

State is stored in WM files, NOT a global state file. This allows:

- Multiple concurrent sessions without state conflicts
- Each session has its own WM with embedded workflow context
- State persists in the `## Workflow Context` section of WM

```python
from swe_hooks.core.state_manager import StateManager

# Automatically finds most recent WM file
state_mgr = StateManager(cwd)

# Or specify a specific WM file
state_mgr = StateManager(cwd, wm_filename="WM_20260120_my_task")

state_mgr.get_current_state()  # "WF_CLASSIFY" - read from WM
state_mgr.transition_to("WF_EXECUTE")  # Updates WM file
state_mgr.get_working_memory()  # Returns WM filename
state_mgr.increment_edits()  # In-memory only (session-local)
state_mgr.should_checkpoint()  # True if >= 3 edits
```

**State Storage in WM:**

```markdown
## Workflow Context

- **Calling Step**: WF_EXECUTE ← Current state stored here
- **Feature Key(s)**: BUILDER
- **Session ID**: 20260120_143052
- **Return Step**: WF_VERIFY
- **Invocation Mode**: workflow
```

### Session Module

```python
from swe_hooks.core.session import get_session_id, find_wm_file, create_wm_file

session_id = get_session_id()  # e.g., "250125a3"
wm_path = find_wm_file(cwd)    # Find most recent WM
create_wm_file(cwd, session_id, initial_state="WF_INIT")
```

### WM Validator

```python
from swe_hooks.core.wm_validator import validate_wm_structure, get_wm_section

is_valid, errors = validate_wm_structure(wm_content)
section_content = get_wm_section(wm_content, "Workflow Context")
```

## Hook Loading

**SWE hooks load automatically from the plugin folder.**

The plugin's `hooks/hooks.json` uses `${CLAUDE_PLUGIN_ROOT}` which is resolved by Claude Code's plugin system. No copying to settings.json is needed.

**Verify hooks are loading:**

```bash
jq '.hooks | keys' .claude/plugins/serena-workflow-engine/hooks/hooks.json
# Expected: ["PostToolUse", "PostToolUseFailure", "PreToolUse", "SessionEnd", "SessionStart", "Stop", "UserPromptSubmit"]
```

## Diagnostic Checklist

1. Is Python 3 available? `which python3`
2. Are hooks executable? `chmod +x hooks/**/*.py`
3. Is hooks.json using `python3` commands?
4. Does each hook have appropriate timeout?
5. Do all hooks exit 0?
6. Is the SWE plugin enabled? `jq '.enabledPlugins' .claude/settings.local.json`
