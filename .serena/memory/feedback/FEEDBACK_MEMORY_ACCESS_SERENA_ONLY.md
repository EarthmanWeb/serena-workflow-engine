---
name: Memory Access Is Serena-Only
description: Agents read/search/write Serena memories ONLY through Serena memory MCP tools; gates and workflow docs must never sanction or reward filesystem access to memory stores.
metadata:
  type: feedback
---

# Memory Access Is Serena-Only

- Access `.serena/memory/`, `.serena/memories/`, and the `~/.claude/projects/<enc>/memory` symlink ONLY via Serena tools: `read_memory`, `list_memories`, `search_memories_by_name`, `search_memories_by_front_matter`, `search_for_pattern(relative_path=".serena/memory")` (body search), `write_memory`, `edit_memory`.
- NEVER design a gate, sweep step, or skill that sanctions or credits Bash/Grep/Glob/Read on a memory store (the former search-docs gate "B2" `memory-grep` docread credit and the WF_CLASSIFY Tier-0 `awk` taught agents to grep memories).
- Enforcement: `hooks/pre/swe_pre_memory_fs_gate.py` + `hooks/swe_hooks/core/memory_fs.py`.

**Why:** 2026-09-30 an agent in another project answered a lookup with `grep`/`head`/`sed` over `.serena/memory`; the operator rejected it ("you have a tool called Serena that does that").

**How to apply:** when adding a gate credit, workflow step, or skill command that touches memories, route it through a Serena memory tool; plugin-source `memories/` in this repo stays a plain-file tree ([[Two Memory Trees]]).
