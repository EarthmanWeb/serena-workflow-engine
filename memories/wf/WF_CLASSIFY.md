---
name: WF_CLASSIFY
description: Classify the task, detect requirements, load the primary feature memory plus its tiered related-memory set (Feature Knowledge Sweep), and route. First workflow state after init — classification and routing only, no task work.
metadata:
  type: workflow
---

# WF_CLASSIFY — Classify, Detect Requirements, Load Primary Feature, Route

> **On step WF_CLASSIFY**

## Entry & Non-Skippable

FIRST workflow state after init (`WF_INIT` → `CLAUDE_OBLIGATIONS` → `WF_CLASSIFY`). Hook creates the WM file and init sentinel automatically on transition in — do not create them. Every task passes through WF_CLASSIFY. NEVER skip it — its sweep sentinel gates every edit downstream; skipping it blocks WF_EXECUTE later. A feature key in WM is not a loaded `FEATURE_[KEY]` memory — features load in Step 4.

Valid paths to WF_EXECUTE: major code change → `WF_CLASSIFY` → `WF_ARCH_REVIEW` → `WF_EXECUTE`; minor code change (3b) → `WF_CLASSIFY` → `WF_EXECUTE` (arch review skipped); operational task → `WF_CLASSIFY` → `WF_EXECUTE`.

## ⛔ NO Task Work in This State

Classification and routing only. `swe_pre_edit_validate.py` HARD-BLOCKS every Edit/Write/Serena-edit call here.

ALLOWED: `read_memory` for `INDEX_FEATURES`, primary `FEATURE_[KEY]`, every Step-4d sweep memory; `search_memories_by_name`/`search_memories_by_front_matter` (4b/4d); reading the request and WM context; lightweight `list_memories`/`Glob` strictly for spec detection (2d) or the targeted feature. Memory reads = classification; source-file reads = task work.

DEFER to WF_EXECUTE/WF_ARCH_REVIEW: reading the target file; `find_symbol`/`get_symbols_overview`/`search_for_pattern`; planning the exact `needle`/`repl`; `Edit`/`Write`/`replace_content`/`replace_symbol_body`/any edit tool — HARD-BLOCKED here.

> File contents are not needed to classify task type or count files touched. Catching yourself opening the target file or reaching for an edit tool: stop, finish routing, transition first.

## Steps

### 1. Clarity Check

- Cannot classify AT ALL (hard blocker, e.g. cannot tell which of two features is targeted) → `WF_CLARIFY`
- Otherwise → continue. Do not resolve approach/design ambiguity here — defer to the single question gate at `WF_ARCH_REVIEW`.

### 2. Detect Requirements

Scan the message for behavioral/UX requirements ("should", "must", "needs to", corrections to current behavior). Found → note in WM for Step 5. None → continue.

Regression-language detection — scan for: "regressed", "just broke", "stopped working", "used to work", "broke after". Match → note `regression: recent` in WM Task Context (drives the regression route — Routing Table). Full mechanics: `mem:ref/REF_WF_CLASSIFY_SWEEP`.

### 2b. Auto-Approve Detection

Detect EXPLICIT intent to skip the WF_ARCH_REVIEW approval gate. ONLY: "skip approval" / "skip the approval gate", "don't ask for approval" / "don't stop for approval", "auto-approve" / "auto approve". "just do it", "go ahead", "run unattended" do NOT qualify.

Explicit opt-out → note `auto_approve: true` in WM (plan still presented; gate skipped). Default → approval required at WF_ARCH_REVIEW.

### 2c. Command & Skill Identification

Check for an existing command/skill before planning manual implementation: scan skills list, project/user/plugin commands; fuzzy-match intent; respect `disable-model-invocation`. Match → note `matched_skill:`/`matched_command:` in WM, invoke it. No match → Step 3. Detail: `mem:ref/REF_WF_CLASSIFY_PROTOCOLS`.

### 2d. Gherkin Spec Detection

Explicit spec-authoring/TDD request → note `gherkin_spec: true`, route per Routing Table. New feature, no SPEC_* found (`list_memories(topic="spec")`, names only) → note `gherkin_spec_needed: true` (enforced at WF_ARCH_REVIEW). Existing feature + `.feature` files found → note `gherkin_spec_update: true` (enforced at WF_VERIFY). Detail: `mem:ref/REF_WF_CLASSIFY_PROTOCOLS`.

### 3. Task Type Assessment

Signals only — see Routing Table for the actual route:

