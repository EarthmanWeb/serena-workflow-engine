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
│   └── core/
│       ├── __init__.py
│       ├── output.py        # HookOutput class, helpers
│       ├── input.py         # Input parsing helpers
│       ├── config.py        # Path helpers, state loading
│       └── state_manager.py # State machine logic
├── session_start.py
├── user_prompt_workflow.py
├── user_prompt_swarm.py
├── post_read_state.py
├── pre_edit_validate.py
├── post_edit_checkpoint.py
├── stop_workflow_check.py
├── post_task_learn.py
├── claude_flow_pre_bash.py
├── claude_flow_post_bash.py
├── claude_flow_pre_edit.py
├── claude_flow_post_edit.py
└── hooks.json
```

## Hook Inventory (12 Python Scripts)

| Hook                    | Event            | Purpose                                                                    |
| ----------------------- | ---------------- | -------------------------------------------------------------------------- |
| session_start.py        | SessionStart     | Initialize workflow state to WF_START, point to memory                     |
| user_prompt_workflow.py | UserPromptSubmit | **Analyze prompt intent** (continuation/addition/new_task), route workflow |

### Prompt Intent Analysis (user_prompt_workflow.py)

The `user_prompt_workflow.py` hook analyzes each user prompt to determine
intent:

| Intent           | Detection Patterns                                                   | Behavior                              |
| ---------------- | -------------------------------------------------------------------- | ------------------------------------- |
| **continuation** | "yes", "continue", "proceed", "go ahead", "ok", "sounds good"        | Stay in current state, brief reminder |
| **addition**     | "also", "additionally", "can you also", "one more thing"             | Stay in state, incorporate addition   |
| **new_task**     | "help me build", "create", "fix", "implement", action verbs at start | Transition to WF_START                |
| **unknown**      | Doesn't match patterns                                               | Provide full workflow instructions    |

**State-Aware Responses:**

- In WF_START + continuation → MANDATORY instruction to read WF_START
- In active states (WF_EXECUTE, etc.) + continuation → Brief "Continue with
  workflow" message
- New task detected → Transition to WF_START regardless of current state |
  user_prompt_swarm.py | UserPromptSubmit | Detect swarm keywords in prompts | |
  post_read_state.py | PostToolUse (read_memory) | State transitions,
  WM enforcement | | post_task_learn.py | PostToolUse (read_memory)
  | RLVR trajectory tracking | | pre_edit_validate.py | PreToolUse
  (Edit/Write/Serena) | Block edits in planning states | |
  claude_flow_pre_edit.py | PreToolUse (Edit/Write/Serena) | Context gathering
  (stub) | | post_edit_checkpoint.py | PostToolUse (Edit/Write/Serena) | Edit
  counting, checkpoint triggers | | claude_flow_post_edit.py | PostToolUse
  (Edit/Write/Serena) | Edit outcome learning (stub) | | claude_flow_pre_bash.py
  | PreToolUse (Bash) | Dangerous command blocking | | claude_flow_post_bash.py
  | PostToolUse (Bash) | Command outcome learning (stub) | |
  stop_workflow_check.py | Stop | Verify WF_DONE before session end |

## Instruction File Strategy

**Changed from echoing to memory references:**

- Hooks no longer read and echo instruction file contents
- Instead, hooks point agent to use `mcp__serena__read_memory("WF_*")`
- Instruction files are copied to `.serena/memories/wm/` during `/swe-init`

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

state_mgr.get_current_state()  # "WF_START" - read from WM
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

## ⚠️ CRITICAL: settings.json Sync Requirements

Hook configuration exists in TWO places that MUST stay synchronized:

### 1. Plugin hooks.json (Template)

**Path:** `.claude/plugins/serena-workflow-engine/hooks/hooks.json` **Uses:**
`${CLAUDE_PLUGIN_ROOT}` variable for portability

```json
{
  "hooks": {
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/session_start.py",
        "timeout": 10
      }]
    }]
  }
}
```

### 2. Project settings.json (Active Config)

**Path:** `.claude/settings.json` **Uses:** Literal paths (Claude Code reads
this file directly)

```json
{
  "hooks": {
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "python3 .claude/plugins/serena-workflow-engine/hooks/session_start.py",
        "timeout": 10
      }]
    }]
  }
}
```

### Sync Process

When modifying hooks:

1. **Edit hook script** in plugin folder
2. **Update hooks.json** if adding/removing/renaming hooks
3. **Update settings.json** with literal path equivalent
4. **Verify sync** using diff command below

### Path Translation

| hooks.json                            | settings.json                                          |
| ------------------------------------- | ------------------------------------------------------ |
| `${CLAUDE_PLUGIN_ROOT}/hooks/file.py` | `.claude/plugins/serena-workflow-engine/hooks/file.py` |

### Verification Command

```bash
# Compare hook structures (ignoring path differences)
diff <(jq -S '.hooks' .claude/plugins/serena-workflow-engine/hooks/hooks.json) \
     <(jq -S '.hooks' .claude/settings.json | \
       sed 's|\.claude/plugins/serena-workflow-engine|\${CLAUDE_PLUGIN_ROOT}|g')
```

### Common Sync Errors

| Symptom             | Cause                       | Fix                         |
| ------------------- | --------------------------- | --------------------------- |
| Hook not firing     | Missing from settings.json  | Copy config from hooks.json |
| "Command not found" | Path typo in settings.json  | Verify literal path         |
| Hook fires twice    | Duplicate entries           | Remove duplicate            |
| Matcher not working | Regex differs between files | Sync matcher exactly        |

### Required Sync Points

When changing:

- **Event type** (SessionStart, PreToolUse, etc.) → Sync both
- **Matcher regex** → Sync both exactly
- **Hook order** → Sync both (order matters!)
- **Timeout value** → Sync both
- **Command path** → Translate path for settings.json

## Diagnostic Checklist

1. Is Python 3 available? `which python3`
2. Are hooks executable? `chmod +x hooks/*.py`
3. Is hooks.json using `python3` commands?
4. Does each hook have 10s timeout?
5. Do all hooks exit 0?
6. **Are hooks.json and settings.json in sync?** (use verification command
   above)
