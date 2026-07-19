---
name: swe-memory-frontmatter
description: Audit and backfill YAML front-matter across the project's Serena memories (nested metadata.type, type derived from the directory prefix)
argument-hint: [scope]
---

# /swe-memory-frontmatter [scope]

Bring every Serena memory to the standard nested `metadata.type` front-matter so
`search_memories_by_front_matter` has complete, uniform data. Adds a block to memories that lack one,
converts flat `type:` blocks, repairs non-standard nested blocks, and derives `metadata.type` from the
memory's directory prefix. The body is never modified. Idempotent.

Optional `scope` limits the audit to one directory prefix (e.g. `ref`, `feedback`); omit to audit all.

Execute the skill at `skills/swe-memory-frontmatter/SKILL.md`.