- Research (explore only) — no edits planned.
- Debugging (TDD; failing tests, env-divergent).
- Operational (shell/WP-CLI/HTTP/DB/tests/deploy-check; no edits).
- Code change (bug fix/feature/refactor/doc; modifies source) — see Step 3b for arch-review necessity.
- Parallel subagents — signal detail incl. triggers and orchestrator-default rule: `mem:ref/REF_WF_CLASSIFY_PROTOCOLS`. Note `parallel_agents: true` when triggered.

Regression route — WM `regression: recent` (Step 2) → Feature Knowledge Sweep DEFERRED (loads on-miss after evidence); note "sweep deferred: regression route" in WM Affected Features. Edit gate still requires the sweep before any edit. Full detail: `mem:ref/REF_WF_CLASSIFY_SWEEP`.

### 3b. Architecture Review Necessity Check (Code Changes Only)

REQUIRES `WF_ARCH_REVIEW` if ANY: new feature; major module addition; touches MORE than 5 files; touches 3+ layers OR `parallel_agents` noted; `gherkin_spec_needed: true` (2d).

MAY SKIP → `WF_EXECUTE` ONLY if ALL: minor patch to EXISTING functionality; ≤5 files; all design questions resolved. Skipping: note `arch_review_skipped: true` + reason in WM; still load relevant DEV__/DOM__ standards scoped to touched files at start of WF_EXECUTE; WF_EXECUTE reveals a larger change → STOP, route back to `WF_ARCH_REVIEW`. When in doubt, do NOT skip. Full criteria: `mem:ref/REF_WF_CLASSIFY_PROTOCOLS`.

## Step 4: Feature Loading (Gate)

Complete all substeps first.

### 4a. Read Feature Registry

`read_memory("index/INDEX_FEATURES")`

### 4b. Identify All Affected Features

Scan request for feature indicators: explicit names, file paths, cross-cutting concerns, domain terminology.

MANDATORY fuzzy fallback — registry can lag, absence from `INDEX_FEATURES` is NOT absence of a feature memory: no row matches, or match uncertain → run BOTH `search_memories_by_name("<key terms>")` AND `search_memories_by_front_matter("<key terms>")` on the request's key nouns. Do not conclude "no feature memory exists" without both returning nothing. A hit outside the registry IS the primary feature — use it, note the gap in WM.

MANDATORY symptom search: search memories on the request's LITERAL symptom tokens (error strings, class names, option keys) — surfaces memories feature-noun searches miss.

Body-content search: when name/front-matter search misses, search memory BODIES via `mcp__plugin_swe_serena__search_for_pattern(substring_pattern="<terms>", relative_path=".serena/memory")` — NEVER Bash/Grep/Glob/Read on memory trees (`swe_pre_memory_fs_gate.py` denies both reads and shell writes into `.serena/memory/`, `.serena/memories/`, and the auto-memory symlink).

### 4c. Load the Primary FEATURE_[KEY]

`read_memory("feature/FEATURE_[KEY]")`. Note its Related Memories/`[[linked]]` names — they seed the sweep in 4d.

### 4d. Feature Knowledge Sweep (MANDATORY — every route) — TWO-TIER

Load the feature's knowledge set before transitioning — the sweep sentinel unlocking WF_EXECUTE edits is verified against this load (4e). TWO tiers, always: cheap front-matter digest (TIER 0) then a hard-capped full-body read of the task-relevant subset (TIER 1). Every candidate rule gets a disposition (read/planned/ruled-out/deferred) — nothing silently skipped. Full rules, cross-cutting handling, idempotence, source enumeration: `mem:ref/REF_WF_CLASSIFY_SWEEP`.

#### TIER 0 — Digest Pass (ALWAYS, ONE extraction)

Enumerate candidates from the primary FEATURE memory's links, `MEMORY.md` index, and `search_memories_by_name`. Then run ONE sanctioned front-matter extraction (`name`+`description`+`obligations`) with ONE call:

```
mcp__plugin_swe_serena__search_memories_by_front_matter(query="<task key terms>")
```

Returns name/description/obligations across every `.serena/memory-paths.conf` root, incl. aliased trees and plugin memories — NEVER Bash/awk/grep over `.serena/memory/` (`swe_pre_memory_fs_gate.py` denies it).

No `obligations:` field → digest by `description:` alone.

#### TIER 1 — Body Pass (task-relevant subset, HARD-CAPPED)

