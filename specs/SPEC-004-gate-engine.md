# SPEC-004: Gate Engine - Declarative Blocking System

**Version:** 2.0.0
**Status:** Draft
**Date:** 2026-05-20
**Depends on:** SPEC-001, SPEC-002, SPEC-003

---

## 1. Purpose

Replace the current three separate PreToolUse gate scripts (`swe_pre_tool_init_gate.py`, `swe_pre_swarm_feature_gate.py`, `swe_pre_bash_test_gate.py`) with a single **Gate Engine** that reads declarative gate definitions from `config/gates.yml` and evaluates them against the session state store.

This enables users to add new blocking gates without writing Python code.

## 2. Current Problem

### 2.1 Three Separate Gate Scripts

Each gate is a separate Python file with bespoke logic:
- **Init gate:** Checks sentinel file existence, has hardcoded tool allowlist
- **Swarm gate:** Checks swarm sentinel file, blocks only `swarm_init` tool
- **Test gate:** Regex-matches test commands in Bash, checks test sentinel file

### 2.2 Issues

1. **Adding a new gate requires writing Python** -- high barrier for users
2. **Sentinel files scattered** -- `.serena/streams/.init_{id}`, `.swarm_feature_{id}`, `.test_feature_{id}`
3. **Hardcoded allowlists** -- init gate has inline list of allowed tools/memories
4. **No composability** -- gates can't depend on each other or share conditions
5. **Imperative deny reasons** -- "You MUST read WF_INIT" instead of factual state

## 3. Gate Configuration Schema

### 3.1 Gate Definition: `config/gates.yml`

```yaml
version: "2.0.0"

gates:

  # ── INIT GATE ──────────────────────────────────────────────
  init:
    name: "Workflow Initialization"
    description: "Blocks all non-bootstrap tools until WF_INIT is complete"
    priority: 0          # Lower = evaluated first
    enabled: true

    # When this gate applies (tool matcher)
    matcher: ".*"        # All tools

    # Tools EXEMPT from this gate (allowed even when gate is unsatisfied)
    exempt:
      tools:
        - "ToolSearch"
        - "mcp__serena__write_memory"
        - "mcp__plugin_swe_serena__write_memory"
        - "mcp__serena__edit_memory"
        - "mcp__plugin_swe_serena__edit_memory"
        - "mcp__serena__activate_project"
        - "mcp__plugin_swe_serena__activate_project"
        - "mcp__serena__list_projects"
        - "mcp__plugin_swe_serena__list_projects"
      # Exempt specific read_memory calls by input pattern
      tool_inputs:
        - tool: "mcp__serena__read_memory|mcp__plugin_swe_serena__read_memory"
          field: "memory_name"
          pattern: "^(wf/WF_INIT|wf/WF_START|claude/CLAUDE_OBLIGATIONS|claude/CLAUDE|claude/CLAUDE_META|ref/REF_WM)$"

    # Condition that satisfies (clears) this gate
    satisfied_when:
      state_field: "gates_satisfied.init"
      equals: true

    # What satisfies the gate (for state engine to set)
    satisfied_by:
      event: "state_transition"
      condition:
        new_state_in: ["WF_START", "WF_CLASSIFY", "WF_RESEARCH", "WF_CONTINUE"]

    # Deny response (factual, not imperative)
    deny:
      reason: >
        init gate: WF_INIT workflow not completed.
        Required: WF_INIT completion and Working Memory creation.
      context: >
        Session {session_id} workflow state: {current_state}.
        Gate init (unsatisfied). No tools available until workflow initialization completes.
        Satisfied gates: [{satisfied_gates}].

  # ── FEATURE SWARM GATE ─────────────────────────────────────
  feature_swarm:
    name: "Swarm Feature Loading"
    description: "Blocks swarm tools until FEATURE_SWARM is loaded"
    priority: 10
    enabled: true

    matcher: "mcp__ruv-swarm__swarm_init"

    depends_on:
      - init      # Init gate must be satisfied first

    satisfied_when:
      state_field: "gates_satisfied.feature_swarm"
      equals: true

    satisfied_by:
      event: "memory_read"
      condition:
        memory_name: "feature/FEATURE_SWARM"

    deny:
      reason: >
        feature_swarm gate: FEATURE_SWARM context not loaded.
        Required: read FEATURE_SWARM memory before swarm initialization.
      context: >
        Session {session_id} state: {current_state}.
        Swarm initialization requires FEATURE_SWARM context for orchestration patterns.
        Gate: feature_swarm (unsatisfied).

  # ── FEATURE TESTS GATE ─────────────────────────────────────
  feature_tests:
    name: "Test Feature Loading"
    description: "Blocks test execution until FEATURE_TESTS is loaded"
    priority: 10
    enabled: true

    matcher: "Bash"

    # Additional input filtering (only block test commands)
    input_filter:
      field: "command"
      pattern: "(npx\\s+playwright|jest|vitest|pytest|npm\\s+test|yarn\\s+test|pnpm\\s+test)"

    depends_on:
      - init

    satisfied_when:
      state_field: "gates_satisfied.feature_tests"
      equals: true

    satisfied_by:
      event: "memory_read"
      condition:
        memory_name_pattern: ".*FEATURE_TESTS.*"

    deny:
      reason: >
        feature_tests gate: FEATURE_TESTS context not loaded.
        Required: read FEATURE_TESTS memory before running tests.
      context: >
        Session {session_id} state: {current_state}.
        Test execution requires FEATURE_TESTS for project-specific test configuration.
        Gate: feature_tests (unsatisfied).
```

