---
name: Init memory-paths & Serena Reconnect Gate
description: memory-paths.conf lists only ./.serena/memory (singular); Serena MUST reconnect after bootstrap or memories split-brain.
metadata:
  type: domain
---

# Init: memory-paths.conf + Serena Reconnect Gate

## Singular vs Plural Tree

- `./.serena/memory` (SINGULAR) — authoritative typed-memory tree. Auto-memory symlink targets it; committed feature/dom/ref memories live here. This is the ONLY path init writes to `memory-paths.conf`.
- `./.serena/memories` (PLURAL) — gitignored session Working-Memory dir (`WM_*.md`). NOT a Serena memory source. NEVER add it to `memory-paths.conf`.

`scripts/swe-bootstrap.py::ensure_memory_paths_conf` → `required_lines = ['./.serena/memory']`. The plural entry was a bug that seeded the split-brain — NEVER re-add it.

## Reconnect Gate (root cause of memory-tree split-brain)

Serena reads `.serena/memory-paths.conf` ONCE, at MCP connection time. On a fresh project the session's Serena server connects BEFORE bootstrap creates that file. Until Serena reconnects, it resolves memories against its DEFAULT single path — writes land in one tree, the SWE system reads another.

**Fix (Task 3.5 in `agents/swe-init-agent.md`):** After bootstrap writes `memory-paths.conf`, STOP — end the turn, tell the user to reconnect Serena (`/mcp` → `serena` → Reconnect), then resume via `/swe-init`. NEVER write any memory (onboarding / migration / memory_maintenance) before the reconnect.

**Two-pass / resume:** `/swe-init` is idempotent — bootstrap guards on `bootstrapped: true`. Resume detection: `bootstrapped:true` + `complete:false` ⇒ resume pass ⇒ skip Tasks 2–3.5, run Tasks 4–11 with Serena reading correct paths. Documented in `commands/swe-init.md`.

Related: `mem:feature/FEATURE_SWE`, `mem:feedback/FEEDBACK_PLUGIN_SOURCE_LOCATION`.
