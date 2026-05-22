# SPEC-007: Stop Hook Compliance Verification

**Version:** 2.0.0
**Status:** Draft
**Date:** 2026-05-20
**Depends on:** SPEC-001, SPEC-005

---

## 1. Purpose

Replace the current Stop hook (which only logs interrupted states) with a compliance verification system that can **force Claude to continue** if required workflow steps were skipped. This is the safety net behind the gate engine.

## 2. Current Problem

The current `swe_stop_workflow_check.py` detects incomplete states and logs them to the stream, but it does not prevent Claude from stopping. Claude can finish a response without completing the workflow.

## 3. Claude Code Stop Hook Capabilities

From the official documentation:

- **Exit code 2** from a Stop hook **blocks Claude from stopping** and forces it to continue
- **`decision: "block"`** in JSON output has the same effect
- **`reason`** field provides text that Claude receives as its next instruction
- **`additionalContext`** provides factual context alongside the block decision

This means the Stop hook can enforce workflow completion by blocking the stop when the session is in an incomplete state.

## 4. Approach: Prompt-Type Hook for Compliance

### 4.1 Why Prompt, Not Command

A simple command hook can check the state store and block if state != WF_DONE. But this is too rigid -- it would block Claude from stopping even when the user explicitly says "stop" or "never mind."

A **prompt-type hook** uses a fast LLM (Haiku) to evaluate whether stopping is appropriate given the context. This provides:
- Judgment about user intent ("stop" vs premature completion)
- Ability to assess partial completion
- Natural language reasoning about compliance

### 4.2 Why Not Agent Type

An agent-type hook spawns a full subagent with tool access. This is overkill for compliance checking -- the state store JSON file contains all needed information. A prompt hook is faster (~1-2s vs ~10-30s) and cheaper.

## 5. Implementation

### 5.1 Hook Configuration: `hooks/hooks.json`

```json
{
  "Stop": [
    {
      "hooks": [
        {
          "type": "command",
          "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/stop/swe_stop_compliance.py",
          "timeout": 5
        }
      ]
    }
  ]
}
```

### 5.2 Command Hook Logic

The Stop hook reads the state store and decides whether to block:

```python
#!/usr/bin/env python3
"""Stop hook: verify workflow compliance before allowing stop.

Reads session state store and blocks stopping if workflow
is in an incomplete state that wasn't explicitly abandoned.
"""
import json, sys, os
from swe_hooks.core.input import read_stdin_safe
from swe_hooks.core.session import extract_session_id
from swe_hooks.core.state_store import StateStore
from swe_hooks.core.stream import append_event, get_stream_path

# States where stopping is acceptable
TERMINAL_STATES = {"WF_DONE"}
# States where stopping is acceptable (informational work)
SAFE_STOP_STATES = {"WF_RESEARCH", "WF_CLARIFY", "WF_INIT"}
# States where stopping means incomplete work
INCOMPLETE_STATES = {
    "WF_EXECUTE", "WF_ARCH_REVIEW", "WF_VERIFY",
    "WF_DEBUG_TDD", "WF_CHECKPOINT", "WF_CLASSIFY"
}

def main():
    data = read_stdin_safe()
    if not data:
        print(json.dumps({}))
        sys.exit(0)

    session_id = extract_session_id(data.get("transcript_path", ""))
    if not session_id:
        print(json.dumps({}))
        sys.exit(0)

    store = StateStore(session_id)
    current = store.current_state

    # Terminal or safe states: allow stop
    if current in TERMINAL_STATES or current in SAFE_STOP_STATES:
        # Log completion
        if current in TERMINAL_STATES:
            stream = get_stream_path(session_id)
            append_event(stream, "session_complete", state=current)
        print(json.dumps({}))
        sys.exit(0)

    # Incomplete states: block with factual context
    if current in INCOMPLETE_STATES:
        completed = ", ".join(store.completed_steps) or "none"
        result = {
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "decision": "block",
                "reason": (
                    f"Session {session_id} workflow state: {current}. "
                    f"Completed steps: [{completed}]. "
                    f"Expected terminal state: WF_DONE. "
                    f"Current state {current} indicates incomplete work."
                ),
                "additionalContext": (
                    f"Session {session_id} attempting to stop in state {current}. "
                    f"Workflow has not reached WF_DONE. "
                    f"Completed: [{completed}]. "
                    f"If the task is genuinely complete, transition to WF_VERIFY then WF_DONE. "
                    f"If the user explicitly requested stopping, acknowledge incomplete state."
                )
            }
        }
        # Log interruption
        stream = get_stream_path(session_id)
        append_event(stream, "interrupted", state=current)
        print(json.dumps(result))
        sys.exit(0)

    # Unknown state: allow stop (don't trap the user)
    print(json.dumps({}))
    sys.exit(0)

if __name__ == "__main__":
    main()
```

### 5.3 Key Design Decisions

**Why factual `reason` text, not imperative:**

Instead of: `"You MUST complete the workflow. Go to WF_VERIFY NOW."`

