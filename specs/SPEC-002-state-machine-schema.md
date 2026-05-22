# SPEC-002: Declarative State Machine Schema

**Version:** 2.0.0
**Status:** Draft
**Date:** 2026-05-20
**Depends on:** SPEC-001

---

## 1. Purpose

Define the configuration schema for the workflow state machine, enabling users to:
- Modify existing states (icons, descriptions, transitions)
- Add new custom states
- Define transition rules declaratively
- Configure state-level behaviors (plan mode, edit permissions)

## 2. Current State (v1)

The current `state-machine/states.json` serves dual purposes:
1. State definitions with metadata (icons, descriptions, permissions)
2. Transition matrix (which states can follow which)

**Problems:**
- Hardcoded state behaviors in Python (PLAN_MODE_STATES, EXIT_PLAN_MODE_STATES constants)
- No schema validation
- No support for user-defined custom states
- Complexity thresholds are unused in practice
- State icons duplicated in `state_manager.py`

## 3. New Schema: `config/states.json`

### 3.1 Top-Level Structure

```json
{
  "$schema": "./schema/states.schema.json",
  "version": "2.0.0",
  "description": "Serena Workflow Engine state machine definition",

  "defaults": {
    "planMode": "never",
    "allowEdit": false,
    "allowWrite": false,
    "timeout": null
  },

  "categories": {
    "setup":      { "label": "Setup",      "order": 0 },
    "entry":      { "label": "Entry",      "order": 1 },
    "analysis":   { "label": "Analysis",   "order": 2 },
    "planning":   { "label": "Planning",   "order": 3 },
    "gates":      { "label": "Gates",      "order": 4 },
    "execution":  { "label": "Execution",  "order": 5 },
    "completion": { "label": "Completion", "order": 6 }
  },

  "states": { },

  "transitionMatrix": { },

  "hooks": {
    "onEnter": { },
    "onExit": { }
  }
}
```

### 3.2 State Definition Schema

Each state in the `states` object:

```json
{
  "WF_CLASSIFY": {
    "id": "WF_CLASSIFY",
    "category": "entry",
    "icon": "🔍",
    "label": "Classify",
    "description": "Classify task, detect requirements, load features, route",

    "planMode": "conditional",
    "allowEdit": false,
    "allowWrite": false,

    "terminal": false,

    "contextTemplate": "classify",

    "transitions": {
      "code_changes": "WF_ARCH_REVIEW",
      "operational": "WF_EXECUTE",
      "research_needed": "WF_RESEARCH",
      "debug_needed": "WF_DEBUG_TDD",
      "needs_clarification": "WF_CLARIFY"
    },

    "requiredGates": [],

    "metadata": {
      "continuation": "Load features, classify task type, route to next state."
    }
  }
}
```

### 3.3 Field Definitions

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Yes | Unique state identifier. Must match the key. |
| `category` | string | Yes | Must be a key in `categories`. |
| `icon` | string | Yes | Emoji icon for display. |
| `label` | string | No | Short human-readable label. Defaults to id. |
| `description` | string | Yes | Purpose of this state. |
| `planMode` | `"never"` \| `"always"` \| `"conditional"` | No | When plan mode is activated. Default: `"never"`. |
| `allowEdit` | boolean | No | Whether file edits are permitted. Default: `false`. |
| `allowWrite` | boolean | No | Whether file writes are permitted. Default: `false`. |
| `terminal` | boolean | No | Whether this is a terminal state. Default: `false`. |
| `contextTemplate` | string | No | Reference to a template in `context-templates.yml`. |
| `transitions` | object | Yes | Map of transition labels to target state IDs. |
| `requiredGates` | string[] | No | Gate IDs that must be satisfied before entering this state. |
| `metadata.continuation` | string | No | Factual continuation hint for this state. |

### 3.4 Transition Matrix

The transition matrix is auto-derived from state definitions but can be explicitly overridden:

```json
{
  "transitionMatrix": {
    "WF_START": ["WF_CLASSIFY", "WF_CONTINUE", "WF_RESEARCH", "WF_ONBOARD"],
    "WF_CLASSIFY": ["WF_ARCH_REVIEW", "WF_EXECUTE", "WF_RESEARCH", "WF_DEBUG_TDD", "WF_CLARIFY"]
  }
}
```

**Auto-derivation rule:** For each state, collect all unique values from its `transitions` map. The explicit matrix takes precedence if both exist.

### 3.5 State Hooks (onEnter / onExit)

Optional per-state hooks that fire on state transitions:

