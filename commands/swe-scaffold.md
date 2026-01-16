---
name: swe-scaffold
description: Initialize workflow for new empty projects
---

# /scaffold-project

Initialize workflow system for new or empty projects.

## When to Use

- New projects without existing memories
- Projects missing INDEX_FEATURES
- Converting existing projects to workflow system

## Process

### Stage 1: Project Detection

Detect:
- Project root (git or cwd)
- Package manager (npm, composer, cargo, pip, go)
- Primary language (TypeScript, Python, PHP, Rust, Go, etc.)
- Framework (if detectable)

### Stage 2: Directory Setup

Create required directories:

```bash
mkdir -p .serena/memories
mkdir -p .claude/skills
mkdir -p .claude/hooks
```

### Stage 3: Core Memory Creation

Create from templates:

**_INDEX.md** - Navigation hub
```markdown
# _INDEX - Memory Navigation

## Quick Reference
- Features: INDEX_FEATURES
- Architecture: ARCH_INDEX
- Workflows: INDEX_WORKFLOWS_STATES

## Memory Types
| Prefix | Purpose |
|--------|---------|
| FEATURE_ | Feature configs |
| DOM_ | Domain behaviors |
| SYS_ | System references |
| REF_ | Reference docs |
| INDEX_ | Navigation |
| WF_ | Workflow states |
| WORKING_MEMORY_ | Session state |
```

**INDEX_FEATURES.md** - Empty feature registry
```markdown
# INDEX_FEATURES

## Registered Features
(none yet - run /onboard-feature to add)

## Quick Start
1. `/onboard-feature [KEY]` - Full wizard
2. `/onboard-quick [KEY]` - Fast setup
```

**ARCH_INDEX.md** - Basic architecture placeholder
```markdown
# ARCH_INDEX - Architecture Overview

## Project Type
[Detected or unknown]

## Primary Language
[Detected]

## Framework
[Detected or none]

## Structure
(Run /onboard-feature to populate)
```

### Stage 4: First Feature Prompt

```
================================================================================
PROJECT SCAFFOLDED
================================================================================
Created:
  [x] .serena/memories/
  [x] _INDEX
  [x] INDEX_FEATURES
  [x] ARCH_INDEX

Your project needs at least one feature to enable code changes.

What is the main codebase?
- Name: [e.g., "Backend API"]
- Key: [e.g., "BACKEND"]
- Path: [e.g., "src/"]

[A] Set up now with /onboard-feature (recommended)
[B] Quick setup with /onboard-quick
[C] Skip - add features later (research-only mode)
================================================================================
```

### Stage 5: Optional Swarm Analysis

If swarm MCP available:
```
AI-powered codebase analysis available.

[A] Full DAA analysis (creates DOM_*, SYS_*, detailed memories)
[B] Quick scan (basic structure)
[C] Skip
```

## Minimal Mode

If user skips feature setup, workflow enters minimal mode:
- Allowed: WF_START, WF_RESEARCH, WF_CLARIFY
- Blocked: WF_EXECUTE, WF_CHECKPOINT
- Message: "Feature onboarding required for code changes"

## Output

```
================================================================================
SCAFFOLD COMPLETE
================================================================================
Project Root:   [path]
Language:       [detected]
Framework:      [detected or none]
Package Mgr:    [detected]

Memories Created:
  [x] _INDEX
  [x] INDEX_FEATURES
  [x] ARCH_INDEX

Next Steps:
  1. Run /onboard-feature [KEY] to add your first feature
  2. Or /onboard-quick [KEY] for fast setup

Workflow Mode: [full|minimal]
================================================================================
```
