---
name: Memory Instruction-Language Standard
description: MANDATORY style for all project memories — terse, imperative, machine-readable commands for Claude. Every memory MUST conform; legacy-style memories MUST be rewritten on sight.
obligations:
  - Write every memory in imperative mood with concrete thresholds/names/paths — NEVER suggestion-mood ("should", "consider") or vague quantifiers ("some", "a few").
  - Rewrite a memory to this standard immediately on sight of any legacy marker (missing front-matter, conversational prose, suggestion mood) — do not defer.
  - Split any memory over 16,000 chars into a hub + children via `/swe-memory-size-audit`; act immediately on a `📏 MEMORY SIZE` advisory.
metadata:
  type: reference
---

# Memory Instruction-Language Standard

Authority for how EVERY memory in this project is written. Memories are commands FOR CLAUDE, not documentation for humans. Optimize for machine adherence, not human readability.

Enforced by `swe_post_memory_style.py` (flags violations on `write_memory`) and `/swe-memory-audit` (detects + rewrites legacy-style memories). When these flag a memory, rewrite it to this standard immediately — do not defer.

## Hard Rules (NEVER violate)

1. **Imperative mood only.** Write commands: "Read X.", "Route to Y.", "Refuse when Z." NEVER "you should", "consider", "it's a good idea to", "you may want to", "try to". A rule phrased as a suggestion WILL be treated as optional.
2. **Concrete over vague — ALWAYS.** State exact thresholds, counts, names, paths. "≤5 files", "at least 2 failures", "one quote <15 words" — NEVER "small change", "a few", "be concise", "keep it short". Ambiguity is the #1 cause of instruction failure; specificity fixes more than any wording change.
3. **Negative constraints are first-class.** `NEVER` / `Do NOT` / `avoid` read as hard stops. Use them for prohibitions; make each concrete. Do NOT soften a prohibition into a preference.
4. **CAPS only for true hard-stops.** Reserve `MUST`, `NEVER`, `ALWAYS`, `STOP` for boundaries that block the workflow or corrupt state. CAPS everywhere = CAPS nowhere.
5. **Keep anti-misapplication clauses; cut everything else.** Delete conversational filler, restated context, and illustrative examples. KEEP the one-line "why" ONLY when its absence lets Claude rationalize around the rule (e.g. "the hook allowlist is not permission to skip init"). Rationale earns its place by preventing a specific, likely misapplication — nothing else.
6. **No preamble, no summary-of-what-follows, no hedging.** Lead with the command. NEVER "This section covers…", "In general…", "Note that…".

## Required Structure

- Front-matter block first (name / description / metadata.type) — REQUIRED for discovery. See below.
- Body: headings + terse bullets or tables. One rule per bullet. No paragraphs of prose.
- Use tables for routing/conditions/mappings (condition → action).
- Reference other memories as `mem:<name>` in backticks.

## Front-Matter (MANDATORY on every memory)

```
---
name: <short title>
description: <one sentence: what this memory is / when to open it>
metadata:
  type: <reference | feedback | project | feature | domain | workflow | index | architecture | spec>
---
```

Derive `type` from the directory prefix: ref→reference, feedback→feedback, feature→feature, dom→domain, wf→workflow, index→index, arch→architecture, spec→spec.

## Legacy Markers (rewrite on sight)

A memory is LEGACY and MUST be rewritten immediately if it has any of:

- Conversational or explanatory prose ("Let me…", "This document describes…", "In order to…").
- Suggestion-mood guidance ("should", "consider", "you might", "it's recommended").
- Vague quantifiers ("some", "a few", "small", "large", "appropriate") where a concrete value fits.
- Missing front-matter block.
- Examples/rationale that do not prevent a specific misapplication.

## Conform / Reject Examples

| REJECT (legacy)                                      | CONFORM (standard)                                                                                          |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| "You should probably read the feature memory first." | "Read `mem:feature/FEATURE_[KEY]` before editing."                                                          |
| "Try to keep changes small."                         | "Touch ≤5 files. If >5, STOP and route to `mem:wf/WF_ARCH_REVIEW`."                                         |
| "It's a good idea to verify state."                  | "Verify state with a tool call in the same turn before asserting it. If unverified, label it 'unverified'." |
| "This section explains the init gate."               | (delete the sentence; state the gate's rules directly)                                                      |

## Size Budget

| Status       | Chars   | Meaning                                                                      |
| ------------ | ------- | ---------------------------------------------------------------------------- |
| `ok`         | ≤8,000  | Target — no action.                                                          |
| `warn`       | ≤16,000 | Trim in place; approaching the split threshold.                              |
| `split`      | <50,000 | MUST split into hub + children.                                              |
| `unreadable` | ≥50,000 | ≥50,000 chars — Claude Code replaces the read with a 2KB preview (measured). |

Split at >16,000 chars into hub + children per `/swe-memory-size-audit` SPLIT CONTRACT. The hub keeps the
original name/path — existing `mem:` links stay valid. A `📏 MEMORY SIZE` advisory means act now — run
`/swe-memory-size-audit`, not a manual edit.

Exempt: `spec/` and `report/` memories (not loaded as general context; ignored by the size tooling).

## Self-Compliance

This memory conforms to itself. When editing it, keep it imperative, concrete, and free of filler.
