---
name: SWE Init — memory-paths.conf & Serena reconnect gate
description: Why init writes only ./.serena/memory and must reconnect Serena before writing memories
metadata:
  type: domain
---

# SWE Init: memory-paths.conf + Serena reconnect gate

## The singular vs plural tree

- `./.serena/memory` (SINGULAR) — authoritative typed-memory tree. The auto-memory symlink targets it; committed feature/dom/ref/etc. memories live here. This is the ONLY path init writes to `memory-paths.conf`.
- `./.serena/memories` (PLURAL) — gitignored session Working-Memory dir (`WM_*.md`). NOT a Serena memory source. Must never be added to `memory-paths.conf`.

`scripts/swe-bootstrap.py::ensure_memory_paths_conf` → `required_lines = ['./.serena/memory']` (was previously `['./.serena/memory', './.serena/memories']` — the plural entry was a bug that seeded the split-brain).

## The reconnect gate (root cause of memory-tree split-brain)

Serena reads `.serena/memory-paths.conf` **once, at MCP connection time**. On a fresh project the session's Serena server connects BEFORE bootstrap creates that file. So until Serena reconnects, it resolves memories against its DEFAULT single path — writes land in one tree while the SWE system reads another.

**Fix (Task 3.5 in `agents/swe-init-agent.md`):** after bootstrap writes `memory-paths.conf`, STOP — end the turn, tell the user to reconnect Serena (`/mcp` → `serena` → Reconnect), then resume via `/swe-init`. Do NOT write any memory (onboarding/migration/memory_maintenance) before the reconnect.

**Two-pass / resume:** `/swe-init` is idempotent — bootstrap guards on `bootstrapped: true`. Resume detection: `bootstrapped:true` + `complete:false` ⇒ resume pass ⇒ skip Tasks 2–3.5, run Tasks 4–11 with Serena now reading correct paths. Documented in `commands/swe-init.md`.

Related: `mem:feature/FEATURE_SWE` (bootstrap & init flow), `mem:feedback/FEEDBACK_PLUGIN_SOURCE_LOCATION`.
