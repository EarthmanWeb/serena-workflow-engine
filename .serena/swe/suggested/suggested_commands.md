# Suggested Commands

## Formatting
```bash
# Format markdown and JSON files
npm run fmt
# Check formatting without writing
npm run fmt:check
```

## Version Management
```bash
# Bump plugin version
bash scripts/bump-version.sh
```

## Development Setup
```bash
# Install hooks for local dev (git submodule setup)
bash scripts/install-hooks.sh
# Start Serena MCP server
bash scripts/start-serena.sh
# Start Working Memory MCP server
bash scripts/start-wm-mcp.sh
```

## Bootstrap (per-project)
```bash
# Run bootstrap for a target project
python3 scripts/swe-bootstrap.py
```

## System Utilities (macOS / Darwin)
```bash
git status        # Check repo state
jq '.key' file    # JSON processing
ls -la            # List files
```

## Claude Code Plugin Commands
```
/swe-init                   # First-time setup
/swe-status                 # Show current workflow state
/swe-feature-onboard [KEY]  # Register existing feature
/swe-feature-update [KEY]   # Update feature memories
/swe-scaffold               # Scaffold new project
/swe-reset                  # Reset workflow state
/swe-goto [STATE]           # Force transition (debug)
/swe-cleanup                # Archive completed work
```