We use: `"Session state: WF_EXECUTE. Completed: [WF_INIT, WF_START, WF_CLASSIFY, WF_ARCH_REVIEW]. Expected terminal: WF_DONE. Current state indicates incomplete work."`

The reason text is delivered to Claude as the next prompt context. Factual state description lets Claude determine the appropriate action without triggering injection defenses.

**Why command hook (not prompt/agent):**

The compliance check is deterministic: compare `current_state` against known terminal states. No LLM judgment needed. This keeps the Stop hook fast (~10ms) and reliable.

**When NOT to block:**

- `WF_INIT` -- session was never started; don't trap Claude in a loop
- `WF_RESEARCH` -- informational work that may be complete at any point
- `WF_CLARIFY` -- waiting for user input; stopping is the correct behavior
- Unknown/missing state -- fail open to avoid trapping the user

## 6. Enhanced Compliance: Prompt-Type Verification (Optional)

For teams that want deeper compliance checking, a prompt-type hook can be added as a secondary check:

### 6.1 Configuration

```json
{
  "Stop": [
    {
      "hooks": [
        {
          "type": "command",
          "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/stop/swe_stop_compliance.py",
          "timeout": 5
        },
        {
          "type": "prompt",
          "prompt": "Review the session state. Current state: $ARGUMENTS. Should the session be allowed to stop? Respond with {\"decision\": \"allow\"} if the work appears complete or the user requested stopping, or {\"decision\": \"block\", \"reason\": \"<why>\"} if critical work is incomplete.",
          "timeout": 15,
          "statusMessage": "Checking workflow compliance..."
        }
      ]
    }
  ]
}
```

### 6.2 How Prompt Hooks Work

1. The command hook runs first (fast, deterministic)
2. If the command hook allows the stop, the prompt hook runs
3. The prompt hook receives session context via `$ARGUMENTS` (substituted with hook input)
4. A fast model (Haiku by default) evaluates compliance
5. If it returns `decision: "block"`, Claude is forced to continue

### 6.3 When to Use Prompt Hooks

Prompt hooks are slower (~3-5s) and consume API tokens. They're appropriate when:
- The team has strict compliance requirements (e.g., Jira ticket must be fetched)
- The state alone is insufficient (e.g., need to verify specific actions were taken)
- False positives from the command hook are a problem

For most users, the command hook alone is sufficient.

## 7. Compliance Reporting

### 7.1 Session Summary on WF_DONE

When the session reaches WF_DONE, the Stop hook can emit a completion summary:

```python
if current in TERMINAL_STATES:
    summary = {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": (
                f"Session {session_id} complete. "
                f"States visited: [{', '.join(store.completed_steps)}]. "
                f"Total transitions: {store.data['counters']['total_transitions']}. "
                f"Total edits: {store.data['counters']['total_edits']}."
            )
        }
    }
    print(json.dumps(summary))
```

### 7.2 Stream Event Logging

All Stop events are logged to the JSONL stream:

```json
{"t": 1716220500, "type": "session_complete", "state": "WF_DONE", "s": "00893aaf"}
{"t": 1716220500, "type": "interrupted", "state": "WF_EXECUTE", "s": "00893aaf"}
```

## 8. User Configuration

### 8.1 Customizing Compliance Rules

Users can customize which states are safe to stop in via `config/workflows.yml`:

```yaml
compliance:
  terminal_states:
    - WF_DONE
  safe_stop_states:
    - WF_RESEARCH
    - WF_CLARIFY
    - WF_INIT
    - WFX_CUSTOM_TERMINAL    # User-defined safe stop state

  # Optional: require specific gates before allowing stop
  required_gates_for_stop:
    - init

  # Optional: enable prompt-type verification
  prompt_verification: false
```

### 8.2 Disabling Compliance

Users who find the Stop hook too aggressive can disable it:

```yaml
# .serena/config/workflows.yml
compliance:
  enabled: false    # Disable Stop hook compliance checking
```

Or in the hook config:
```json
{
  "Stop": []    # No stop hooks
}
```

## 9. Edge Cases

### 9.1 Repeated Blocking

If the Stop hook blocks and Claude can't figure out how to proceed, it may try to stop again, creating a loop. Mitigation:

```python
# Track block count in state store
block_count = store.get_custom("stop_block_count", 0)
if block_count >= 3:
    # Allow stop after 3 blocks to prevent infinite loop
    store.set_custom("stop_block_count", 0)
    print(json.dumps({}))
    sys.exit(0)

store.set_custom("stop_block_count", block_count + 1)
```

### 9.2 User Explicitly Says "Stop"

The command hook cannot detect user intent (it only sees state). If the user says "stop" or "cancel", Claude should transition to WF_DONE (or at least WF_CLARIFY) before the Stop hook fires. The UserPromptSubmit hook can help by detecting cancellation patterns and transitioning state.

### 9.3 Error States

If the state store is corrupt or unreadable, the Stop hook allows the stop (fail open). Never trap the user in an unrecoverable loop.
