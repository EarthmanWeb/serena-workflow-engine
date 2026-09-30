---
name: WF_CLASSIFY Sweep Details — Dispositions, WM Rejection, Regression Route
description: Detailed mechanics for the Step 4d Feature Knowledge Sweep — disposition rules, WM server rejection behaviors for the Affected Features write, and the regression route. Open when a write is rejected, a disposition (planned/deferred/ruled-out) needs justification, or the regression route applies.
metadata:
  type: reference
obligations:
  - Give every Tier-0 digest a disposition (read, planned, ruled out, deferred) before transitioning — none may be silently dropped.
  - Cite every `**Rules planned**:` name as `(mem:<name>)` on a `## Compliance Checklist` line or the WM write is rejected.
---

# WF_CLASSIFY Sweep Details

## Tier-0 Source Enumeration (full)

Enumerate related-memory candidates from THREE sources before the front-matter extraction:

1. Primary FEATURE memory's Related Memories section and `[[links]]`.
2. `MEMORY.md` index lines matching the feature area/domain terms.
3. `search_memories_by_name("<feature key / domain terms>")` — catches memories neither the feature table nor MEMORY.md lists.

Output of the Tier-0 pass: full awareness of every candidate's name+description+obligations, ~1-2k tokens — input to dispositions below, not a substitute for a Tier-1 body read.

## Tier-1 Dispositions (full rules)

1. **READ** — HARD CAP: primary `FEATURE_*` + secondary `FEATURE_*` memories the request explicitly touches + at most 3 directly-relevant `REF_*`/`DOM_*`/`SYS_*`/`ARCH_*` refs whose Tier-0 digest intersects the task's touched surfaces.
2. **DEFER** — cold refs (tangential subsystems, sibling-feature detail the request never touches). Every link this task surfaces ends in one of: read (`**Memories loaded**:`), planned (`**Rules planned**:` + Compliance Checklist line), or deferred (`**Memories deferred**:`).
   - Canonical sweep rule: a link surfaced by the PRIMARY feature cannot be deferred — READ it (counts against the 3-ref cap) or, past the cap, PLAN it (obligations → Compliance Checklist) or RULE IT OUT with a reason. Docpending satisfaction for primary links = read ∪ planned ∪ ruled-out; for other links = read ∪ deferred ∪ planned ∪ ruled-out.
3. **PLANNED** — a Tier-0 digest intersects the task but doesn't clear the Tier-1 cap. Its `obligations:` lines copy into WM `## Compliance Checklist` as `- [ ] <obligation text> (mem:<name>)`, unread. Not a body read — a scoped IOU. WF_EXECUTE reads the body on-miss before implementing that item. WF_VERIFY rejects a planned item verified from the digest alone.
4. **RULED OUT** — Tier-0 digest judged genuinely irrelevant. Note on `**Rules ruled out**:` with a MANDATORY reason (unlike deferred, where a reason is optional).
5. **ON-MISS EXPANSION** — the moment a deferred/planned ref turns out to matter (a rule needed, a pattern the edit must follow, a docpending link the work surfaces), read the body then, before the dependent edit. Expected, not a failure.

Cross-cutting tasks (≥3 sibling features): load the shared parent feature + its `ARCH_*` only; defer per-child feature memories to on-miss. Do NOT enumerate every sibling up front.

## Sweep Exclusions (full)

Do NOT bulk-read these during Step 4d, even when Tier-0 surfaces a hit:

- `spec/`, `report/` — EXCLUDED from sweeps entirely: never bulk-loaded, never demanded by a sweep, no disposition (read/planned/ruled-out/deferred) needed. A hit from ANY sweep search (4b feature/fuzzy/symptom) is not a sweep obligation — it is never turned into a docpending link or a required WM disposition. Load a spec/report ONLY when the task explicitly names it (asks to review, author, or implement that exact spec) — exactly that one, nothing else from the topic.
- `research/`, `project/` — excluded from BULK loading as general context only.
- `dev/` standards — edit-time compliance; load at `WF_ARCH_REVIEW` or the start of `WF_EXECUTE`, scoped to touched files.
- `wf/`, `claude/`, `WM_*` — workflow machinery, not feature knowledge.