```json
{
  "hooks": {
    "onEnter": {
      "WF_ARCH_REVIEW": {
        "enablePlanMode": true
      },
      "WF_EXECUTE": {
        "disablePlanMode": true,
        "resetEditCounter": true
      },
      "WF_DONE": {
        "archiveSession": true
      }
    },
    "onExit": {
      "WF_CHECKPOINT": {
        "resetEditCounter": true
      }
    }
  }
}
```

These are declarative actions, not arbitrary code. Supported actions:

| Action | Type | Description |
|---|---|---|
| `enablePlanMode` | boolean | Activate plan mode on state entry |
| `disablePlanMode` | boolean | Deactivate plan mode on state entry |
| `resetEditCounter` | boolean | Reset edits-since-checkpoint counter |
| `archiveSession` | boolean | Mark session as complete in state store |
| `createSentinel` | string | Create a named sentinel in state store gates |
| `requireGate` | string | Verify a gate is satisfied before entry (deny if not) |

### 3.6 Plan Mode Rules

Plan mode behavior is fully declarative via the `planMode` field:

- `"never"`: Plan mode is never activated by this state
- `"always"`: Plan mode is activated on entry, deactivated on exit to any non-`"always"` state
- `"conditional"`: Plan mode may be activated depending on task complexity (left to Claude's judgment based on factual context)

**Replaces:** The hardcoded `PLAN_MODE_STATES` and `EXIT_PLAN_MODE_STATES` sets in `state_manager.py`.

## 4. Custom State Extension

### 4.1 User-Defined States

Users can add custom states by adding entries to `states` in their own config file (see SPEC-006 for overlay mechanism):

```yaml
# config/custom/my-states.yml
states:
  WF_SECURITY_SCAN:
    id: WF_SECURITY_SCAN
    category: execution
    icon: "🛡️"
    label: "Security Scan"
    description: "Run security analysis before verification"
    planMode: never
    allowEdit: false
    allowWrite: false
    transitions:
      passed: WF_VERIFY
      issues_found: WF_EXECUTE
    requiredGates:
      - security_tools_available

transitionMatrix:
  WF_EXECUTE:
    - WF_CHECKPOINT
    - WF_VERIFY
    - WF_SECURITY_SCAN   # Added transition
```

### 4.2 State ID Conventions

- Built-in states: `WF_` prefix (reserved)
- User custom states: `WF_` prefix allowed but `WFX_` prefix recommended to avoid future conflicts
- State IDs: `UPPER_SNAKE_CASE`, max 32 characters

## 5. Validation Rules

The config loader (SPEC-006) validates:

1. **Referential integrity:** All transition targets must exist in `states`
2. **Terminal consistency:** Terminal states must have `transitions: { "complete": null }` only
3. **Category validity:** All state categories must exist in `categories`
4. **No orphan states:** Every non-entry state must be reachable from at least one other state
5. **Cycle safety:** WF_CLARIFY's `(return_to_caller)` is the only dynamic target allowed
6. **Gate references:** All `requiredGates` must reference gates defined in `gates.yml`

## 6. JSON Schema

A formal JSON Schema file at `config/schema/states.schema.json` will validate the configuration. This enables IDE autocompletion and pre-flight validation.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["version", "states", "transitionMatrix"],
  "properties": {
    "version": { "type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$" },
    "states": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "required": ["id", "category", "icon", "description", "transitions"],
        "properties": {
          "id": { "type": "string", "pattern": "^WF[X]?_[A-Z_]{1,28}$" },
          "category": { "type": "string" },
          "icon": { "type": "string", "maxLength": 4 },
          "label": { "type": "string", "maxLength": 32 },
          "description": { "type": "string", "maxLength": 200 },
          "planMode": { "enum": ["never", "always", "conditional"] },
          "allowEdit": { "type": "boolean" },
          "allowWrite": { "type": "boolean" },
          "terminal": { "type": "boolean" },
          "contextTemplate": { "type": "string" },
          "transitions": { "type": "object" },
          "requiredGates": { "type": "array", "items": { "type": "string" } },
          "metadata": { "type": "object" }
        }
      }
    },
    "transitionMatrix": {
      "type": "object",
      "additionalProperties": {
        "type": "array",
        "items": { "type": ["string", "null"] }
      }
    }
  }
}
```

## 7. Migration from v1

The existing `state-machine/states.json` is migrated to `config/states.json` with these changes:

1. Add `$schema` reference
2. Add `defaults` and `categories` sections
3. Add `contextTemplate` references to each state
4. Add `metadata.continuation` from the current hardcoded `directives` dict
5. Add `hooks.onEnter/onExit` for plan mode states
6. Remove `complexityThresholds` (unused, can be re-added if needed)
7. Keep `transitionMatrix` as-is (already correct format)

The old `state-machine/` directory is kept with a deprecation notice pointing to `config/`.