### 3.2 Field Reference

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Human-readable gate name |
| `description` | string | Yes | What this gate protects |
| `priority` | integer | No | Evaluation order (lower = first). Default: 50 |
| `enabled` | boolean | No | Whether gate is active. Default: true |
| `matcher` | string | Yes | Tool name pattern (same syntax as hooks.json matcher) |
| `exempt.tools` | string[] | No | Tool names exempt from this gate |
| `exempt.tool_inputs` | object[] | No | Tool+input combinations exempt from this gate |
| `input_filter` | object | No | Additional filter on tool input (e.g., command pattern) |
| `depends_on` | string[] | No | Gate IDs that must be satisfied first |
| `satisfied_when` | object | Yes | Condition in state store that marks gate as satisfied |
| `satisfied_by` | object | Yes | Event that satisfies the gate (used by state engine) |
| `deny.reason` | string | Yes | `permissionDecisionReason` text (supports `{variables}`) |
| `deny.context` | string | No | `additionalContext` text (supports `{variables}`) |

### 3.3 Condition Types for `satisfied_when`

```yaml
# Simple field check
satisfied_when:
  state_field: "gates_satisfied.init"
  equals: true

# State check
satisfied_when:
  state_field: "current_state"
  in: ["WF_EXECUTE", "WF_VERIFY", "WF_DONE"]

# Completed steps check
satisfied_when:
  state_field: "completed_steps"
  contains: "WF_CLASSIFY"

# Multiple conditions (AND)
satisfied_when:
  all:
    - state_field: "gates_satisfied.init"
      equals: true
    - state_field: "current_state"
      not_in: ["WF_INIT"]
```

### 3.4 Event Types for `satisfied_by`

```yaml
# Satisfied by reaching a state
satisfied_by:
  event: "state_transition"
  condition:
    new_state_in: ["WF_START", "WF_CLASSIFY"]

# Satisfied by reading a specific memory
satisfied_by:
  event: "memory_read"
  condition:
    memory_name: "feature/FEATURE_SWARM"

# Satisfied by reading a memory matching a pattern
satisfied_by:
  event: "memory_read"
  condition:
    memory_name_pattern: ".*FEATURE_TESTS.*"

# Satisfied by a tool completing successfully
satisfied_by:
  event: "tool_success"
  condition:
    tool_name: "mcp__jira__get_issue"

# Satisfied by a custom flag being set
satisfied_by:
  event: "flag_set"
  condition:
    flag: "jira_fetched"
```

## 4. Gate Engine Implementation

