# Serena Workflow Engine

A 14-state workflow engine plugin for Claude Code. Provides structured task routing, Serena memory persistence, hook-driven automation, and optional multi-agent swarm orchestration.

## Quick Start

### 1. Install

```bash
claude plugin marketplace add https://github.com/EarthmanWeb/serena-workflow-engine.git
claude plugin install swe@EarthmanWeb --scope local
```

Install with `--scope local` for a single project, or `--scope user` to make it available globally across all projects. When installed globally, hooks are inert in projects that haven't been initialized -- they won't interfere until you run `/swe-init`.

Auto-update is built in: the plugin checks for the latest version on session start via the marketplace hook.

### 2. Initialize

Restart Claude Code, then run:

```
/swe-init
```

This launches an autonomous agent that handles everything:

- Detects your project's languages and test framework
- Creates `.serena/` directory structure and config files
- Renders template memories with auto-detected project values (project name, language, test runner, etc.)
- Migrates existing auto-memory files from `~/.claude/projects/.../memory/` into `.serena/memory/` with structured subdirectories, then creates a symlink so future auto-memory writes go directly to `.serena/memory/`
- Injects `CLAUDE.md` with memory storage directives pointing to `.serena/memory/`
- Sets up and verifies MCP servers (Serena + swe-wm)
- Installs language servers for detected languages
- Configures `.gitignore` for runtime exclusions

Designed to work with the **VSCode extension** version of Claude Code -- it uses the same auto-memory path that the extension expects for the symlink.

Init is idempotent -- safe to re-run if interrupted.

### 3. Onboard a feature

Restart Claude Code, then:

```
/swe-feature-onboard [KEY]
```

Example: `/swe-feature-onboard BACKEND`

Features define the scope, file paths, and architecture patterns the workflow uses when routing tasks.

## How It Works

Every session follows a structured flow:

```
WF_START -> WF_CLASSIFY -> WF_ARCH_REVIEW -> WF_EXECUTE -> WF_VERIFY -> WF_DONE
```

- **WF_CLASSIFY** loads feature memories and routes by task type
- **WF_ARCH_REVIEW** designs the plan, checks compliance, gets approval
- **WF_EXECUTE** does the work with automatic checkpoints every 3 edits
- **WF_VERIFY** validates against architecture and compliance rules

Side paths: `WF_RESEARCH` (read-only exploration), `WF_CONTINUE` (resume previous work), `WF_SWARM_ORCHESTRATE` (multi-agent tasks), `WF_DEBUG_TDD` (test-driven debugging).

## Memory Architecture

### Storage Locations

| Path | Purpose |
|---|---|
| `.serena/memory/` | Project memories (features, domain, refs, specs) -- persisted, committed |
| `.serena/memories/` | Working Memory files (`WM_<session>.md`) -- ephemeral, gitignored |
| `.serena/memory-paths.conf` | Serena memory path config |

### Auto-Memory Symlink

The init sequence creates a symlink from `~/.claude/projects/<encoded>/memory/` to `.serena/memory/`. This redirects Claude Code's auto-memory system so all memory files are stored in the project repo instead of a global directory. The `MEMORY.md` index is also migrated and updated with new paths.

### Working Memory MCP Server (swe-wm)

The plugin installs its own lightweight MCP server (`swe-wm`) for automated Working Memory management. It:

- Provides `swe_wm_read`, `swe_wm_update_section`, and `swe_wm_update_status` tools
- Filters WM files from `list_memories` output (accessed via swe-wm, not Serena)
- Auto-includes the plugin's hardcoded `WF_*` workflow instruction files in read-only format from the plugin's cached install folder

### Custom Memory Paths

Edit `.serena/memory-paths.conf` to add extra directories Serena should access (one path per line):

```
./.serena/memory
./.serena/memories
./docs:ro
./src/config:ro
```

Append `:ro` for read-only access. The first two paths are always present.

## Template Rendering

Bootstrap auto-detects project info and fills template placeholders:

