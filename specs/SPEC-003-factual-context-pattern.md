# SPEC-003: Factual Context Pattern

**Version:** 2.0.0
**Status:** Draft
**Date:** 2026-05-20
**Depends on:** SPEC-001, SPEC-002

---

## 1. Purpose

Define how ALL `additionalContext` output is rewritten from imperative commands to factual state descriptions. This is the single most important change in the refactor -- it directly addresses why Claude ignores or fights the current workflow gates.

## 2. The Problem

### 2.1 Current Output Style (Triggers Prompt Injection Defenses)

```
🚀 SERENA WORKFLOW ENGINE v1.1.17 - Session 00893aaf
⏳ Working Memory: Not yet created (will be created after WF_INIT)
Current State: WF_INIT

STEP 1: Read WF_INIT workflow instructions
STEP 2: Follow WF_INIT to classify and execute user's task

⚠️ ANTI-RATIONALIZATION BLOCK:
❌ "This is simple" → ALL tasks go through workflow
❌ "I know what to do" → Workflow exists for consistency
```

**Why this fails:** Claude's safety training treats out-of-band imperative instructions ("STEP 1: Read...", "You MUST...", "STOP.") as potential prompt injection. Claude is trained to surface such text rather than blindly follow it.

### 2.2 Required Output Style (Factual State)

```
Serena Workflow Engine v2.0.0. Session 00893aaf.
Workflow state: WF_INIT. Working Memory: not created.
Completed steps: none. Required before task work: WF_INIT completion, WM creation.
Feature context: not loaded.
```

**Why this works:** Factual statements about current state inform Claude's decision-making without triggering injection defenses. Claude naturally uses state awareness to determine appropriate next actions.

## 3. Context Template System

### 3.1 Template Definition Format

Templates are defined in `config/context-templates.yml`:

```yaml
version: "2.0.0"

# Global context prefix (always included)
prefix: |
  Serena Workflow Engine v{version}. Session {session_id}.

# Per-event templates
templates:

  # SessionStart context
  session_start: |
    {prefix}
    Workflow state: {current_state}. Working Memory: {wm_status}.
    Setup status: {setup_status}.

  # UserPromptSubmit context
  prompt_context: |
    Session {session_id} state: {current_state}.
    WM: {wm_status}. Completed: [{completed_steps}].
    Required before task work: [{required_steps}].
    Detected: {detected_patterns}.

  # PreToolUse deny reason (used in permissionDecisionReason)
  gate_deny: |
    {gate_name}: {gate_reason}. Required: {gate_requirement}.
    Session state: {current_state}. Satisfied gates: [{satisfied_gates}].

  # PreToolUse additional context (accompanies deny)
  gate_context: |
    Session {session_id} workflow requires {gate_requirement} before {blocked_action}.
    Current state: {current_state}. Gate: {gate_name} ({gate_status}).

  # PostToolUse state transition context
  state_transition: |
    Transition: {old_state} -> {new_state}.
    Completed steps: [{completed_steps}].
    State {new_state}: {state_description}.
    Continuation: {continuation_hint}.

  # PostToolUse memory read context (non-WF memories)
  memory_read: |
    Session state: {current_state}. {continuation_hint}.

  # PostToolUse WM write context
  wm_write: |
    WM updated. Session state: {current_state}. Continue: {continuation_hint}.

  # Stop compliance check (used by prompt-type hook)
  stop_compliance: |
    Session {session_id} completing in state {current_state}.
    Completed steps: [{completed_steps}].
    Expected completion state: WF_DONE.
    {compliance_note}
```

### 3.2 Template Variables

All templates use `{variable}` interpolation. Variables are populated from the state store:

