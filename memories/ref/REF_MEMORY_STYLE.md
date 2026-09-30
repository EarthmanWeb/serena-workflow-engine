---
name: Memory Instruction-Language Standard
description: MANDATORY style for all project memories — terse, imperative, machine-readable commands for Claude. Every memory MUST conform; legacy-style memories MUST be rewritten on sight.
obligations:
  - Write every memory in imperative mood with concrete thresholds/names/paths — NEVER suggestion-mood ("should", "consider") or vague quantifiers ("some", "a few").
  - Every `dom/`/`ref/`/`dev/`/`feature/` memory MUST carry an `obligations:` field (or explicit `obligations: []`) as a top-level sibling of `description`.
  - Split any memory over 16,000 chars into a hub + children via `/swe-memory-size-audit`; act immediately on a `📏 MEMORY SIZE` advisory.
metadata:
  type: reference
---

# Memory Instruction-Language Standard

Authority for how EVERY memory in this project is written. Memories are commands FOR CLAUDE, not documentation for humans. Optimize for machine adherence, not human readability.

Enforced by the `swe_post_memory_style.py` hook (flags violations on write_memory/edit_memory) and `/swe-memory-audit` (detects + rewrites legacy-style memories). When either flags a memory, rewrite it to this standard immediately — do not defer.

## Hard Rules (NEVER violate)

1. **Imperative mood only.** Write commands: "Read X.", "Route to Y.", "Refuse when Z." NEVER "you should", "consider", "it's a good idea to", "you may want to", "try to". A rule phrased as a suggestion WILL be treated as optional.
2. **Concrete over vague — ALWAYS.** State exact thresholds, counts, names, paths. "≤5 files", "at least 2 failures", "one quote <15 words" — NEVER "small change", "a few", "be concise", "keep it short". Ambiguity is the #1 cause of instruction failure.
3. **Negative constraints are first-class.** `NEVER` / `Do NOT` / `avoid` read as hard stops. Use them for prohibitions; make each concrete. Do NOT soften a prohibition into a preference.
4. **CAPS only for true hard-stops.** Reserve `MUST`, `NEVER`, `ALWAYS`, `STOP` for boundaries that block the workflow or corrupt state. CAPS everywhere = CAPS nowhere.
5. **Keep anti-misapplication clauses; cut everything else.** Delete conversational filler, restated context, and illustrative examples. KEEP the one-line "why" ONLY when its absence lets Claude rationalize around the rule. Rationale earns its place by preventing a specific, likely misapplication — nothing else.
6. **No preamble, no summary-of-what-follows, no hedging.** Lead with the command.

## Required Structure

- Front-matter block first (name / description / obligations / metadata.type) — REQUIRED for discovery.
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

## Obligations Field (REQUIRED for dom/, ref/, dev/, feature/)

Add `obligations:` as a top-level sibling of `description` (not nested under `metadata`):

```
---
name: <short title>
description: <one sentence: what this memory is / when to open it>
obligations:
  - <imperative obligation, one line, concrete>
  - <imperative obligation, one line, concrete>
metadata:
  type: <reference | domain | dev | feature | …>
---
```

- REQUIRED on every `dom/`, `ref/`, `dev/`, `feature/` memory. `obligations: []` is the conscious-none escape — write it when the memory genuinely imposes no rule (pure reference/index content); an author who skips the field entirely, rather than declaring `[]`, has not made the call.
- Each line: imperative mood, one line, concrete — the same Hard Rules that govern the body apply here, doubled. The digest IS the planning interface: WF_CLASSIFY's Tier-0 pass plans a task's Compliance Checklist FROM these lines alone, without reading the body. A vague obligation ("follow best practices") hides the rule from every task that plans against the digest instead of reading the body — write the threshold/name/path the body would state.
- 1-2 lines per memory. More than 2 means the memory covers more than one obligation-bearing concern — split it or keep only the lines a Tier-0 planner needs to seed a checklist item correctly.
- Optional (may be added, never required) outside dom/ref/dev/feature — `wf/`, `index/`, `arch/`, `spec/` carry no field requirement.
- Enforced by: `swe_pre_memory_index_gate.py` DENIES a `write_memory`/direct-`Write` that CREATES or OVERWRITES a rule-bearing-prefix memory with no `obligations:` field (`edit_memory` partial edits are not denied); `swe_post_memory_style.py` nudges toward adding the field on an edit that lacks it; `/swe-memory-obligations` backfills the field across existing memories that predate this standard.

## Legacy Markers (rewrite on sight)

A memory is LEGACY and MUST be rewritten immediately if it has any of:

- Conversational or explanatory prose ("Let me…", "This document describes…", "In order to…").
- Suggestion-mood guidance ("should", "consider", "you might", "it's recommended").
- Vague quantifiers ("some", "a few", "small", "large", "appropriate") where a concrete value fits.
- Missing front-matter block.
- Examples/rationale that do not prevent a specific misapplication.

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