| Detected From | Values Filled |
|---|---|
| `package.json`, `composer.json`, `Cargo.toml` | Project name, test framework, test commands |
| File extensions scan | Primary language, all languages |
| Dev dependencies | Test runner (Playwright, Jest, Vitest, PHPUnit, Pest, pytest, etc.) |

Templates rendered to `.serena/memory/`:

- `MEMORY.md` -- memory index with default entries
- `FEATURE_TESTS.md` -- test config with detected framework
- `FEATURE_DEV_STANDARDS.md` -- dev standards index
- `FEATURE_AGENTS.md` -- agent registry
- `feedback/FEEDBACK_RESPONSE_FORMAT.md` -- response style
- `ref/REF_MCP_BROWSER_DEVTOOLS.md` -- browser DevTools reference

Unresolved placeholders are left as-is for manual fill-out.

## Auto-Memory Migration

When initializing a project that already has Claude Code auto-memory files, bootstrap automatically migrates, reorganizes, and symlinks them:

| Original | Migrated To |
|---|---|
| `feedback_*.md` | `feedback/FEEDBACK_*.md` |
| `user_*.md` | `user/USER_*.md` |
| `project_*.md` | `project/PROJECT_*.md` |
| `reference_*.md` | `ref/REF_*.md` |
| `SPEC_*.md` | `spec/SPEC_*.md` |
| `MEMORY.md` | Merged with updated paths |

After migration, the symlink ensures all future auto-memory writes go to `.serena/memory/`.

## Commands & Skills

| Command | Purpose |
|---|---|
| `/swe-init` | Full first-time setup (autonomous agent) |
| `/swe-scaffold-project` | Lightweight setup (no MCP/LSP verification) |
| `/swe-feature-onboard` | Register a feature to the workflow |
| `/swe-feature-update` | Sync feature memory with current code |
| `/swe-status` | Show workflow state and transitions |
| `/swe-reset` | Reset workflow state |
| `/swe-goto [STATE]` | Force transition (debug/recovery) |
| `/swe-cleanup` | Archive completed memories |
| `/swe-symlink-memory` | Set up auto-memory symlink with migration |
| `/swe-wm-update` | Update Working Memory sections |
| `/swe-workflow-research` | Read-only code exploration |
| `/swe-workflow-verify` | Verify against requirements |
| `/swe-workflow-arch-review` | Architecture compliance review |
| `/swe-workflow-debug-tdd` | Test-driven debugging |
| `/swe-swarm-orchestrate` | Multi-agent swarm coordination |
| `/swe-swarm-analyze` | DAA-powered codebase analysis |
| `/swe-symbol-index` | Generate symbol index for feature docs |

## Alternative Setup

### Existing project (already has `.serena/`)

```
/swe-init   # Detects existing structure, only runs what's missing
```

### Lightweight (skip MCP/LSP verification)

```
/swe-scaffold-project
```

### Bypass SWE entirely

```bash
# Say "skip swe" when prompted, or:
echo '{"bypass": true, "reason": "user_declined"}' > .serena/swe-bypass.json
```

Remove the file to re-enable.

## Troubleshooting

**Stale plugin version:**
```bash
rm -rf ~/.cache/uv/environments-v2/ ~/.cache/uv/git-v0/ ~/.cache/uv/builds-v0/
rm -rf ~/.claude/plugins/cache/EarthmanWeb/
claude plugin marketplace add https://github.com/EarthmanWeb/serena-workflow-engine
claude plugin install swe@EarthmanWeb --scope local
```

**Init gate blocking tools:** `/swe-status` to check state, `/swe-reset` to fix.

**Debug mode:** `claude --debug`

## Contributing

```bash
git submodule update --init .claude/plugins/serena-workflow-engine
bash .claude/plugins/serena-workflow-engine/scripts/install-hooks.sh
```

| Location | Path | Purpose |
|---|---|---|
| Plugin folder | `.claude/plugins/serena-workflow-engine/` | Generic/portable code |
| Local memories | `.serena/swe/` | Project-specific feature memories |
| Working memory | `.serena/memories/` | Session-scoped WM files |
| State files | `.serena/swe-state/` | Authoritative workflow state |

See `memories/REF_SWE_DEVELOPMENT.md` for development standards.
