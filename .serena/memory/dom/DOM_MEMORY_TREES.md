---
name: Two Memory Trees
description: This repo has TWO opposite-purpose memory trees — plugin SOURCE (memories/, ships to every install) vs this repo's OWN dev memories (.serena/memory/, local only). Never conflate them.
metadata:
  type: domain
---

# Two Memory Trees

This repo (serena-workflow-engine) holds two separate, opposite-purpose memory sets. NEVER conflate them.

## 1. `memories/` — PLUGIN SOURCE (ships to every installed repo)

- Canonical source of the plugin's behavior: `wf/WF_*`, `claude/CLAUDE_OBLIGATIONS`, `dom/*`, `arch/*`, `feature/FEATURE_SWE` + `FEATURE_SWARM`, `ref/*`, `claude/RUFLO`.
- `memories/templates/*` = seed files bootstrap copies into a NEW project's `.serena/memory/` at `/swe-init` (`copy_template_memories` walks `memories/templates/` and copies every `.md`).
- Edit as plain files with Read/Write/Edit — this is the plugin repo, NOT a Serena memory store.
- Blast radius: GLOBAL — a change here changes plugin behavior in ALL repos.

## 2. `.serena/memory/` — THIS REPO'S OWN DEV MEMORIES (local only, never ships)

- Memories for developing this plugin (dogfooding): `feature/FEATURE_DEV_STANDARDS`, `feature/FEATURE_TESTS`, `feedback/*`, `dom/DOM_SWE_INIT_MEMORY_PATHS`, `index/INDEX_FEATURES`, `ref/REF_MEMORY_STYLE`, `ref/REF_MEMORY_MAINTENANCE`, `MEMORY.md`.
- Edit ONLY with the Serena memory MCP tools (`write_memory` / `edit_memory`) — this IS a Serena memory store. NEVER use raw Write/Edit (the pre-edit gate hard-blocks it).
- Blast radius: LOCAL.

## Where They Meet

This repo's `.serena/memory/` was stamped from `memories/templates/`, then customized. To change what every installed project receives, edit the TEMPLATE in `memories/templates/` — NOT only the local copy.

## Consequence for shipped standards

Anything that must govern every install lives in BOTH trees:
- `ref/REF_MEMORY_STYLE` → `memories/templates/ref/REF_MEMORY_STYLE.md` (inherited by installs) AND local `.serena/memory/ref/` (governs local dev).
- Enforcement hooks (e.g. `swe_post_memory_style.py`) live in plugin source `hooks/post/` so they ship and enforce everywhere.

Related: `mem:dom/DOM_SWE_INIT_MEMORY_PATHS` (singular `.serena/memory` vs plural `.serena/memories`), `mem:feedback/FEEDBACK_PLUGIN_SOURCE_LOCATION` (never write to the plugin cache).
