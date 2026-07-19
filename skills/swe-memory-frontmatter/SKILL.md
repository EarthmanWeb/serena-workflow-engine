---
name: swe-memory-frontmatter
version: 1.0.0
description: "Audit and backfill YAML front-matter across a project's Serena memories so name/description/front-matter search works. Adds a front-matter block to memories that lack one, normalizes existing blocks to the nested metadata.type shape, and derives type from the memory's directory prefix. Never touches the memory body. Idempotent; safe to re-run. Mutates only through the Serena memory MCP tools (required by the pre-edit gate)."
workflow:
  aware: true
  callable_from:
    - WF_CLASSIFY
    - WF_EXECUTE
  default_return: WF_CLASSIFY
  supports_standalone: true
args:
  - name: scope
    description: "Optional directory-prefix filter (e.g. ref, feedback) to limit the audit to one topic. Omit to audit ALL memories."
    required: false
---

## ⚠️ WORKFLOW INITIALIZATION

**If starting a new session**, first read workflow initialization:

```
mcp__plugin_swe_serena__read_memory("wf/WF_INIT")
```

Follow WF_INIT instructions before executing this skill.

---

# /swe-memory-frontmatter [scope]

Bring every Serena memory in this project to a consistent YAML front-matter block, so
`search_memories_by_front_matter` (and the front-matter that front-matter search reads) has complete,
uniform data.

This is needed because front-matter is currently inconsistent: many memories have none (they open with
an `#` H1 or prose), and those that do split between a flat `type:` and a nested `metadata:` block.
`search_memories_by_name` finds any memory by name regardless, but `search_memories_by_front_matter`
can only match memories that actually carry front-matter — this skill fills that gap.

## What it does

For every memory in scope:

1. **Read** the memory (`mcp__plugin_swe_serena__read_memory`).
2. **Classify** its current front-matter. Having *any* front-matter is NOT a pass — every block is
   validated against the standard and repaired if it deviates:
   - **None** (starts with `#`, prose, or anything other than a `---` fence) → block ADDED.
   - **Flat** (`type:` at top level) → CONVERTED to the nested shape.
   - **Nested but non-standard** (`metadata:` present but: `type` missing/wrong for the directory,
     `name` or `description` missing, extra stray top-level keys, or fields out of the standard
     `name → description → metadata` order) → REPAIRED to the standard.
   - **Standard** (already exactly `name` + `description` + `metadata.type`, with `type` matching the
     directory-derived value, in the standard order) → `ok`, left untouched.

   A memory is `ok` ONLY when it already equals the standard. Any existing block that differs — flat,
   partial, mis-typed, or extra-keyed — is rewritten to the standard shape. Preserve the human-written
   `name`/`description` values when present; only `metadata.type` is authoritatively (re)derived from
   the directory prefix.
3. **Derive** the three fields:
   - `name` — from an existing `name:`, else the H1 heading text, else the base filename.
   - `description` — from an existing `description:`, else a single concise sentence summarizing the
     body (what the memory is about — the "why you'd open it").
   - `metadata.type` — derived from the memory's **directory prefix** (see map below).
4. **Write** the normalized block back, **prepending/replacing only the leading `---…---`** — the body
   below the front-matter is never modified.

## Target shape (the ONLY shape this skill writes)

Nested `metadata.type` — chosen because `metadata:` is an extensible namespace (future keys like
`tags`/`status`/`related` nest under it without polluting the top level):

```yaml
---
name: REF_SECURITY_SCANNER
description: Convenely Security Scanner MU-plugin rules — the plugin/theme allowlist ("bypass") and how to add an allowed plugin.
metadata:
  type: reference
---
```

A flat `type:` block is converted into this shape. The `name`/`description` values are preserved.

## Directory-prefix → type map

Derive `metadata.type` from the leading path segment of the memory name (case-insensitive):

| prefix | type | | prefix | type |
| --- | --- | --- | --- | --- |
| `ref` | `reference` | | `feature` | `feature` |
| `feedback` | `feedback` | | `dom` | `domain` |
| `project` | `project` | | `sys` | `system` |
| `arch` | `architecture` | | `spec` | `spec` |
| `report` | `report` | | `research` | `research` |
| `content` | `content` | | `wf` | `workflow` |

- Prefix not in the map → use the prefix itself, lowercased, as the type (do not invent a bucket).
- A flat memory at the root (no `/` prefix, e.g. `MEMORY`) → type `index`.

## Stages

### Stage 1: Discover

List the memories to audit:

```
mcp__plugin_swe_serena__list_memories(topic="<scope>")   # scope arg, or omit topic for ALL
```

Skip these — they are managed elsewhere or intentionally front-matter-free:
- `WM_*` / `wm/*` (working memory, ephemeral)
- `wf/*`, `claude/*` (read-only workflow/obligation memories)
- `MEMORY` (the index file)
- any memory listed under `read_only_memories` (cannot be written)

### Stage 2: Classify + derive (per memory)

For each in-scope memory: read it, classify, and derive `name` / `description` / `metadata.type` per
the rules above. Record an action per memory:
`add` (no front-matter) | `convert` (flat → nested) | `repair` (nested but non-standard) |
`ok` (already exactly the standard).

### Stage 3: Write (per memory that needs it)

Apply the block **only through the Serena memory MCP tools** — raw `Edit`/`Write` on
`.serena/memor*` is hard-blocked by the pre-edit gate (`swe_pre_edit_validate.py`):

- **Add** (no front-matter): prepend the new `---…---` block above the existing content using
  `mcp__plugin_swe_serena__edit_memory` with `mode="regex"`, `needle="^"`, `repl="<block>\n\n"`
  (anchored at the start), or read + `write_memory` the full `<block>\n\n<original-body>`.
- **Convert** (flat → nested) / **Repair** (nested but non-standard): replace the entire existing
  leading `---…---` block with the standard one via `edit_memory` (match the exact old `---…---`
  span, `mode="literal"`). The body after the block is left byte-for-byte unchanged.

Never alter the body. After each write, the `swe_post_memory_index.py` hook may remind you to index
new memories — that is unrelated to front-matter; ignore for existing memories.

### Stage 4: Verify

- Re-run for a sample: read 2-3 changed memories, confirm the block parses and the body is intact.
- Confirm idempotency: a second pass over an already-fixed memory reports `ok` (no write).

## Idempotency

Running twice is safe: a memory already in the nested shape with a directory-derived type is reported
`ok` and left untouched. Only `add`/`convert` memories are written.

## Skill Return

```markdown
- **Skill**: swe-memory-frontmatter
- **Status**: success | needs_clarification
- **Scope**: <scope or "all">
- **Audited**: <count>
- **Added**: <count>   (front-matter created)
- **Converted**: <count>   (flat → nested)
- **Repaired**: <count>   (nested but non-standard → standard)
- **OK**: <count>   (already exactly the standard)
- **Skipped**: <count>   (read-only / WM / index / wf / claude)
- **Next Step Hint**: WF_CLASSIFY
```

## Exit

> **Skill /swe-memory-frontmatter complete** — memories normalized to nested `metadata.type` front-matter; body content unchanged.

## Troubleshooting

- **`edit_memory`/`write_memory` refused (read-only)** — the memory matches a `read_only_memory_patterns`
  entry. Report it under Skipped; do not force it.
- **Raw `Edit`/`Write` blocked** — expected; use the Serena memory MCP tools (see Stage 3).
- **Body accidentally changed** — you replaced more than the leading `---…---`. Restore from the memory
  revision and redo the write matching only the front-matter span.