| Variable | Source | Example |
|---|---|---|
| `{version}` | Plugin version from plugin.json | `2.0.0` |
| `{session_id}` | Extracted from transcript_path | `00893aaf` |
| `{current_state}` | State store `current_state` | `WF_CLASSIFY` |
| `{old_state}` | Previous state (on transition) | `WF_START` |
| `{new_state}` | Target state (on transition) | `WF_CLASSIFY` |
| `{wm_status}` | WM file existence check | `exists (WM_00893aaf.md)` / `not created` |
| `{wm_file}` | WM filename | `WM_00893aaf.md` |
| `{setup_status}` | Setup complete check | `complete` / `pending` |
| `{completed_steps}` | State store `completed_steps` | `WF_INIT, WF_START` |
| `{required_steps}` | Computed from gates | `WF_INIT, WM creation` |
| `{detected_patterns}` | State store `detected_patterns` | `jira: SPS-755` / `none` |
| `{gate_name}` | Gate being evaluated | `init_gate` |
| `{gate_reason}` | Why gate is blocking | `WF_INIT not completed` |
| `{gate_requirement}` | What satisfies the gate | `read WF_INIT workflow` |
| `{gate_status}` | Gate current status | `unsatisfied` |
| `{blocked_action}` | Tool being blocked | `code research tools` |
| `{satisfied_gates}` | List of satisfied gates | `init` |
| `{state_description}` | From states.json description field | `Classify task, detect requirements...` |
| `{continuation_hint}` | From states.json metadata.continuation | `Load features, classify task type.` |
| `{compliance_note}` | Computed compliance status | `State is not WF_DONE.` |

### 3.3 Template Overrides

Users can override templates in `config/custom/context-templates.yml` (see SPEC-006). Only specified templates are overridden; others fall back to defaults.

## 4. Rewrite Rules

### 4.1 SessionStart Hook

**Current:**
```python
# Emits multi-line imperative instructions with anti-rationalization block
emit_context(f"""
🚀 SERENA WORKFLOW ENGINE v{version} - Session {session_id}
⏳ Working Memory: Not yet created
Current State: WF_INIT

STEP 1: Read WF_INIT workflow instructions
STEP 2: Follow WF_INIT to classify and execute user's task

⚠️ ANTI-RATIONALIZATION BLOCK:
❌ "This is simple" → ALL tasks go through workflow
...
""")
```

**Refactored:**
```python
context = render_template("session_start", {
    "version": version,
    "session_id": session_id,
    "current_state": state_store.current_state,
    "wm_status": "not created" if not state_store.wm_file else f"exists ({state_store.wm_file})",
    "setup_status": "complete" if setup_complete else "pending"
})
output_message(context, event="SessionStart")
```

**Output:**
```
Serena Workflow Engine v2.0.0. Session 00893aaf.
Workflow state: WF_INIT. Working Memory: not created.
Setup status: complete.
```

### 4.2 UserPromptSubmit Hook

**Current:**
```python
# Emits imperative commands with "MUST READ" instructions
# Contains anti-rationalization blocks, mandatory read lists
emit_context(f"""
MANDATORY: Read the following memories in order:
1. wf/WF_START
2. CLAUDE_OBLIGATIONS
...
""")
```

**Refactored:**
```python
context = render_template("prompt_context", {
    "session_id": session_id,
    "current_state": state_store.current_state,
    "wm_status": wm_status,
    "completed_steps": ", ".join(state_store.completed_steps),
    "required_steps": compute_required_steps(state_store),
    "detected_patterns": format_detected_patterns(state_store)
})
output_message(context, event="UserPromptSubmit")
```

**Output:**
```
Session 00893aaf state: WF_CLASSIFY.
WM: exists (WM_00893aaf.md). Completed: [WF_INIT, WF_START].
Required before task work: [feature loading, classification].
Detected: jira: SPS-755.
```

### 4.3 PreToolUse Gate Deny

**Current:**
```python
# Exit code 2 with stderr imperative
output_block(f"""
🚫 BLOCKED: Workflow not initialized.
You MUST read WF_INIT before using any tools.
This is NON-NEGOTIABLE. Read wf/WF_INIT NOW.
""")
```

