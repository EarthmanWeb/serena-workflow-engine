---
name: swe-memory-audit
version: 1.0.0
description: "Audit every project memory against the terse-imperative machine-readable standard (ref/REF_MEMORY_STYLE) and rewrite legacy-style memories in place. Detects suggestion-mood phrasing, conversational prose, vague quantifiers, and missing front-matter; rewrites the body to imperative commands while preserving EVERY behavioral rule, routing row, threshold, and step-report line. Complements /swe-memory-frontmatter (which only normalizes the front-matter block). Mutates only through the Serena memory MCP tools."
workflow:
  aware: true
  callable_from:
    - WF_CLASSIFY
    - WF_EXECUTE
  default_return: WF_CLASSIFY
  supports_standalone: true
args:
  - name: scope
    description: "Optional directory-prefix filter (e.g. ref, feedback, feature) to limit the audit to one topic. Omit to audit ALL writable memories."
    required: false
---

## ⚠️ WORKFLOW INITIALIZATION

**If starting a new session**, first read workflow initialization:

```
mcp__plugin_swe_serena__read_memory("wf/WF_INIT")
```

Follow WF_INIT instructions before executing this skill.

---

# /swe-memory-audit [scope]

Bring every writable project memory into compliance with the memory instruction-language standard. Read the standard first — it is the authority this skill enforces:

```
mcp__plugin_swe_serena__read_memory("ref/REF_MEMORY_STYLE")
```

Memories are commands FOR CLAUDE. Legacy-style memories (prose, suggestions, vague quantifiers) lower guardrail adherence. This skill finds them and rewrites them to terse, imperative, concrete commands — with ZERO loss of behavioral rules.

## Relationship to /swe-memory-frontmatter

- `/swe-memory-frontmatter` — fixes only the leading `---…---` block; NEVER touches the body.
- `/swe-memory-audit` (this skill) — fixes the BODY (prose → imperative), and also adds a front-matter block if missing.

Run `/swe-memory-frontmatter` first for a fast front-matter-only pass, then this skill for the deeper style rewrite. This skill subsumes the front-matter add, so running it alone is sufficient.

## Legacy markers (what makes a memory fail)

A memory is LEGACY and MUST be rewritten if it has any of:

| Marker | Fix |
| --- | --- |
| Suggestion mood ("you should", "consider", "it's a good idea to", "try to", "feel free to") | Rewrite as an imperative command. |
| Conversational opener ("Let me…", "Now …", "This document describes…", "In order to…") | Delete; lead with the command. |
| Vague quantifier ("a few", "some", "small", "large", "as appropriate") where a value fits | Replace with a concrete threshold/count. |
| Prose paragraphs where bullets/tables fit | Convert to one-rule-per-bullet or a condition→action table. |
| Missing front-matter block | Add `--- name / description / metadata.type ---`. |
| Rationale/examples that do NOT prevent a specific misapplication | Delete. KEEP only anti-misapplication "why" clauses. |

## Stages

### Stage 1: Discover

```
mcp__plugin_swe_serena__list_memories(topic="<scope>")   # scope arg, or omit topic for ALL
```

Skip (managed elsewhere or exempt):
- `WM_*` / `wm/*` — ephemeral session working memory.
- `MEMORY` — the index (governed by `swe_post_memory_index.py`, not this skill).
- `ref/REF_MEMORY_STYLE` — the authority; it quotes the anti-patterns it forbids.
- Any memory under `read_only_memories` — cannot be written; report as Skipped.

### Stage 2: Classify (per memory)

For each in-scope memory: read it, scan for the legacy markers above. Record an action:
`rewrite` (has ≥1 legacy marker) | `ok` (already conforms).

The `swe_post_memory_style.py` hook flags the same markers on every write — treat any memory it has flagged as `rewrite`.

### Stage 3: Rewrite (per memory that fails)

Rewrite the FULL memory to the standard via the Serena memory MCP tools (raw `Edit`/`Write` on `.serena/memor*` is hard-blocked by `swe_pre_edit_validate.py`):

```
mcp__plugin_swe_serena__write_memory(memory_name="<name>", content="<rewritten>")
```

**MANDATORY preservation — ZERO rule loss.** The rewrite changes language density and framing ONLY. Every one of these MUST survive verbatim in meaning:
- Every behavioral rule and prohibition.
- Every routing-table row and transition target.
- Every threshold, count, path, tool name, flag, and gate condition.
- Every step-report line (e.g. `> **On step WF_X**`).
- Every anti-misapplication "why" clause.

If unsure whether a clause is a rule or filler, KEEP it.

Apply the standard: imperative mood, concrete over vague, negative constraints first-class, CAPS only for hard-stops, front-matter block first, headings + terse bullets/tables, cut conversational filler and non-anti-misapplication examples.

### Stage 4: Verify

- Read 2-3 rewritten memories: confirm front-matter parses, every routing row/threshold/step-report line is present.
- Confirm idempotency: a second pass reports `ok` (no write) for an already-rewritten memory.

## Idempotency

Running twice is safe. A memory already conforming reports `ok` and is left untouched.

## Skill Return

```markdown
- **Skill**: swe-memory-audit
- **Status**: success | needs_clarification
- **Scope**: <scope or "all">
- **Audited**: <count>
- **Rewritten**: <count>
- **OK**: <count>
- **Skipped**: <count>   (read-only / WM / index / authority)
- **Next Step Hint**: WF_CLASSIFY
```

## Exit

> **Skill /swe-memory-audit complete** — memories rewritten to the terse-imperative standard; all behavioral rules preserved.

## Troubleshooting

- **`write_memory` refused (read-only)** — the memory matches a `read_only_memory_patterns` entry. Report under Skipped; do not force it.
- **Raw `Edit`/`Write` blocked** — expected; use the Serena memory MCP tools (Stage 3).
- **A rule went missing after rewrite** — you cut a rule as filler. Restore from the memory revision and redo, keeping every routing row/threshold/step-report line.
