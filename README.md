# Serena Workflow Engine

15-state workflow engine for Claude Code with Serena memory persistence, hook-driven event architecture, and optional swarm orchestration.

## Prerequisites

- **Claude Code** installed globally
- **Python 3** (for hook scripts and bootstrap)
- **jq** (for JSON processing in setup scripts)

## Install

### 1. Install the plugin

```bash
claude plugin marketplace add https://github.com/EarthmanWeb/serena-workflow-engine.git
claude plugin install swe@EarthmanWeb --scope local
```

### 2. Enable auto-update

In Claude Code CLI: `claude /plugin` > **Marketplaces** tab > **EarthmanWeb** > **Enable auto-update**

### 3. Restart Claude Code and initialize

```
/swe-init
```

The init agent will:
1. Detect your environment and resolve the plugin root
2. Run bootstrap (creates directories, detects languages, migrates any existing auto-memory files, installs templates)
3. Prompt for additional Serena memory paths (e.g. `./docs:ro`)
4. Inject `CLAUDE_PREFIX.md` into your project's `CLAUDE.md`
5. Create `.serena/.gitignore` for runtime file exclusions
6. Verify MCP servers (Serena, swe-wm)
7. Run Serena onboarding
8. Verify and install language servers
9. Enable the SWE plugin
10. Review CLAUDE.md for conflicts
11. Install the Serena Log Viewer VSCode extension
12. Set up auto-memory symlink (redirects `~/.claude/projects/.../memory/` to `.serena/memory/`)
13. Finalize setup

### 4. Restart Claude Code and onboard your first feature

```
/swe-feature-onboard [KEY]
```

## Setup Workflows

There are three ways to get the plugin running, depending on your situation:

### New Project (recommended)

Full automated setup — handles everything in one flow:

```
# 1. Install plugin (see Install section above)
# 2. Open project in Claude Code
# 3. Run init
/swe-init
# 4. Restart Claude Code
# 5. Onboard your first feature
/swe-feature-onboard BACKEND
```

Init is **idempotent** — safe to run again if interrupted or if you want to re-verify. Each task checks for completion before running.

### Existing Project (cloned repo that already uses SWE)

The project already has `.serena/` with memories. You just need local setup:

```
# 1. Install plugin (see Install section above)
# 2. Open project in Claude Code
# 3. Run init — it will detect existing structure and only do what's missing
/swe-init
```

Init detects `swe-setup-complete.json` state:
- **No file** → full bootstrap + init
- **`bootstrapped: true`** → skip bootstrap, run init tasks
- **`complete: true`** → skip everything, report already initialized

### Manual/Lightweight Setup

If you want more control or prefer not to use the full init agent:

```
# 1. Install plugin
# 2. Run scaffold skill — creates core memories and prompts for features
/swe-scaffold-project
# 3. Optionally set up auto-memory symlink
/swe-symlink-memory
```

`/swe-scaffold-project` creates directories, core memories (`_INDEX`, `INDEX_FEATURES`, `ARCH_INDEX`), and prompts you to onboard your first feature. It does NOT verify MCP servers, install LSPs, or run the full init agent checklist.

### Bypassing SWE

If you don't want SWE in a project:

```
# Say "skip swe" when prompted at session start
# Or create the bypass file manually:
echo '{"bypass": true, "reason": "user_declined"}' > .serena/swe-bypass.json
```

All hooks become silent. Remove the file to re-enable.

## Auto-Memory Migration

When initializing a project that already has Claude Code auto-memory files (in `~/.claude/projects/<encoded>/memory/`), the bootstrap automatically migrates and reorganizes them into the SWE subdirectory structure:

| Auto-Memory File | Migrated To |
|---|---|
| `feedback_test.md` | `feedback/FEEDBACK_TEST.md` |
| `user_role.md` | `user/USER_ROLE.md` |
| `project_notes.md` | `project/PROJECT_NOTES.md` |
| `reference_api.md` | `ref/REF_API.md` |
| `SPEC_Foo.md` | `spec/SPEC_Foo.md` |
| `MEMORY.md` | Merged into existing `MEMORY.md` with updated paths |

A symlink replaces the original directory so future auto-memory writes go directly to `.serena/memory/`.

## Directory Structure