**Refactored:**
```python
# permissionDecision: "deny" with factual context
result = {
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": render_template("gate_deny", {
            "gate_name": gate.name,
            "gate_reason": gate.reason,
            "gate_requirement": gate.requirement,
            "current_state": state_store.current_state,
            "satisfied_gates": ", ".join(state_store.satisfied_gates())
        }),
        "additionalContext": render_template("gate_context", {
            "session_id": session_id,
            "gate_requirement": gate.requirement,
            "blocked_action": tool_name,
            "current_state": state_store.current_state,
            "gate_name": gate.name,
            "gate_status": "unsatisfied"
        })
    }
}
```

**Output (permissionDecisionReason):**
```
init_gate: WF_INIT not completed. Required: complete WF_INIT workflow.
Session state: WF_INIT. Satisfied gates: [].
```

**Output (additionalContext):**
```
Session 00893aaf workflow requires WF_INIT completion before Grep.
Current state: WF_INIT. Gate: init_gate (unsatisfied).
```

### 4.4 PostToolUse State Transition

**Current:**
```python
# Emits imperative continuation commands
emit_context(f"""
> **{icon} On step {new_state}**
⏩ CONTINUE ({new_state}): {directive}
Do NOT stop or wait for user input. Execute the next step immediately.
""")
```

**Refactored:**
```python
context = render_template("state_transition", {
    "old_state": old_state,
    "new_state": new_state,
    "completed_steps": ", ".join(state_store.completed_steps),
    "state_description": states_config[new_state]["description"],
    "continuation_hint": states_config[new_state].get("metadata", {}).get("continuation", "")
})
output_message(context, event="PostToolUse")
```

**Output:**
```
Transition: WF_START -> WF_CLASSIFY.
Completed steps: [WF_INIT, WF_START].
State WF_CLASSIFY: Classify task, detect requirements, load features, route.
Continuation: Load features, classify task type, route to next state.
```

### 4.5 PostToolUse Continuation (non-transition)

**Current:**
```python
emit_context(f"⏩ CONTINUE ({state}): {directive}\nDo NOT stop.")
```

**Refactored:**
```python
context = render_template("memory_read", {
    "current_state": state_store.current_state,
    "continuation_hint": get_continuation_for_state(state_store.current_state)
})
output_message(context, event="PostToolUse")
```

**Output:**
```
Session state: WF_CLASSIFY. Continuation: Load features, classify task type, route to next state.
```

## 5. Anti-Rationalization: From Prose to Determinism

### 5.1 The Problem with Prose-Based Anti-Rationalization

The current system includes blocks like:
```
⚠️ ANTI-RATIONALIZATION BLOCK:
❌ "This is simple" → ALL tasks go through workflow
❌ "I know what to do" → Workflow exists for consistency
❌ "The hook allowed it" → Hook allowlist ≠ permission to skip steps
```

This is an imperative instruction that Claude's injection defenses actively resist.

### 5.2 The Deterministic Alternative

Instead of telling Claude not to rationalize, **remove the opportunity to rationalize:**

1. **PreToolUse deny** blocks tools Claude hasn't "earned" -- no prose needed
2. **State store** tracks what's actually been done -- no honor system
3. **Stop hook verification** catches any steps that were skipped

The anti-rationalization block is **deleted entirely**. Its function is replaced by:
- `swe_gate_engine.py` (SPEC-004) -- deterministically denying premature tool use
- Stop compliance hook (SPEC-007) -- verifying all steps were completed

### 5.3 Continuation Hints: Facts, Not Orders

Current: `"⏩ CONTINUE: Do NOT stop. Execute the next step immediately."`

This is an order. Replace with a factual description of what the current state entails:

Refactored: `"State WF_CLASSIFY: Classify task, detect requirements, load features, route. Continuation: Load features, classify task type, route to next state."`

Claude reads the state description and continuation hint as facts about what the state involves, not as commands about what to do. Combined with the gate engine denying premature tool use, this is sufficient to keep the workflow on track.

## 6. Context Budget

### 6.1 Character Limits

