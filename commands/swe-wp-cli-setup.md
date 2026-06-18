---
name: swe-wp-cli-setup
description: Configure the WP-CLI MCP server — discover each site's devcontainer and write .serena/wp-cli.conf
---

# /swe-wp-cli-setup

Configure the `wp_cli` MCP tool for this WordPress project.

Runs the `swe-wp-cli-setup` skill: discovers each site's `.devcontainer`,
derives its container name + internal WP path (+ optional SSH), and writes a
sectioned `.serena/wp-cli.conf`. Handles single-project (mono-repo) and
multi-repo workspaces, then verifies each site with a read-only WP-CLI call.

Execute the skill at `skills/swe-wp-cli-setup/SKILL.md`.
