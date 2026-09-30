---
name: swe-memory-size-audit
version: 1.0.0
description: "Audit a project's Serena memories for size and split any too large to be useful. Runs scripts/memory-size-audit.py against .serena/memory-paths.conf roots, classifies each ok/warn/split/unreadable, and fans out parallel split agents turning an oversized memory into a hub + children per the SPLIT CONTRACT — zero rule loss, hub keeps name/path so mem: links stay valid. Complements /swe-memory-audit (style) and /swe-memory-obligations (front-matter); fixes SIZE. Mutates via Serena memory MCP tools (plain-file edits for a plugin-source memories/ tree here)."
workflow:
  aware: true
  callable_from:
    - WF_CLASSIFY
    - WF_EXECUTE
  default_return: WF_CLASSIFY
  supports_standalone: true
args:
  - name: scope
    description: "Optional directory-prefix filter (e.g. dom, ref, feature) passed as --topic to limit the audit to one topic. Omit to audit all memories under the configured roots."
    required: false
---

# /swe-memory-size-audit [scope]

Measure every project memory's raw size and split any too large to be reliably read. Past the
unreadable threshold, Claude Code replaces the MCP read result with a ~2KB preview — content becomes
invisible to every future read. This skill finds those memories (and ones heading toward that cliff) and
splits them into a hub + focused children with ZERO rule loss.

## Relationship to /swe-memory-audit and /swe-memory-obligations

- `/swe-memory-audit` — fixes STYLE (prose → imperative); not size.
- `/swe-memory-obligations` — backfills `obligations:`; not size.
- `/swe-memory-size-audit` (this skill) — fixes SIZE (hub + children). Run after a split settles content;
  a follow-up `/swe-memory-obligations` pass backfills `obligations:` on children.

## Memory Graph Validator