```
.serena/
+-- .gitignore              # Runtime file exclusions (auto-created)
+-- memory-paths.conf       # Serena memory path config
+-- project.yml             # Detected languages
+-- memory/                 # All memories (symlinked from ~/.claude/projects/.../memory/)
|   +-- feedback/           # User feedback memories
|   +-- feature/            # Feature configurations
|   +-- project/            # Project context
|   +-- ref/                # Reference docs
|   +-- spec/               # Specifications
|   +-- user/               # User profile memories
|   +-- MEMORY.md           # Memory index
|   +-- _INDEX.md           # Navigation hub
|   +-- INDEX_FEATURES.md   # Feature registry
|   +-- ARCH_INDEX.md       # Architecture overview
+-- swe/                    # SWE-specific memories (feature, ref, dom)
+-- memories/               # Working Memory files (per-session)
|   +-- WM_<session>.md
+-- swe-state/              # Decoupled workflow state (authoritative)
|   +-- <session>.state
+-- streams/                # Append-only event logs
|   +-- <session>.jsonl
|   +-- .init_<session>     # Init gate sentinel
+-- swe-setup-complete.json # Setup completion flag
+-- swe-bypass.json         # SWE disabled flag (if user declines)
```

## Custom Memory Paths

During bootstrap, you'll be prompted to add extra folders for Serena to access.
You can also edit `.serena/memory-paths.conf` manually (one path per line):

```
./.serena/memory
./.serena/memories
./docs:ro
```

Append `:ro` for read-only access. Plugin bundled memories are always appended automatically. See [MCP-README.md](MCP-README.md) for details.

## Commands & Skills

### Commands (lightweight operations)

| Command | Description |
|---|---|
| `/swe-init` | Full automated first-time setup (launches init agent) |
| `/swe-status` | Show current workflow state and valid transitions |
| `/swe-reset` | Reset workflow to WF_START (requires confirmation) |
| `/swe-goto [STATE]` | Force transition to specific state (debug/recovery) |
| `/swe-cleanup` | Archive completed memories and specs |
| `/swe-symlink-memory` | Set up auto-memory symlink with migration |

### Skills (complex workflow operations)

| Skill | Description |
|---|---|
| `/swe-scaffold-project` | Scaffold new project (lightweight alternative to init) |
| `/swe-feature-onboard` | Register and onboard a feature to the workflow |
| `/swe-feature-update` | Update a feature's memory files to match current code |
| `/swe-symbol-index` | Generate symbol index table for feature linked docs |
| `/swe-wm-update` | Update Working Memory sections with step checklists |
| `/swe-swarm-orchestrate` | Multi-agent swarm coordination for large tasks |
| `/swe-swarm-analyze` | DAA-powered codebase analysis using swarm agents |
| `/swe-workflow-research` | Code exploration and research without changes |
| `/swe-workflow-debug-tdd` | Test-driven debugging for failing tests |
| `/swe-workflow-verify` | Verify implementation against requirements |
| `/swe-workflow-arch-review` | Architecture compliance review before execution |

## Workflow States

```
SessionStart --> WF_START
  +-- WF_CLASSIFY (task classification + feature loading)
  |     +-- WF_ARCH_REVIEW (design + compliance + approval)
  |     |     +-- WF_EXECUTE (implementation)
  |     |     +-- WF_SWARM_ORCHESTRATE --> WF_EXECUTE
  |     +-- WF_EXECUTE (operational tasks, skip arch review)
  +-- WF_RESEARCH (read-only exploration)
  +-- WF_CONTINUE (resume previous work)
  +-- WF_ONBOARD (first-time feature setup)

WF_EXECUTE <--> WF_CHECKPOINT (every 3 edits)
WF_EXECUTE --> WF_VERIFY --> WF_DONE
WF_CLARIFY (requirement clarification, returns to caller)
WF_DEBUG_TDD (test-driven debugging)
```

## Troubleshooting

### Stale plugin or Serena version

```bash
rm -rf ~/.cache/uv/environments-v2/ ~/.cache/uv/git-v0/ ~/.cache/uv/builds-v0/
rm -rf ~/.claude/plugins/cache/EarthmanWeb/
claude plugin marketplace add https://github.com/EarthmanWeb/serena-workflow-engine
claude plugin install swe@EarthmanWeb --scope local
```

Restart Claude Code.

### Init gate blocking all tools

The init gate blocks tool use until `WF_INIT` is read. If you're stuck:

```
/swe-status    # Check current state
/swe-reset     # Reset if state is corrupted
```

### Debug

```bash
claude --debug
```

---

## Contributing

### Local dev setup

```bash
git submodule update --init .claude/plugins/serena-workflow-engine
bash .claude/plugins/serena-workflow-engine/scripts/install-hooks.sh
```

### Dual-location architecture

| Location | Path | Purpose |
|---|---|---|
| Plugin folder | `.claude/plugins/serena-workflow-engine/` | Generic/portable code |
| Local memories | `.serena/swe/` | Project-specific feature memories |
| Working memory | `.serena/memories/` | Session-scoped WM files |
| State files | `.serena/swe-state/` | Authoritative workflow state |

See `memories/REF_SWE_DEVELOPMENT.md` for full development standards.
