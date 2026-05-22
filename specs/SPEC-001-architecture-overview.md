# SPEC-001: Architecture Overview & Design Principles

**Version:** 2.0.0
**Status:** Draft
**Date:** 2026-05-20
**Scope:** Complete refactor of Serena Workflow Engine hook architecture

---

## 1. Executive Summary

This specification defines the architectural redesign of the Serena Workflow Engine (SWE) plugin for Claude Code. The refactor addresses a fundamental incompatibility: the current system writes **imperative commands** in `additionalContext` (e.g., "STOP. Read WF_INIT NOW."), which triggers Claude's prompt injection defenses and results in unreliable gate enforcement.

The new architecture shifts to:
- **Factual state descriptions** instead of imperative commands
- **Deterministic hook-based gates** instead of prose in memories
- **Declarative configuration** for states, gates, and transitions
- **User-extensible workflows** via JSON/YAML config files

## 2. Problem Statement

### 2.1 Core Issue: Imperative Context vs Prompt Injection Defenses

Claude Code's `additionalContext` mechanism is designed for factual state injection, not instructions. Per official documentation:

> "Write as factual statements: 'The deployment target is production.' Not as imperative commands (triggers prompt injection defenses)."

The current SWE plugin violates this principle throughout:

| Current Pattern (Broken) | Required Pattern (Working) |
|---|---|
| `"STOP. Your next action MUST be a tool call."` | `"Session state: WF_INIT incomplete. Working Memory not created."` |
| `"Read WF_INIT NOW before doing anything."` | `"Required before task work: WF_INIT, WM creation."` |
| `"You MUST load FEATURE_SWARM before swarm init."` | `"FEATURE_SWARM: not loaded. Swarm operations require this context."` |

### 2.2 Secondary Issues

1. **Too many imperative gates** compete for Claude's attention budget
2. **State tracked in prose** (WM markdown) rather than deterministic JSON
3. **No extensibility** -- adding a new gate requires writing Python hook code
4. **Sentinel files scattered** across `.serena/streams/` without schema
5. **Stop hook** only logs; doesn't verify compliance

### 2.3 Critical Platform Constraint: VSCode Extension

**Hooks configured in `settings.json` do NOT fire in the VSCode extension.** However, plugin hooks (configured in `hooks/hooks.json` within the plugin directory) operate through the plugin system and should be verified during implementation. If plugin hooks also do not fire in VSCode extension mode, this must be addressed by:
- Documenting CLI-only requirement for hook-gated workflows
- Providing a graceful degradation path (CLAUDE.md-based instructions as fallback)
- Investigating MCP-tool-based alternatives that work in both modes

## 3. Design Principles

### 3.1 Facts, Not Commands

All `additionalContext` output MUST be written as factual statements describing current state, never as imperative instructions.

**Pattern:**
```
Session {id} workflow state: {state}.
Working Memory: {exists|not created}.
Completed steps: [{list}].
Required before {action}: [{list}].
Detected patterns: [{list}].
```

### 3.2 Deterministic Gates, Not Prose

Blocking decisions are made by **hook code reading JSON state files**, not by Claude interpreting prose in memory files. A gate either denies a tool call or allows it -- there is no "Claude, please don't do this" middle ground.

### 3.3 Declarative Over Procedural

New gates, states, and transitions are defined in configuration files (JSON/YAML), not by writing Python hook scripts. The hook scripts become a generic **gate engine** that reads config and makes decisions.

### 3.4 Minimal Context, Maximum Signal

Each hook injects the minimum context needed. The total `additionalContext` across all hooks for a single event should stay well under 2,000 characters (hard limit is 10,000 but attention degrades long before).

### 3.5 Fail Closed, Degrade Gracefully

- If state file is missing or corrupt: deny tool use, inject state describing the problem
- If config is invalid: fall back to built-in defaults
- If hook times out: allow operation (avoid blocking the user indefinitely)

## 4. Architecture Overview

### 4.1 Component Diagram

```
                    +--------------------------+
                    |   User-Defined Config    |
                    |  (YAML/JSON)             |
                    |                          |
                    |  workflows/*.yml         |
                    |  gates/*.yml             |
                    |  states.json             |
                    +-----------+--------------+
                                |
                    +-----------v--------------+
                    |    Configuration Loader   |
                    |    (validates + merges)    |
                    +-----------+--------------+
                                |
              +-----------------+------------------+
              |                 |                   |
    +---------v------+  +------v--------+  +-------v--------+
    |  Gate Engine    |  | State Engine  |  | Context Engine |
    |                 |  |               |  |                |
    | Reads gates.yml |  | Reads state   |  | Builds factual |
    | Evaluates       |  | Validates     |  | context from   |
    | conditions      |  | transitions   |  | current state  |
    | Returns deny/   |  | Persists to   |  | Returns string |
    | allow           |  | state file    |  |                |
    +---------+------+  +------+--------+  +-------+--------+
              |                 |                   |
    +---------v-----------------v-------------------v--------+
    |                    Hook Dispatcher                      |
    |                                                         |
    |  SessionStart  -> Context Engine                        |
    |  UserPromptSubmit -> Context Engine + Gate Engine        |
    |  PreToolUse -> Gate Engine + Context Engine              |
    |  PostToolUse -> State Engine + Context Engine            |
    |  Stop -> Compliance Verifier (prompt/agent hook)        |
    +---------------------------------------------------------+
              |
    +---------v-------------------------------------------------+
    |                   State Store                              |
    |                                                            |
    |  .serena/swe-state/{session_id}.json  (authoritative)     |
    |  .serena/swe-state/{session_id}.gates.json (gate status)  |
    |  .serena/streams/{session_id}.jsonl   (audit log)         |
    +---------------------------------------------------------+
```

