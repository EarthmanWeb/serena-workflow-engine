---
name: swe-memory-frontmatter
description: Audit and backfill YAML front-matter across the project's Serena memories (nested metadata.type + body-derived metadata.keywords, stacked-block collapse, type derived from the directory prefix)
argument-hint: [scope]
---

# /swe-memory-frontmatter [scope]

Bring every Serena memory to the standard nested `metadata.type` front-matter so
`search_memories_by_front_matter` has complete, uniform data. Adds a block to memories that lack one,
collapses stacked (duplicate) leading blocks into one, converts flat `type:` blocks, repairs
non-standard nested blocks, derives `metadata.type` from the memory's directory prefix, and enriches
search-poor blocks with a `metadata.keywords` list + description terms extracted from the body's
concrete identifiers (usernames, ports, option keys, command names). The body is never modified.
Idempotent.

Optional `scope` limits the audit to one directory prefix (e.g. `ref`, `feedback`); omit to audit all.

Execute the skill at `skills/swe-memory-frontmatter/SKILL.md`.
