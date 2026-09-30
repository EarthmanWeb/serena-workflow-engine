---
name: DOM_SWE_MEMORY_PATHS
description: Multi-source memory-paths.conf format — aliasing rules, flat-merge behavior, and the Serena memory_manager fork that implements it.
obligations:
  - Use an alias for EVERY imported sibling-project memory tree — an aliased memory is addressed ONLY as `<alias>/<rel>`, NEVER merged into the flat namespace.
metadata:
  type: domain
---

# DOM_SWE_MEMORY_PATHS

Multi-source memory config: `.serena/memory-paths.conf`.

- Entry syntax: `[alias=]path[:ro]`, one per line. First line = primary write dir (NEVER aliased). `start-serena.sh` appends the plugin `memories:ro` dir unaliased.
- Aliased entry (e.g. `em=../em-serena/.serena/memory`): memories addressed ONLY as `<alias>/<rel>` (`em/feature/FEATURE_TESTS`) for list/read/write/edit/delete/move/search. NEVER merged into the flat namespace — same-named memories across sources cannot shadow each other.
- Unaliased extra: flat merge, primary wins; Serena logs a warning per shadowed name.
- Alias rules (Serena raises ValueError at startup): `[A-Za-z0-9_-]+`, not `global`, unique, not the name of a top-level dir in the primary tree.
- Implementation: fork `serena/memories/memory_manager.py` (`_memory_aliases`, `split_alias`); `serena_memory_patch.py` preserves the `<alias>/` segment and normalizes only the remainder, and NEVER falls back to a non-aliased lookup for an aliased name.
