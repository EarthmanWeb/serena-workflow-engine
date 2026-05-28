# Style and Conventions

## Python
- Scripts use `#!/usr/bin/env python3` shebang
- Standard library preferred (json, os, sys, pathlib, subprocess)
- No type hints enforced in hook scripts (utility/glue code style)
- Functions use snake_case
- Constants use UPPER_SNAKE_CASE

## Markdown
- Formatted by dprint (`npm run fmt`)
- Memory files use structured headings and bullet lists
- Template memories use `FEATURE_` prefix convention

## JSON
- Formatted by dprint
- 2-space indentation

## Naming Conventions
- Memory files: UPPER_SNAKE_CASE (e.g., `FEATURE_TESTS.md`, `WF_INIT.md`)
- Feature keys: `FEATURE_[KEY]` format
- Hook scripts: lowercase with underscores (e.g., `swe_session_start.py`)
- Skills directories: kebab-case (e.g., `swe-feature-onboard`)

## Design Patterns
- Hook-driven architecture: all workflow logic triggered by Claude Code hooks
- State machine pattern: transitions defined declaratively in JSON
- Memory persistence: Serena memories for cross-session state
- Working Memory: per-session ephemeral state via swe-wm MCP
