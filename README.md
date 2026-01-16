# Serena Workflow Engine

21-state workflow engine for Claude Code with RLVR learning, swarm coordination,
and Serena memory persistence.

---

## Quickstart

### 1. Add to your project

```bash
cd your-project
git submodule add https://github.com/anthropics/serena-workflow-engine .claude/plugins/serena-workflow-engine
chmod +x .claude/plugins/serena-workflow-engine/hooks/*.sh
```

### 2. Enable the plugin

Open Claude Code in your project directory. Run these slash commands **inside
Claude Code** (not in terminal):

**Option A: Via marketplace (if published)**

```bash
claude /plugin marketplace add .claude/plugins/serena-workflow-engine
claude /plugin install serena-workflow-engine@serena-workflow-engine --scope project
```

**Option B: Local path (unpublished)**

```bash
claude /plugin install --path .claude/plugins/serena-workflow-engine --scope project
```

After running, **restart Claude Code** for the plugin to load.

### 3. Initialize the plugin

After restart, paste this prompt into Claude Code:

```
Read the file .claude/plugins/serena-workflow-engine/commands/swe-init.md and execute the setup steps it describes. Install any missing MCP servers to ~/.claude.json and complete the 7-step initialization.
```

This will:

- Detect and install required MCPs (serena, claude-flow, ruv-swarm)
- Run Serena onboarding
- Create core memories
- Configure .gitignore

### 4. Start working

After setup, the workflow guides you automatically. Type any task to begin.

---

## Commands

| Command              | Description                   |
| -------------------- | ----------------------------- |
| `/swe-init`          | First-time setup              |
| `/swe-status`        | Show current state            |
| `/swe-reset`         | Reset workflow                |
| `/swe-goto [STATE]`  | Force transition              |
| `/swe-memory`        | Manage WORKING_MEMORY         |
| `/swe-scaffold`      | Scaffold new project          |
| `/swe-onboard [KEY]` | Register existing feature     |
| `/swe-onboard-quick` | Quick feature registration    |
| `/swe-cleanup`       | Archive completed work        |

---

## Onboarding Features / Scaffolding New Apps

### Scaffolding a New Project

For empty or new projects:

```
/swe-scaffold
```

8-stage wizard: app type → platform config → goals → assets → recommendations → architecture → memories → analysis.

Creates: `.serena/memories/`, core memories, architecture folders.

### Onboarding an Existing Feature

To register an existing codebase feature:

```
/swe-onboard [KEY]
```

5-stage wizard: identifier → name → folders → dependencies → analysis mode.

Creates: `FEATURE_[KEY]`, updates `INDEX_FEATURES`, optionally `DOM_*` and `SYS_*` memories.

### Quick Onboarding

Fast registration without wizard:

```
/swe-onboard-quick [KEY] [NAME] [PATH]
```

Example: `/swe-onboard-quick AUTH "Authentication" src/auth/`

---

## Requirements

- **Serena MCP** - Memory persistence
- **Claude-Flow MCP** - Swarm orchestration
- **RUV-Swarm MCP** - DAA learning
- **jq** - JSON parsing (`brew install jq`)

---

## How It Works

The engine enforces a 21-state workflow:

```
START → CLASSIFY → PLAN → EXECUTE → VERIFY → DONE → CLEANUP
           ↓
       RESEARCH / DEBUG / CLARIFY (as needed)
```

Key features:

- Auto plan mode for medium+ complexity
- Checkpoint every 3 edits
- RLVR learning at task completion
- Swarm agents for large tasks

---

## License

MIT
