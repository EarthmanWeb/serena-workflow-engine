---
name: swe-scaffold-project
version: 1.0.0
description: Initialize workflow for new empty projects. Creates core memories and directory structure.
workflow:
  aware: true
  callable_from:
    - WF_START
    - WF_INITIAL_SETUP
  default_return: WF_START
  supports_standalone: true
  auto_transition: true
---

## ⚠️ WORKFLOW INITIALIZATION

**If starting a new session**, first read workflow initialization:

```
mcp__plugin_swe_serena__read_memory("wf/WF_INIT")
```

Follow WF_INIT instructions before executing this skill.

---

# Scaffold Project Skill

Initialize workflow system for new or empty projects.

## When to Use

- New projects without existing memories
- Projects missing INDEX_FEATURES
- Converting existing projects to workflow system
- **Lightweight alternative to `/swe-init`** — creates memories and prompts for features without running the full autonomous verification agent (MCP checks, LSP install, VSCode extension, etc.)

**Prefer `/swe-init`** for first-time setup — it runs bootstrap, scaffold, AND verification in one autonomous flow.

## Detection Triggers

Automatically suggested when:

- No `.serena/memory/` directory exists
- No `INDEX_FEATURES.md` file exists
- `INDEX_FEATURES.md` has zero features registered

## Process

### Stage 0: Git Repository Check

**BEFORE any other detection, check for a git repository.**

```bash
if ! git rev-parse --git-dir > /dev/null 2>&1; then
  echo "No git repository found in this project directory."
fi
```

**If no git repo exists:**
1. Ask the user: "No git repository detected. Initialize one? (recommended for SWE workflow)"
2. If yes:
   ```bash
   git init
   echo "# Project" > README.md  # only if no README exists
   git add -A
   git commit -m "Initial commit"
   ```
3. If no: Warn that some features may not work (project root detection, .gitignore integration) but proceed.

**Why git is needed:**
- Serena uses `.git/` to detect project root (`_get_project_root()` in init gate)
- SWE hooks use `CLAUDE_PROJECT_DIR` with `.git/` fallback for root resolution
- `.gitignore` integration for ignoring `WM_*.md`, `.serena/swe-state/`, etc.
- Without git, `get_project_root()` falls back to `os.getcwd()` which may be wrong in subdirectories

### Stage 1: Project Detection

```bash
# Git repo guaranteed by Stage 0 (or user warned)
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)

# Detect package manager
[ -f "package.json" ] && echo "npm"
[ -f "composer.json" ] && echo "composer"
[ -f "Cargo.toml" ] && echo "cargo"
[ -f "requirements.txt" ] && echo "pip"
[ -f "go.mod" ] && echo "go"

# Detect primary language
find . -name "*.ts" -o -name "*.js" | head -1  # TypeScript/JavaScript
find . -name "*.py" | head -1                   # Python
find . -name "*.php" | head -1                  # PHP
find . -name "*.rs" | head -1                   # Rust
find . -name "*.go" | head -1                   # Go
```

### Stage 2: Directory Setup

```bash
mkdir -p .serena/memory
mkdir -p .claude/skills
mkdir -p .claude/hooks
```

### Stage 3: Core Memory Creation

Create from templates:

1. **_INDEX** - Navigation hub

```markdown
# _INDEX - Memory Navigation

## Quick Reference

- Features: INDEX_FEATURES
- Architecture: ARCH_INDEX
- Workflows: INDEX_WORKFLOWS_STATES

## Memory Types

| Prefix   | Purpose           |
| -------- | ----------------- |
| FEATURE_ | Feature configs   |
| DOM_     | Domain behaviors  |
| SYS_     | System references |
| REF_     | Reference docs    |
| INDEX_   | Navigation        |
| WF_      | Workflow states   |
| WM_      | Session state     |
```

2. **INDEX_FEATURES** - Empty feature registry

```markdown
# INDEX_FEATURES

## Registered Features

(none yet - run /swe-feature-onboard to add)

## Quick Start

1. `/swe-feature-onboard [KEY]` - Full wizard
2. `/swe-onboard-quick [KEY]` - Fast setup
```

3. **ARCH_INDEX** - Basic architecture placeholder

```markdown
# ARCH_INDEX - Architecture Overview

## Project Type

[Detected or unknown]

## Primary Language

[Detected]

## Framework

[Detected or none]

## Structure

(Run /swe-feature-onboard to populate)
```

### Stage 4: First Feature Prompt

**PROJECT SCAFFOLDED**

**Created:**

- .serena/memory/
- _INDEX
- INDEX_FEATURES
- ARCH_INDEX

Your project needs at least one feature to enable code changes.

**What is the main codebase?**

- Name: [e.g., "Backend API"]
- Key: [e.g., "BACKEND"]
- Path: [e.g., "src/"]

**Options:**

- **[A]** Set up now with /swe-feature-onboard (recommended)
- **[B]** Quick setup with /swe-onboard-quick
- **[C]** Skip - add features later (research-only mode)

### Stage 5: Optional Swarm Analysis

If swarm MCP available:

```
AI-powered codebase analysis available.

[A] Full DAA analysis (creates DOM_*, SYS_*, detailed INDEX_*)
[B] Quick scan (basic structure)
[C] Skip
```

### Stage 6: Finalize Setup Status

If `swe-setup-complete.json` has `bootstrapped: true` but not `complete: true`, update it:

```bash
PLUGIN_VERSION=$(jq -r '.version' "$SWE_PLUGIN_ROOT/.claude-plugin/plugin.json" 2>/dev/null || echo "unknown")
cat > .serena/swe-setup-complete.json << EOF
{
  "complete": true,
  "timestamp": "$(date -Iseconds)",
  "version": "${PLUGIN_VERSION}",
  "scaffolded": true,
  "verified": false
}
EOF
```

This unblocks the full init gate for subsequent sessions. Running `/swe-init` later will add `verified: true` after full verification.

## Minimal Workflow Mode

If user skips feature setup, enable minimal mode:

```json
{
  "mode": "minimal",
  "allowed_states": ["WF_START", "WF_RESEARCH", "WF_CLARIFY"],
  "blocked_states": ["WF_EXECUTE", "WF_CHECKPOINT"],
  "message": "Feature onboarding required for code changes"
}
```

## Skill Return Format

```markdown
## Skill Return

- **Skill**: swe-scaffold-project
- **Status**: [success|needs_clarification]
- **Project Root**: [path]
- **Language**: [detected]
- **Framework**: [detected or none]
- **Memories Created**: _INDEX, INDEX_FEATURES, ARCH_INDEX
- **Next Step Hint**: WF_START or /swe-feature-onboard
```

## Exit

`> **Skill /swe-scaffold-project complete** - Project scaffolded, run /swe-feature-onboard to add first feature`