| Source | Max Characters | Notes |
|---|---|---|
| `additionalContext` total per event | 10,000 | Hard limit; excess saved to file |
| Recommended per hook | 500 | Keep total across concurrent hooks < 2,000 |
| `permissionDecisionReason` | 1,000 | Shown as tool error; keep concise |

### 6.2 Budget Allocation

For a typical PreToolUse event with gate denial:

```
permissionDecisionReason:  ~150 chars (gate name + reason + requirement)
additionalContext:         ~200 chars (session state + gate status)
Total:                     ~350 chars
```

For a typical PostToolUse state transition:

```
additionalContext:         ~250 chars (transition + state description + continuation)
Total:                     ~250 chars
```

For UserPromptSubmit:

```
additionalContext:         ~300 chars (state + WM + completed + required + detected)
Total:                     ~300 chars
```

### 6.3 Compared to Current System

The current system routinely emits 800-2000+ characters of imperative text per hook event. The refactored system targets 150-350 characters of factual state per event. This dramatically improves signal-to-noise ratio within Claude's attention window.

## 7. Context Engine Implementation

### 7.1 Module: `swe_hooks/core/context_engine.py`

```python
class ContextEngine:
    """Builds factual context strings from state and templates."""

    def __init__(self, config_dir: str):
        """Load templates from config/context-templates.yml."""
        self.templates = load_yaml(config_dir, "context-templates.yml")
        self.prefix = self.templates.get("prefix", "")

    def render(self, template_name: str, variables: dict) -> str:
        """Render a named template with variable substitution.

        Args:
            template_name: Key in templates.templates
            variables: Dict of {variable_name: value}

        Returns:
            Rendered context string, stripped and capped at 2000 chars.
        """
        template = self.templates["templates"].get(template_name, "")
        variables["prefix"] = self.prefix.format(**variables)
        result = template.format(**variables)
        return result.strip()[:2000]
```

### 7.2 Usage in Hooks

Every hook script that emits context uses the ContextEngine:

```python
from swe_hooks.core.context_engine import ContextEngine
from swe_hooks.core.state_store import StateStore

engine = ContextEngine(config_dir)
store = StateStore(session_id)

context = engine.render("prompt_context", {
    "session_id": store.session_id,
    "current_state": store.current_state,
    "wm_status": store.wm_status(),
    "completed_steps": store.completed_steps_str(),
    "required_steps": store.required_steps_str(),
    "detected_patterns": store.detected_patterns_str()
})
```

## 8. Memory File Rewrite

### 8.1 Workflow Memory Files (WF_*.md)

The WF_*.md files in `memories/wf/` currently contain imperative instructions like:

```markdown
# WF_INIT - Session Initialization

## MANDATORY FIRST ACTIONS
1. Read CLAUDE_OBLIGATIONS immediately
2. DO NOT skip any step
...
```

These files are read by Claude via `read_memory`. Since they appear as regular content (not injected context), they don't trigger injection defenses as strongly. However, they should still be rewritten for consistency:

**Before:**
```markdown
## MANDATORY FIRST ACTIONS
1. Read CLAUDE_OBLIGATIONS immediately
2. Extract session ID from your transcript path
3. Create Working Memory file
```

**After:**
```markdown
## WF_INIT Steps
- CLAUDE_OBLIGATIONS contains session behavioral requirements
- Session ID is derived from the transcript path UUID (first 8 characters)
- Working Memory file (WM_{session_id}.md) stores session context and progress
- WF_START is the next state after WF_INIT completion
```

The rewrite shifts from "you MUST do X" to "X is / X contains / X stores". Claude reads these as facts about the workflow and acts accordingly.

### 8.2 CLAUDE_OBLIGATIONS.md

This file should remain as behavioral guidelines but be reviewed for imperative overload. Keep rules that describe facts ("The workflow engine tracks state via hooks. State transitions are logged automatically.") and remove redundant enforcement prose ("You MUST NOT skip states. NEVER proceed without...").
