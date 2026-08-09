---
name: swe-memory-frontmatter
version: 1.0.0
description: "Audit and backfill YAML front-matter across a project's Serena memories so name/description/front-matter search works. Adds a front-matter block to memories that lack one, normalizes existing blocks to the nested metadata.type shape, derives type from the memory's directory prefix, collapses stacked (duplicate) leading blocks into one, and derives metadata.keywords + a search-rich description from concrete identifiers in the body (credentials, usernames, ports, option keys, command names). Never touches the memory body. Idempotent; safe to re-run. Mutates only through the Serena memory MCP tools (required by the pre-edit gate)."
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
   - **Stacked** (TWO or more consecutive leading `---…---` blocks — e.g. an edit inserted a new
     block instead of replacing the old) → COLLAPSED into ONE standard block. Merge fields with the
     LATER block winning on conflicts; front-matter search only reliably reads one block, so a
     stacked file hides its newer fields.
   - **Flat** (`type:` at top level) → CONVERTED to the nested shape.
   - **Nested but non-standard** (`metadata:` present but: `type` missing/wrong for the directory,
     `name` or `description` missing, extra stray top-level keys, or fields out of the standard
     `name → description → metadata` order) → REPAIRED to the standard.
   - **Search-poor** (standard shape, but the description is a generic topic sentence while the BODY
     carries concrete searchable identifiers — credentials/usernames, ports, option keys, command
     names, domain slugs — that appear nowhere in the front-matter) → ENRICHED: fold the key
     identifiers into the description and/or a `metadata.keywords` list.
   - **Standard** (`name` + search-rich `description` + `metadata.type` matching the directory, in
     the standard order, with no body identifiers missing from the front-matter) → `ok`, untouched.

   A memory is `ok` ONLY when it already equals the standard. Any existing block that differs — flat,
   partial, mis-typed, or extra-keyed — is rewritten to the standard shape. Preserve the human-written
   `name`/`description` values when present; only `metadata.type` is authoritatively (re)derived from
   the directory prefix.
3. **Derive** the fields:
   - `name` — from an existing `name:`, else the H1 heading text, else the base filename.
   - `description` — one sentence stating what the memory is about (the "why you'd open it") that
     ALSO carries the body's highest-value search terms. A description a future agent would query
     with must contain the words they would query: "the standardized local WordPress admin login
     credentials (claude_admin username + password preset)" is findable; "dev environment feature
     memory" is not. Preserve an existing description's meaning but enrich it with missing key
     identifiers.
   - `metadata.type` — derived from the memory's **directory prefix** (see map below).
   - `metadata.keywords` — a flat list of 3–10 concrete searchable identifiers extracted from the
     BODY that don't fit naturally in the description: usernames/credential keys (`claude_admin`),
     ports, WP option/meta keys, CLI/command names, script filenames, env vars, domain slugs.
     Literal identifiers only — never generic words ("configuration", "setup") and never secret
     VALUES (a password itself stays in the body, only its existence/username goes in front-matter).
     Omit the key entirely when the body has no such identifiers.
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
  keywords: [security-scanner.php, convenely_security_scan_event, composer.json allowlist]
---
```

A flat `type:` block is converted into this shape. The `name`/`description` values are preserved
(enriched, not replaced). `metadata.keywords` is present only when the body carries concrete
identifiers (see Derive rules); a keywords-free block is still standard.

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

For each in-scope memory: read it, classify, and derive `name` / `description` / `metadata.type` /
`metadata.keywords` per the rules above. Record an action per memory:
`add` (no front-matter) | `collapse` (stacked blocks → one) | `convert` (flat → nested) |
`repair` (nested but non-standard) | `enrich` (search-poor description/keywords) |
`ok` (already exactly the standard).

### Stage 3: Write (per memory that needs it)

Apply the block **only through the Serena memory MCP tools** — raw `Edit`/`Write` on
`.serena/memor*` is hard-blocked by the pre-edit gate (`swe_pre_edit_validate.py`):

- **Add** (no front-matter): prepend the new `---…---` block above the existing content using
  `mcp__plugin_swe_serena__edit_memory` with `mode="regex"`, `needle="^"`, `repl="<block>\n\n"`
  (anchored at the start), or read + `write_memory` the full `<block>\n\n<original-body>`.
- **Convert** (flat → nested) / **Repair** (nested but non-standard) / **Enrich** (search-poor):
  replace the entire existing leading `---…---` block with the standard one via `edit_memory`
  (match the exact old `---…---` span, `mode="literal"`). The body after the block is left
  byte-for-byte unchanged.
- **Collapse** (stacked blocks): replace ALL consecutive leading `---…---` blocks with the single
  merged standard block in ONE `edit_memory` call (match the full stacked span). NEVER prepend or
  insert a new block while an old one remains — that is what creates stacked blocks. After any
  front-matter write, re-read the memory and confirm exactly one leading block.

Never alter the body. After each write, the `swe_post_memory_index.py` hook may remind you to index
new memories — that is unrelated to front-matter; ignore for existing memories.

### Stage 4: Verify

- Re-run for a sample: read 2-3 changed memories, confirm the block parses and the body is intact.
- Confirm idempotency: a second pass over an already-fixed memory reports `ok` (no write).

## Idempotency

Running twice is safe: a memory already in the nested shape with a directory-derived type and a
search-rich description/keywords is reported `ok` and left untouched. Only
`add`/`collapse`/`convert`/`repair`/`enrich` memories are written; a second pass over an enriched
memory finds its identifiers already in the front-matter and reports `ok`.

## Skill Return

```markdown
- **Skill**: swe-memory-frontmatter
- **Status**: success | needs_clarification
- **Scope**: <scope or "all">
- **Audited**: <count>
- **Added**: <count>   (front-matter created)
- **Collapsed**: <count>   (stacked blocks → one)
- **Converted**: <count>   (flat → nested)
- **Repaired**: <count>   (nested but non-standard → standard)
- **Enriched**: <count>   (search-poor description/keywords)
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