### 4.1 Module: `swe_hooks/core/gate_engine.py`

```python
class GateEngine:
    """Evaluates declarative gate definitions against session state."""

    def __init__(self, config_dir: str):
        """Load gate definitions from config/gates.yml."""
        self.gates = load_gates(config_dir)

    def evaluate(self, tool_name: str, tool_input: dict,
                 state_store: StateStore) -> GateResult:
        """Evaluate all applicable gates for a tool call.

        Args:
            tool_name: The tool being called
            tool_input: The tool's input parameters
            state_store: Current session state

        Returns:
            GateResult with allow/deny decision and context
        """
        for gate in sorted(self.gates, key=lambda g: g.priority):
            if not gate.enabled:
                continue
            if not gate.matches_tool(tool_name):
                continue
            if gate.is_exempt(tool_name, tool_input):
                continue
            if gate.has_input_filter() and not gate.matches_input(tool_input):
                continue
            if not gate.is_satisfied(state_store):
                # Check dependencies
                for dep_id in gate.depends_on:
                    dep_gate = self.get_gate(dep_id)
                    if dep_gate and not dep_gate.is_satisfied(state_store):
                        # Dependency not met -- block with dependency info
                        return GateResult.deny(dep_gate, state_store)
                return GateResult.deny(gate, state_store)

        return GateResult.allow()
```

### 4.2 GateResult

```python
@dataclass
class GateResult:
    allowed: bool
    gate_name: str = None
    reason: str = None       # For permissionDecisionReason
    context: str = None      # For additionalContext

    @classmethod
    def allow(cls):
        return cls(allowed=True)

    @classmethod
    def deny(cls, gate, state_store):
        variables = state_store.to_template_vars()
        variables["gate_name"] = gate.name
        variables["gate_status"] = "unsatisfied"
        return cls(
            allowed=False,
            gate_name=gate.id,
            reason=gate.deny_reason.format(**variables),
            context=gate.deny_context.format(**variables) if gate.deny_context else None
        )
```

### 4.3 Hook Script: `hooks/pre/swe_gate_engine.py`

```python
#!/usr/bin/env python3
"""Generic gate engine for PreToolUse events.

Reads gate definitions from config/gates.yml and evaluates
against session state store. Replaces all bespoke gate scripts.
"""
import json, sys
from swe_hooks.core.input import read_stdin_safe
from swe_hooks.core.session import extract_session_id
from swe_hooks.core.state_store import StateStore
from swe_hooks.core.gate_engine import GateEngine
from swe_hooks.core.output import output_empty

def main():
    data = read_stdin_safe()
    if not data:
        output_empty()
        return

    session_id = extract_session_id(data.get("transcript_path", ""))
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    store = StateStore(session_id)
    engine = GateEngine(config_dir)

    result = engine.evaluate(tool_name, tool_input, store)

    if result.allowed:
        output_empty()
    else:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": result.reason
            }
        }
        if result.context:
            output["hookSpecificOutput"]["additionalContext"] = result.context
        print(json.dumps(output))
        sys.exit(0)

if __name__ == "__main__":
    main()
```

### 4.4 Hook Wiring: `hooks/hooks.json`

The three separate PreToolUse entries are replaced by one:

```json
{
  "PreToolUse": [
    {
      "matcher": ".*",
      "hooks": [
        {
          "type": "command",
          "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/pre/swe_gate_engine.py",
          "timeout": 5
        }
      ]
    }
  ]
}
```

## 5. User-Defined Gates

### 5.1 Adding a Custom Gate

Users create `config/custom/gates.yml` with additional gate definitions:

```yaml
gates:
  # Block code changes until Jira ticket is fetched
  jira_fetch:
    name: "Jira Context Loading"
    description: "Blocks code research tools until detected Jira ticket is fetched"
    priority: 5
    enabled: true

    matcher: "Grep|Glob|Read|Agent"

    # Only activate when Jira tickets are detected
    active_when:
      state_field: "detected_patterns.jira_tickets"
      not_empty: true

    satisfied_when:
      state_field: "gates_satisfied.jira_fetch"
      equals: true

    satisfied_by:
      event: "tool_success"
      condition:
        tool_name_pattern: ".*jira.*|Bash"
        output_contains: "SPS-"

    deny:
      reason: >
        jira_fetch gate: Jira ticket {detected_jira} detected in task.
        Required: fetch Jira ticket context before code research.
      context: >
        Session {session_id} state: {current_state}.
        Jira issue {detected_jira} was detected. Project policy requires
        fetching ticket context (scope, reproduction steps, prior fixes)
        before beginning code research.

  # Block deployment commands until tests pass
  test_pass:
    name: "Test Verification"
    description: "Blocks deployment until tests have passed"
    priority: 20
    enabled: true

    matcher: "Bash"

    input_filter:
      field: "command"
      pattern: "(deploy|publish|release|push)"

    active_when:
      state_field: "current_state"
      in: ["WF_VERIFY", "WF_DONE"]

    satisfied_when:
      state_field: "gates_satisfied.test_pass"
      equals: true

    satisfied_by:
      event: "tool_success"
      condition:
        tool_name: "Bash"
        input_pattern: "(test|spec|check)"
        exit_code: 0

    deny:
      reason: >
        test_pass gate: Tests must pass before deployment.
        Required: run and pass test suite.
      context: >
        Session {session_id} state: {current_state}.
        Deployment commands require prior successful test execution.
```

### 5.2 Gate Composition

Gates can reference other gates in `depends_on`:

```yaml
gates:
  security_scan:
    depends_on:
      - init
      - feature_tests    # Tests must be loadable first
    # ...
```

If a dependency is unsatisfied, the dependent gate's deny message is shown with the dependency chain.

### 5.3 Conditional Activation

Gates can have `active_when` conditions that determine whether the gate is even evaluated:

```yaml
active_when:
  state_field: "detected_patterns.jira_tickets"
  not_empty: true
```

If `active_when` evaluates to false, the gate is skipped entirely (as if it doesn't exist). This is different from `satisfied_when` -- an inactive gate doesn't block anything.

## 6. Gate Satisfaction Flow

### 6.1 How Gates Get Satisfied

The **State Engine** (SPEC-005) is responsible for marking gates as satisfied in the state store. The flow:

1. An event occurs (state transition, memory read, tool success)
2. State Engine checks all gate `satisfied_by` conditions
3. If a condition matches, the corresponding `gates_satisfied.{gate_id}` field is set to `true` in the state store
4. Next time Gate Engine evaluates, the gate's `satisfied_when` check passes

### 6.2 Gate Reset

Gates can be reset (re-locked) by:
- Session reset (new session always starts with all gates unsatisfied)
- State transition to WF_CLASSIFY from WF_DONE (new task in same session)
- Explicit config: `reset_on` field

```yaml
gates:
  jira_fetch:
    # Reset when a new task begins in the same session
    reset_on:
      event: "state_transition"
      condition:
        new_state: "WF_CLASSIFY"
        from_state: "WF_DONE"
```

## 7. Performance Considerations

### 7.1 Gate Evaluation Speed

The gate engine must complete within the 5-second hook timeout. Target: <100ms.

- **State store read:** Single JSON file read (~1ms)
- **Gate config:** Cached after first load (~0ms after first call)
- **Evaluation:** Linear scan of ~3-10 gates with simple field checks (~1ms)
- **Template rendering:** String format with ~5 variables (~0ms)

### 7.2 Caching

- Gate definitions: Loaded once per process, cached in module-level variable
- State store: Read fresh each invocation (must reflect latest state)
- No file-watching needed (hooks are short-lived processes)

## 8. Validation

The config loader validates gates.yml on load:

1. **Unique IDs:** No duplicate gate IDs
2. **Valid matchers:** Matcher patterns must be valid regex or tool names
3. **Valid references:** `depends_on` must reference existing gate IDs
4. **No circular dependencies:** Dependency graph must be a DAG
5. **Valid state fields:** `state_field` paths must be valid JSON paths
6. **Template variables:** `{variables}` in deny strings must be resolvable