READ — HARD CAP: primary `FEATURE_*` + secondary `FEATURE_*` the request EXPLICITLY touches + at most 3 directly-relevant `REF_*`/`DOM_*`/`SYS_*`/`ARCH_*` refs whose Tier-0 digest intersects the task's touched surfaces. DEFER cold refs. Canonical rule: a link surfaced by the PRIMARY feature cannot be deferred — READ it (counts against the cap) or, past the cap, PLAN or RULE IT OUT with a reason. Unsure → read it. Full mechanics: `mem:ref/REF_WF_CLASSIFY_SWEEP`.

Exclusions — do NOT bulk-read during the sweep:

- `spec/`, `report/`, `research/`, `project/` — EXCLUDED from sweeps: never bulk-loaded, never demanded, no disposition needed. Load one ONLY when the task explicitly names it.
- `dev/` standards — loaded at `WF_ARCH_REVIEW`/`WF_EXECUTE` start, scoped to files.
- `wf/`, `claude/`, `WM_*` — workflow machinery.

Sweep = memory reads ONLY — no source reads, symbol lookups, or edits.

### 4e. Update WM with Features + Loaded Memories (ENFORCED)

ONE `swe_wm_update` call, `session_id` passed explicitly (printed in every hook message: `WM[<id>]` / `session="<id>"`). NEVER omit it — wrong/missing session_id silently fails verification:

```
mcp__plugin_swe_swe-wm__swe_wm_update(
  session_id="<id from hook messages>",
  status="IN_PROGRESS",
  sections=[{"section": "Affected Features", "content": <below>}, …])
```

```markdown
## Affected Features

- **Primary**: [KEY1] - [reason]
- **Secondary**: [KEY2] - [reason]
- **Memories loaded**: [comma-separated PLAIN names — Tier-1 set actually read in 4d; no annotations; excludes init chain (`wf/*`, `claude/*`)]
- **Memories deferred**: [only if deferred — names only, e.g. `ref/REF_A, ref/REF_B`; reason optional]
- **Rules planned**: [Tier-0 digest names given PLANNED disposition, e.g. `dom/DOM_A` — each MUST appear as `- [ ] <obligation> (mem:<name>)` on the Compliance Checklist, or the write is rejected]
- **Rules ruled out**: [`<name> — <reason>` entries; reason MANDATORY]
```

Docpending satisfaction: primary links = read ∪ planned ∪ ruled-out; other links = read ∪ deferred ∪ planned ∪ ruled-out.

HARD-ENFORCED per task: every `**Memories loaded**:` name needs an ACTUAL `read_memory` THIS SESSION or rejected; list must include ≥1 `feature/*` memory or state `no-feature`; every `**Rules planned**:` name cited as `(mem:<name>)` on a Compliance Checklist line, rejected otherwise. Verified write creates the sweep sentinel gating all edits. One docs-first read ≠ the sweep. Full enforcement: `mem:ref/REF_WF_CLASSIFY_SWEEP`.

## Step 5: Validate Requirements Against Domain Memories

Step 2 detected requirements → check DOM_* memories: NEW → note it, added post-implementation; CONFLICTING → note conflict in WM (do NOT route to WF_CLARIFY — defer to the single question gate at `WF_ARCH_REVIEW`); EXISTING → acknowledge, already documented. No requirements at Step 2 → skip.

## Step 6: Note Key Information for Implementation

From loaded feature memories, record: file paths, class/function names for Serena lookups, test commands, architecture patterns.

## Skill Invocation Protocol

Routing to a workflow-aware skill: set WM context (calling step, feature key, session ID, return step, mode), inform user, route by return status. Protocol: `mem:ref/REF_WF_CLASSIFY_PROTOCOLS`.

## Routing Table

Single source of truth for routing — determine which condition applies, read that WF_* memory, report the new step to the user:

- Hard blocker, cannot classify → `WF_CLARIFY`
- Research only → `WF_RESEARCH`
- Regression language (`regression: recent`) → `WF_RESEARCH`, sweep deferred
- Test debugging needed → `WF_DEBUG_TDD`
- Approach/design ambiguity or conflict → defer to `WF_ARCH_REVIEW`
- Operational task, no code changes → `WF_EXECUTE`
- Minor patch, ≤5 files, no open Qs (3b) → `WF_EXECUTE` (`arch_review_skipped: true`)
- New feature / major module / >5 files / 3+ layers (3b) → `WF_ARCH_REVIEW`
- Parallel subagents → `WF_ARCH_REVIEW`
- Gherkin spec authoring (explicit) → `/swe-gherkin-spec`
- Gherkin TDD from existing spec → `/swe-gherkin-dev`

Update WM via `/swe-wm-update --from WF_CLASSIFY` before transitioning.
