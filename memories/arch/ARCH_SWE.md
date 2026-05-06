# ARCH_SWE - Workflow System Architecture

## Overview

The workflow system is a **finite state machine** implemented through Serena memories. Each state (WF_*) is a self-contained instruction set that Claude reads and executes sequentially.

## Core Principles

### 1. Single State Focus

Claude reads ONE WF_* memory at a time, executes its steps, then transitions to the next state. This prevents context overflow and ensures predictable behavior.

### 2. Mandatory Transitions

Every WF_* memory ends with a "MANDATORY NEXT STEP" section. Skipping transitions is a workflow violation.

### 3. Step Reporting

Each state begins with a step report line that must be output immediately:

```
> **🚀 On step WF_START**
```

### 4. Session Persistence

WM provides session continuity across conversation turns and enables WF_CONTINUE to resume work.

## Architecture Layers

```
┌─────────────────────────────────────────────────────────┐
│                    ENTRY LAYER                          │
│  WF_START → WF_CLASSIFY → routing decision              │
└─────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│ RESEARCH PATH │  │  ALL CODE TASKS    │
│  WF_RESEARCH  │  │  (via WF_CLASSIFY) │
└───────────────┘  └────────────────────┘
        │                   │
        └───────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│              REVIEW & PLANNING LAYER                    │
│  WF_ARCH_REVIEW (design + compliance + swarm assess)   │
│            ↓ swarm needed? → WF_SWARM_ORCHESTRATE      │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                    GATE LAYER                           │
│  WF_ARCH_REVIEW (includes approval) ←→ WF_CLARIFY        │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                  EXECUTION LAYER                        │
│  WF_EXECUTE ←→ WF_CHECKPOINT ←→ WF_DEBUG_TDD            │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                 COMPLETION LAYER                        │
│  WF_VERIFY → WF_DONE                                    │
└─────────────────────────────────────────────────────────┘
```

## Integration Points

### Skill Integration (WCP/SRP)

Workflow-aware skills can be invoked from WF_* states:

1. Calling state sets `## Workflow Context` in WM
2. Skill executes and writes `## Skill Return`
3. Calling state reads return status and routes accordingly

See: `REF_SKILL_PROTOCOLS`, `SPEC_WORKFLOW_SKILLS`

### Swarm Integration

WF_SWARM_ORCHESTRATE coordinates multi-agent work:

- Spawns specialized agents (researcher, coder, analyst)
- Each agent can follow workflow or receive direct instructions
- Results aggregated back to main workflow

See: `REF_SWARM_PATTERNS`, `RUFLO`

### Memory Integration

Workflows interact with feature memories:

- `_INDEX` for navigation
- `FEATURE_*` for scope
- `DOM_*`, `SYS_*` for domain/system context
- `ARCH_*` for architecture patterns
- `INDEX_*` for file/symbol lookup

## State Memory Format

Every WF_* memory follows this structure:

```markdown
# WF_[NAME] - [Description]

> **On step WF_[NAME]**

OUTPUT THE ABOVE LINE IMMEDIATELY...

---

## Execute These Steps

[Numbered steps with specific actions]

## MANDATORY NEXT STEP

| Condition   | MUST Read Next |
| ----------- | -------------- |
| [condition] | `WF_[STATE]`   |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**
```

## Modification Checklist

When modifying the workflow system:

- [ ] Read CLAUDE_WORKFLOW for full state diagram
- [ ] Identify all affected states
- [ ] Update WF_* memory content
- [ ] Update transition tables in affected states
- [ ] Update CLAUDE_WORKFLOW diagram if transitions change
- [ ] Update INDEX_WORKFLOWS_STATES if states added/removed
- [ ] Test affected paths manually
- [ ] Update SPEC_WORKFLOW_SKILLS if skill integration changes

## Dependencies

| Component       | Depends On                             |
| --------------- | -------------------------------------- |
| WF_START        | CLAUDE_OBLIGATIONS, INDEX_FEATURES, WM |
| WF_CLASSIFY     | _INDEX, FEATURE_*, REF_SWARM_PATTERNS  |
| WF_CLASSIFY     | (also) _INDEX, DOM_*, SYS_*, INDEX_*   |
| WF_ARCH_REVIEW  | ARCH_INDEX, ARCH__, REF__              |
| WF_VERIFY       | CLAUDE_OBLIGATIONS, ARCH_INDEX         |
| Skills          | REF_SKILL_PROTOCOLS, WM                |