### 4.2 State Store (Replaces Sentinel Files + WM State Parsing)

A single JSON file per session replaces the current scattered sentinel files:

```json
{
  "session_id": "00893aaf",
  "current_state": "WF_CLASSIFY",
  "previous_state": "WF_START",
  "created_at": "2026-05-20T10:30:00Z",
  "updated_at": "2026-05-20T10:35:00Z",
  "wm_file": "WM_00893aaf.md",
  "completed_steps": ["WF_INIT", "WF_START"],
  "gates_satisfied": {
    "init": true,
    "feature_swarm": false,
    "feature_tests": false,
    "jira_fetch": false
  },
  "detected_patterns": {
    "jira_tickets": ["SPS-755"],
    "swarm_keywords": false,
    "test_patterns": false
  },
  "edits_since_checkpoint": 0,
  "plan_mode": false
}
```

### 4.3 Hook Count Reduction

| Current (v1) | Refactored (v2) |
|---|---|
| `swe_session_start.py` | `swe_session_start.py` (simplified: init state store, emit facts) |
| `swe_user_prompt_workflow.py` | `swe_prompt_context.py` (merged: emit state facts + detect patterns) |
| `swe_user_prompt_swarm.py` | *(merged into above)* |
| `swe_pre_tool_init_gate.py` | `swe_gate_engine.py` (generic: reads gates.yml, evaluates all gates) |
| `swe_pre_swarm_feature_gate.py` | *(handled by gate engine)* |
| `swe_pre_bash_test_gate.py` | *(handled by gate engine)* |
| `swe_post_read_state.py` | `swe_state_transition.py` (simplified: update state store, emit facts) |
| `swe_post_write_continue.py` | `swe_post_context.py` (merged: continuation facts) |
| `swe_post_todo_wm_sync.py` | *(kept as-is, orthogonal concern)* |
| `swe_stop_workflow_check.py` | **prompt-type hook** in hooks.json (LLM verification) |

**Result:** 10 scripts -> 5 scripts + 1 prompt hook

## 5. File Structure (v2)

```
serena-workflow-engine/
  specs/                          # This spec set
  config/                         # NEW: Declarative configuration
    states.json                   # State machine definition (moved)
    gates.yml                     # Gate definitions (NEW)
    workflows.yml                 # Workflow path definitions (NEW)
    context-templates.yml         # Context output templates (NEW)
    schema/                       # JSON Schema for validation
      states.schema.json
      gates.schema.json
      workflows.schema.json
  hooks/
    hooks.json                    # Hook event wiring (simplified)
    swe_hooks/
      core/
        config_loader.py          # NEW: loads + validates YAML/JSON config
        gate_engine.py            # NEW: generic gate evaluator
        state_engine.py           # REFACTORED from state_manager.py
        context_engine.py         # NEW: builds factual context strings
        state_store.py            # NEW: JSON state file I/O
        session.py                # KEPT: session ID extraction
        stream.py                 # KEPT: JSONL audit log
        input.py                  # KEPT: stdin parsing
        output.py                 # KEPT: hook output formatting
      session/
        swe_session_start.py      # SIMPLIFIED
      prompt/
        swe_prompt_context.py     # MERGED from 2 scripts
      pre/
        swe_gate_engine.py        # NEW: replaces 3 gate scripts
      post/
        swe_state_transition.py   # REFACTORED
        swe_post_context.py       # MERGED
        swe_post_todo_wm_sync.py  # KEPT
      stop/                       # REMOVED (replaced by prompt hook)
  memories/                       # KEPT: Serena memory files
  state-machine/                  # DEPRECATED (moved to config/)
  ...
```

## 6. Spec Document Index

| Spec | Title | Scope |
|---|---|---|
| SPEC-001 | Architecture Overview (this document) | System design, principles, structure |
| SPEC-002 | Declarative State Machine Schema | State/transition config format, validation |
| SPEC-003 | Factual Context Pattern | How all context output is rewritten |
| SPEC-004 | Gate Engine | Declarative blocking system with conditions |
| SPEC-005 | Session & State Management | State store, session isolation, WM interaction |
| SPEC-006 | User-Defined Extensions | YAML/JSON config for custom gates/states |
| SPEC-007 | Stop Hook Compliance Verification | Prompt/agent-based compliance checking |
| SPEC-008 | Migration & Compatibility | Incremental migration from v1 to v2 |

## 7. Non-Goals

- **Replacing Serena MCP:** The memory system stays. WM files remain the user-facing artifact.
- **Changing the 15-state model:** States are kept. Only the enforcement mechanism changes.
- **Supporting non-Claude-Code environments:** This is Claude Code plugin only.
- **Real-time UI:** No dashboard or monitoring UI changes in this refactor.

## 8. Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| Plugin hooks don't fire in VSCode extension | Critical -- gates don't work | Verify early; document CLI requirement; provide CLAUDE.md fallback |
| Factual context still ignored by Claude | High -- workflow not followed | Combine with deterministic PreToolUse deny; use Stop hook as safety net |
| Config complexity overwhelms users | Medium -- adoption friction | Provide sane defaults; only require config for custom gates |
| Migration breaks existing installations | High -- user trust | Incremental migration with v1 compatibility shim (SPEC-008) |
| Hook timeout under load | Medium -- gates silently fail | Keep hook logic fast (<2s); use cached state files |
