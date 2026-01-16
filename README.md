# Serena Workflow Engine

21-state workflow engine for Claude Code with RLVR learning, swarm coordination, and Serena memory persistence.

---

## Quickstart

### 1. Add to your project

```bash
cd your-project
git submodule add https://github.com/anthropics/serena-workflow-engine .claude/plugins/serena-workflow-engine
chmod +x .claude/plugins/serena-workflow-engine/hooks/*.sh
```

### 2. Enable the plugin

**Option A: Via marketplace (if published)**
```
/plugin marketplace add .claude/plugins/serena-workflow-engine
/plugin install serena-workflow-engine@serena-workflow-engine --scope project
```

**Option B: Manual settings.json (local/unpublished)**

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/plugins/serena-workflow-engine/hooks/session-start.sh"
          }
        ]
      }
    ]
  }
}
```

**Option C: CLI flag (testing)**
```bash
claude --plugin-dir .claude/plugins/serena-workflow-engine
```

### 3. Initialize the plugin

Restart Claude Code, then paste this prompt:

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

| Command | Description |
|---------|-------------|
| `/swe-init` | First-time setup |
| `/swe-status` | Show current state |
| `/swe-reset` | Reset workflow |
| `/swe-goto [STATE]` | Force transition |
| `/swe-memory` | Manage WORKING_MEMORY |
| `/swe-cleanup` | Archive completed work |

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