Sweep idempotence: a memory already read THIS SESSION never re-loads on reclassify, `/swe-goto`, or `WF_CONTINUE`. WM `**Memories loaded**:` is the dedupe ledger; the verifier accepts prior-turn/prior-task reads from this session.

Rationale: reading the entire `[[link]]` closure up front is the dominant per-task token cost and most goes unused. Tiered loading keeps the enforcement floor (primary + task-relevant knowledge in context before any edit) while deferring cold refs. When genuinely unsure whether a ref is relevant, read it.

## `**Memories deferred**:` mechanics

- A `docpending` link this task surfaced must land in ONE of: loaded, planned, or deferred — otherwise the write is rejected.
- To defer: put memory names on a `**Memories deferred**:` line, comma-separated or one per line. Reason optional; if added, can cover the whole line, e.g. `- **Memories deferred**: ref/REF_A, ref/REF_B — cold: PHP-only`.
- Cannot defer a link surfaced by the Primary feature — read those (see canonical sweep rule above). Deferral is for links raised by a paused/other feature during a pivot.
- Only defer what's genuinely cold. When unsure, read it.
- Only links surfaced since the LAST passed sweep are in play — a passed sweep's links are settled; never re-defer a prior task's docs.

## `**Rules planned**:` mechanics

- Every name is a Tier-0 digest whose intersection with the task earned a PLANNED disposition: its `obligations:` lines copy into WM `## Compliance Checklist` as `- [ ] <obligation text> (mem:<name>)`, one item per line, unread.
- Citation is MANDATORY: the WM server cross-checks every `**Rules planned**:` name against checklist `(mem:<name>)` tags and rejects the write on mismatch either direction (planned name with no citation, or citation with no planned name).
- WF_EXECUTE reads the body on-miss before implementing the gated item. WF_VERIFY rejects a planned item checked done without a body read backing it.

## `**Rules ruled out**:` mechanics

- Every name is a Tier-0 digest judged genuinely cold to the task's touched surfaces. Reason mandatory, stays with the name on the same entry.
- Not re-litigated later in the same sweep window; a later on-miss discovery that it matters reopens it as planned or loaded, superseding the ruled-out entry.

## WM Server Enforcement (Affected Features write)

- Every name in `**Memories loaded**:` must have an ACTUAL `read_memory` THIS SESSION — prior-turn/prior-task reads from this session count; never re-read just to satisfy the verifier. Names with no read this session → update rejected.
- List must include ≥1 `feature/*` memory, or state `no-feature` (only when BOTH Step 4b searches returned nothing).
- Every `**Rules planned**:` name must be cited as `(mem:<name>)` on a Compliance Checklist line — rejected otherwise.
- A verified write creates the sweep sentinel; the edit gate (`swe_pre_edit_validate.py`) DENIES every Edit/Write/Serena-edit until it exists. Test-artifact edits additionally require `dev/DEV_TESTS` + `feature/FEATURE_TESTS` reads when the project has them.
- Refilling the docs-first search budget with one memory read is NOT the sweep.
- Enforcement is per task: follow-up tasks re-arm the `Affected Features` WRITE; reads dedupe per session (sweep idempotence, above).

## Regression Route (detail)

When WM has `regression: recent` (Step 2): route to `WF_RESEARCH` with the Feature Knowledge Sweep DEFERRED. Recency triage + runtime observation run FIRST; feature/doc memories load on-miss, keyed to the component the evidence implicates. Note "sweep deferred: regression route" in WM Affected Features. The edit gate still requires the sweep before any later edit — the deferral moves it after evidence, it never removes it.