Execute (do not Read into context) — checks `mem:`/`[[link]]`/backtick-CAPS links. This all-roots form is
the ONE invocation Stage 1 (baseline) and Stage 4 (post-split check) both reuse:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/validate-memory-graph.py" --plugin-root "${CLAUDE_PLUGIN_ROOT}/memories" --json
```

Project-side roots come from `.serena/memory-paths.conf` (no `--root` needed). Inside the swe plugin
source repo only, also pass `--extra-root memories` (adds the plugin's own source tree on top of conf
roots).

- Dangling (ERROR) = resolves to no known memory. Orphan (WARNING) = zero inbound links.
- **ALL-ROOTS-IN-ONE-RUN**: links cross trees (a project's `.serena/memory` links to the plugin's
  `wf/dom/feature` memories, served at runtime as `${CLAUDE_PLUGIN_ROOT}/memories:ro`). Separate-root
  runs report FALSE dangling links (measured: `.serena/memory` alone → 29; both → 12, the true count).
  Always pass every root in ONE invocation.
- **Baseline→subset rule**: take a `--json` baseline BEFORE any split (Stage 1); post-split dangling
  (Stage 4) MUST be a subset — diff programmatically, never eyeball counts.
- **New-orphan rule**: a NEW orphan among a split's children = hub's routing table missing that row =
  FAILURE, not a warning.
- `--root` accepts `alias=DIR`; no `--root` defaults to `.serena/memory-paths.conf` in cwd.

## ⛔ NO IMPROVISATION

- Run the Stage 1 measurement command VERBATIM. NEVER compose an alt `wc`/`find`/`awk` pipeline or
  hand-rolled char count where a literal command exists below.
- Splitting is delegated to parallel `Agent` calls (Stage 3) — orchestrator NEVER edits a memory body to
  shrink it directly. Command failing twice = STOP, report verbatim (`mem:claude/CLAUDE_OBLIGATIONS`
  Skill Failure Threshold). NEVER retry with an invented variant.

## Stages

### Stage 1: Measure

Run the size-audit script, exactly this form (add `--topic <scope>` only when an arg was given, and
`--sections 10` always — Stage 2 needs the per-section breakdown):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/memory-size-audit.py" --json --sections 10
```

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/memory-size-audit.py" --topic <scope> --json --sections 10
```

- Default roots come from `.serena/memory-paths.conf` in cwd (no `--root` needed in the standard case).
- Sizes are UTF-8 decoded CHARACTERS of the whole file, incl. front-matter.
- Thresholds: `ok` ≤8,000 · `warn` 8,001-16,000 · `split` 16,001-49,999 · `unreadable` ≥50,000.
  `UNREADABLE_CHARS` is MEASURED: a 50,052-char memory (front-matter stripped) read inline; 53,734/64,345
  became Claude Code's 2KB preview. If cutoff changes, re-measure with 2 probe files straddling the
  threshold before editing `memory_size.py`'s `UNREADABLE_CHARS`.
- Exit 1 means ≥1 `split`/`unreadable` memory exists.
- **Formatter detection**: check for `dprint.json`/`.dprint.json`, `.prettierrc*`, or a `package.json`
  "scripts.fmt"/"scripts.format" entry. Record the exact per-file command (Stage 3 puts it in every
  prompt); none found, state so and skip formatting.
- **Foreign trees**: a memory prefixed `<alias>/` is a sibling project's, not this one's — mark "foreign
  — out of scope", exclude from Stage 2 unless the user named that alias.
- Ignored: `spec/` (SPEC_), `report/` (REPORT_), `research/` (RESEARCH_), `project/` (PROJECT_) memories —
  both scripts skip them (audit shows `excluded=N`; the graph check ignores links/orphans originating in
  them, but links pointing to them still resolve). NEVER plan, split, or trim them.
- Present non-`ok` memories as a table: `memory | chars | tokens_est | status | sections (heading:chars)`.
- **Graph baseline** (required before any split, per Memory Graph Validator above): run that form (add
  `--extra-root memories` in the plugin source repo), saved to a scratch file:

```bash
mkdir -p .serena/cache
python3 "${CLAUDE_SKILL_DIR}/scripts/validate-memory-graph.py" --plugin-root "${CLAUDE_PLUGIN_ROOT}/memories" --json > .serena/cache/memgraph-baseline.json
```

### Stage 2: Plan

Per flagged memory, choose exactly one action:

- `split` / `unreadable` → SPLIT into hub + children (Stage 3, full SPLIT CONTRACT).
- `warn` → TRIM in place — condense prose, dedupe, move genuinely conditional content to a new child if
  that alone brings it ≤8,000; otherwise SPLIT.
- `ok` → untouched — do not include in the plan table.

**Derive child boundaries from Stage 1's `--sections 10` breakdown**: group adjacent sections so the
group's raw chars, +30% for any table-heavy section (mostly `|` rows), stays ≤8,000. Adjacent sections may
share a child; never split one section across two.

**Always-read memories** (`wf/*`, `claude/*`, any memory read at task start): hub keeps only what every
task needs; conditional content moves behind one routing-table row. Target ≤12,000 for these hubs (vs
≤8,000 general — can't omit invariant content). A task-type table, a "read when" check, and a routing
table restating the same decision: keep one, delete the rest.

Present the plan table: `memory | chars | status | action | proposed children (names)`. Name each child
per the SPLIT CONTRACT naming rule before asking approval — don't defer naming to the split agent.

Ask ONE `AskUserQuestion` for approval of the full plan. Skip only when the caller already gave blanket
consent (e.g. an orchestrating skill/agent explicitly authorized proceeding unconfirmed).

### Stage 3: Fan Out (parallel, background)

ONE message, parallel background `Agent` calls, `model: "sonnet"` (fixed-shape task; escalate per FEATURE_SUBAGENTS table if the work turns out to be design/hard-debug), ONE agent per flagged memory.
Ownership disjoint: each agent owns exactly its assigned memory plus the new children it creates — no two
agents touch the same memory/child name. Each agent prompt MUST also include: the memory's on-disk `path`
from Stage 1's `--json` output (rule 2 — don't make the agent look it up); the per-file formatter command
from Stage 1 (or "no formatter — skip formatting"); and: "You NEVER commit — the orchestrator commits
once after Stage 4 passes."

Each agent's prompt MUST start with:

> You are a subagent. BYPASS WF_INIT entirely. Do NOT read CLAUDE.md workflow. Your task is below;
> follow-up SendMessage from your orchestrator amends it.

...then embed the SPLIT CONTRACT below **verbatim** (adapt wording for the agent's specific memory
name/status/proposed children/path/formatter-command from the Stage 2 plan row; every numbered rule must
appear).

#### SPLIT CONTRACT (embed verbatim)

1. Budgets (chars, whole file incl. front-matter, MEASURED AFTER FORMATTING — rule 8): target ≤8,000 per
   file; hard max 16,000. Hub ≤8,000 (≤12,000 for an always-read hub, e.g. `wf/*`).
2. **Reading an oversized source**: if the memory is ≥50,000 chars, `read_memory` returns only a 2KB
   preview — do NOT rely on it. Read the FULL file with `Read` against the on-disk `path` in your prompt,
   in `offset`/`limit` chunks. Never reconstruct content from a preview.
3. Hub KEEPS the original name/path — `mem:` links stay valid. Hub body = invariants needed every read +
   routing table `| When | Read |`, one row per child (`mem:<child>` link + condition to open it).
4. Child naming (UPPER_SNAKE_CASE): `feature/FEATURE_<KEY>` → `dom/DOM_<KEY>_<TOPIC>`; `wf/WF_<STATE>` →
   `ref/REF_WF_<STATE>_<TOPIC>` (never new `wf/` names — FSM machinery); `spec/*` stays in `spec/`,
   `metadata.type: spec`, NO `obligations:` (not rule-bearing); all others → same directory,
   `<NAME>_<TOPIC>`.
5. Every child carries front-matter: name, description (one sentence), metadata.type (from directory),
   `obligations:` (1-2 imperative lines, or `[]`) for dom/ref/dev/feature (never `spec/`, per rule 4).
6. ZERO RULE LOSS: every rule/threshold/path/command/name/contract survives (moved or condensed, never
   dropped). Produce a rule-diff: original heading → destination.
7. **Dedupe before deleting**: before removing a block as duplicate, `grep`/`search_for_pattern` the
   CANONICAL owner memory for each fact. Delete only what the owner already states; a fact present ONLY
   in the trimmed block moves to a child, never dropped. Confirmed duplicates become a `mem:` link.
8. Style per `mem:ref/REF_MEMORY_STYLE`: terse imperative bullets, tables for mappings, no prose
   paragraphs, no filler; compress verbose table cells. **Format before measuring**: after writing each
   file, run the project's formatter (given in your prompt) ON THIS FILE ONLY — never repo-wide, since
   other agents edit sibling files in parallel. A markdown formatter pads every table cell to its widest
   cell, inflating every row (measured: one file grew 7,540 → 13,892 chars from formatting alone).
   Re-measure with `wc -m <file>` AFTER formatting — that number must meet the rule-1 budget. A table with
   any long cell becomes a bullet list instead; keep tables only where every cell is short.
9. Preserve any heading/marker code or tests parse: `grep -r "<memory-filename-without-ext>" tests/
   hooks/` BEFORE moving any heading; keep every parsed heading, marker, step number (e.g. "Step 4d") in
   the hub. After splitting, run only the matched test file via the project's scoped-test command (its
   test memory, e.g. `FEATURE_TESTS`/`DEV_TESTS`) — never the full suite from a subagent.
10. **Cross-reference check**: hub NAME is unchanged so `mem:` links stay valid, but a quoted section
    reference (e.g. `NAME "Section Title"`) to a moved section goes stale. `grep -rn "<memory-name>"
    memories/ skills/ hooks/ agents/ commands/ .serena/memory/` (adjust to what exists); report each hit
    as `file:line → new owning child`. Do NOT fix other files — Stage 4 assigns one fix agent per file.
11. Links only as `mem:<topic>/<NAME>` in backticks. Do NOT add children to MEMORY.md (hub already
    indexed).
12. Sweep interaction (SWE, hub is dom/ref/dev/feature): a `mem:` link in the hub body becomes a
    docpending link at WF_CLASSIFY. Link children ONLY from the `| When | Read |` routing table; mention
    other memories in prose by bare name, no link. Give every child accurate `obligations:`. Not tracked
    for `wf/claude/spec/report/research/project/` hubs.
13. **Write-gate override**: new dom/ref/dev/feature `write_memory` is refused without `obligations:`
    (`[]` passes) and may be flagged as a near-duplicate of its parent hub. When the gate asks, include
    `[new-memory-justified: split child of <HUB> per /swe-memory-size-audit]`. Write children first, hub
    last.

Mutation channel: project memories (any `.serena/memory` tree, incl. aliased roots) mutate ONLY via
Serena `write_memory`/`edit_memory`/`delete_memory`. A plugin-source `memories/` tree (this repo's own
shipped templates) uses plain-file `Read`/`Edit`/`Write` — never mix channels.

Each agent returns: rule-diff (heading → destination), cross-reference hit list (rule 10), and final
POST-FORMAT char counts (`wc -m`) for hub and every child created.

### Stage 4: Verify

1. Re-run Stage 1's exact command. Every file touched in Stage 3 MUST now be `ok`/`warn` at most 16,000
   chars; every hub MUST be ≤8,000 chars (≤12,000 for an always-read hub).
2. Run the SAME command as the Stage 1 baseline, redirected to a second file, then diff:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/validate-memory-graph.py" --plugin-root "${CLAUDE_PLUGIN_ROOT}/memories" --json > .serena/cache/memgraph-postsplit.json
python3 -c "import json,sys; b={tuple(x) for x in json.load(open('.serena/cache/memgraph-baseline.json'))['dangling']}; p={tuple(x) for x in json.load(open('.serena/cache/memgraph-postsplit.json'))['dangling']}; n=sorted(p-b); print(n); sys.exit(1 if n else 0)"
```

Pass = empty new-dangling list (post-split ⊆ baseline) AND no orphan among the split's new children (a
new-child orphan = hub routing table missing that row = fix it, don't waive).

3. Require each Stage-3 agent's rule-diff; confirm every original heading/rule maps to a destination.
4. **Cross-reference fix wave**: collect every `file:line → new owning child` hit from Stage-3 agents
   (rule 10). Assign each REFERENCING file to exactly one fix agent — disjoint, even if a file references
   multiple split memories — to repoint the stale reference.
5. **Trim wave**: any file still over budget (first-pass agents commonly leave hubs/children at 8-14K)
   triggers ONE agent per still-over-budget family, parallel, background, `model: "sonnet"`, same SPLIT
   CONTRACT plus the target. Re-run Stage 1 after; cap 2 waves — still over after wave 2 is STOP, report
   in Stage 5.

On any other failure (dangling link, missing rule-diff entry), re-launch a fix agent scoped to that
memory — NEVER fix it in the orchestrator directly.

### Stage 5: Report

Present a before/after table: `memory | chars before | status before | chars after (hub) | children
created | status after`. List any file still over budget after 2 trim waves as **Remaining** with current
chars — never drop it silently.

**Commit**: the orchestrator (never a subagent) commits once, here, after Stage 4 passes.

## Idempotency

A re-run where Stage 1 reports all `ok` is a no-op — Stage 2's plan table is empty; exit without approval
or agents.

## Skill Return

```markdown
- **Skill**: swe-memory-size-audit
- **Status**: success | needs_clarification
- **Scope**: <scope or "all">
- **Measured**: <count>
- **Split**: <count> (hub + children created)
- **Trimmed**: <count> (warn, fixed in place)
- **OK / untouched**: <count>
- **Dangling links after verify**: <count> (must be 0)
- **Next Step Hint**: WF_CLASSIFY
```

## Exit

> **Skill /swe-memory-size-audit complete** — oversized memories split into hub + focused children; every
> rule preserved; link graph clean.

## Troubleshooting

- **Script reports `--json` parse failure** — re-run Stage 1's exact command; never hand-parse table
  output.
- **Split agent's memory still >16,000 chars after Stage 3** — expected first-pass; it's Stage 4's trim
  wave, not a one-off fix. Re-launch a fix agent only if Stage 4 exhausted its 2-wave cap.
- **New dangling `mem:` link** (not in baseline) — a child was renamed/dropped post-rule-diff. Re-launch
  a fix agent to restore link/target.
- **Graph validator reports many dangling links** — roots ran separately; rerun all-in-one (see Validator
  above).
- **Serena `write_memory`/`edit_memory` refused (read-only)** — matches a `read_only_memory_patterns`
  entry. Report under Skipped in the before/after table; do not force it.
- **Agent got a 2KB preview, not memory content** — called `read_memory` on a ≥50,000-char source instead
  of `Read`-ing the on-disk `path` (rule 2); re-launch, passing the path explicitly.
- **File grew after formatting, not shrank** — a long table cell padded every row (rule 8). Convert to a
  bullet list, reformat, re-measure with `wc -m`.
- **`write_memory` denied (missing obligations / flagged duplicate)** — add `obligations:` (or `[]`) per
  rule 5; if dedupe fired, retry with `[new-memory-justified: split child of <HUB> per
  /swe-memory-size-audit]` (rule 13).
- **WM sweep at WF_CLASSIFY rejected a hub's child link** — child missing accurate `obligations:`, or
  linked outside the `| When | Read |` table (rule 12). Fix `obligations:` and/or move the link into the
  table.
