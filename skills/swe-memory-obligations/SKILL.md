---
name: swe-memory-obligations
version: 1.0.0
description: "Backfill the `obligations:` front-matter field across a project's Serena memories under dom/, ref/, dev/, feature/ — the two-tier sweep's Tier-0 digest input. Fans out extraction to parallel cheap agents (sonnet/haiku), derives 1-2 imperative obligation lines per memory from its body (or `obligations: []` when genuinely none), and writes back via edit_memory. Never touches memories outside the four rule-bearing prefixes; never rewrites a body. Idempotent; safe to re-run."
workflow:
  aware: true
  callable_from:
    - WF_CLASSIFY
    - WF_EXECUTE
  default_return: WF_CLASSIFY
  supports_standalone: true
args:
  - name: scope
    description: "Optional directory-prefix filter (dom, ref, dev, feature) to limit the backfill to one topic. Omit to audit ALL four rule-bearing prefixes."
    required: false
---

## ⚠️ WORKFLOW INITIALIZATION

**If starting a new session**, first read workflow initialization:

```
mcp__plugin_swe_serena__read_memory("wf/WF_INIT")
```

Follow WF_INIT instructions before executing this skill.

---

# /swe-memory-obligations [scope]

Backfill the `obligations:` front-matter field (see `mem:ref/REF_MEMORY_STYLE` "Obligations Field") across
every `dom/`, `ref/`, `dev/`, `feature/` memory that lacks it. This field is the Tier-0 digest input
`wf/WF_CLASSIFY` Step 4d reads to plan a task's Compliance Checklist WITHOUT a full body read — a memory
missing the field is invisible to that planning pass and only surfaces on-miss, mid-task.

## Field Grammar (exact)

```yaml
---
name: <short title>
description: <one sentence>
obligations:
  - <imperative obligation, one line, concrete>
  - <imperative obligation, one line, concrete>
metadata:
  type: <domain | reference | feature | …>
---
```

- Top-level sibling of `description`, NOT nested under `metadata`.
- 1-2 lines, imperative mood, concrete (name/path/threshold, never "follow best practices").
- `obligations: []` — the conscious-none escape, for a memory that imposes no rule (pure reference/index content).

### Worked example 1 — a DOM rule → digest

Body excerpt (`dom/DOM_EXAMPLE_QUEUE.md`):

> Jobs enqueued via `enqueue_job()` MUST carry an idempotency key derived from `(user_id, action, day)`.
> A duplicate key within the same UTC day is silently dropped by the worker, not retried. Callers that
> need retry semantics must vary the key.

Derived digest:

```yaml
obligations:
  - Derive enqueue_job() idempotency keys from (user_id, action, day) — never omit the key.
  - Expect same-day duplicate keys to be silently dropped, not retried.
```

### Worked example 2 — genuinely no obligation

`ref/REF_GLOSSARY.md` is a flat term-definition list with no imperative content.

```yaml
obligations: []
```

## ⛔ NO IMPROVISATION

- Run the commands in this skill VERBATIM. NEVER compose alternative shell pipelines, `for` loops, scratch files (`/tmp` or anywhere), or awk/sed variants for a step that has a literal command below.
- Discovery is the ONE `grep -L` command in Stage 1 — nothing else. Per-memory reads are `read_memory`. Writes are `edit_memory`. Direct file access ONLY via the documented Stage-3 fallback.
- A verbatim command failing twice = STOP and report the failure output verbatim (`mem:claude/CLAUDE_OBLIGATIONS` Skill Failure Threshold). NEVER retry with an invented variant.

## Stages

### Stage 1: Discover

Two calls, EXACTLY these — nothing else:

1. The candidate list — files LACKING the field (one read-only grep; `-L` prints non-matching files; this is a memory-tree docs consult, credited by the docs gate):

```bash
find .serena/memory/dom .serena/memory/ref .serena/memory/dev .serena/memory/feature -maxdepth 1 -name '*.md' -exec grep -L "^obligations:" {} + 2>/dev/null
```

(`find -exec` form on purpose: a bare glob aborts zsh when a prefix directory is absent; this runs
identically in bash/zsh with any subset of the four directories present. Exit 1 with no output = zero
candidates.)

2. The read-only set to exclude from writes:

```
mcp__plugin_swe_serena__list_memories(topic="dom")     # repeat for ref, dev, feature (or only the scope arg's prefix)
```

- Candidates = grep output MINUS `read_only_memories`, `WM_*`, `MEMORY`. Present-even-as-`[]` files never appear in the grep output — already done.
- The grep matches `^obligations:` anywhere in a file, not only front-matter. This is deliberately dumb (the key legally appears only in front-matter per `mem:ref/REF_MEMORY_STYLE`); accept the rare false "has" rather than build a parser.
- Record `<count before>` per directory FROM THE GREP OUTPUT. No counting scripts, no scratch files.

### Stage 2: Fan Out Extraction (parallel, CHEAP agents)

Per Delegation Economics (`mem:feature/FEATURE_SUBAGENTS`): this is mechanical extraction, never main-agent
work. Batch candidates into parallel `Agent` calls, ONE message, `run_in_background: true`:

- `model: "sonnet"` — default tier, derives obligation lines from body content/judgment.
- `model: "haiku"` — ONLY for a batch that is a mechanical count/pass-through (e.g. confirming a memory is
  pure reference content and should get `obligations: []`) with no derivation judgment required.
- Each agent gets a disjoint file list (no two agents touch the same memory), the field grammar above, and
  both worked examples. Prompt contract: "You are a subagent. BYPASS WF_INIT. Read each assigned memory via
  `mcp__plugin_swe_serena__read_memory` (plain `Read` of the file path ONLY when Serena tools are absent
  from your session). For each, derive 1-2 imperative `obligations:` lines from the body (or
  `obligations: []` if genuinely none). Return the derived block per memory — do NOT write yet. Do NOT run
  shell commands." Extraction and write are separate stages so a bad derivation is caught before it lands
  (Stage 3 review).
- `swe_pre_agent_model_gate.py` enforces `model` + the bypass marker on every call — include both.

### Stage 3: Write Back

Apply each derived block via `edit_memory`, prepending/merging `obligations:` into the existing front-matter
— preserve `name`/`description`/`metadata` and the ENTIRE body byte-for-byte:

- `mcp__plugin_swe_serena__edit_memory(memory_name=..., needle="<exact existing front-matter span>", repl="<same span + obligations: block inserted after description>", mode="literal")`.
- Fall back to direct file `Edit` on the memory's path ONLY when Serena is unavailable for that call (`mcp_unavailable` degraded mode) — resume Serena writes once it reconnects; do not leave a mixed batch half-written through each path without reconciling.
- Re-read after write; confirm the field parses and the body is unchanged.

### Stage 4: Report Coverage

Re-run the EXACT Stage-1 grep. It must print nothing in scope (or only the skipped/read-only remainder,
each explained). Per directory (dom/ref/dev/feature): `<count before>` lacking the field → `<count after>`.

## Skill Return

```markdown
- **Skill**: swe-memory-obligations
- **Status**: success | needs_clarification
- **Scope**: <scope or "all">
- **Audited**: <count>
- **Backfilled**: <count> (obligations added, non-empty)
- **Declared empty**: <count> (obligations: [] written)
- **Already had field**: <count>
- **Skipped**: <count> (read-only / WM / index / wf / claude)
- **Next Step Hint**: WF_CLASSIFY
```

## Exit

> **Skill /swe-memory-obligations complete** — obligations front-matter backfilled across dom/ref/dev/feature memories; bodies unchanged.

## Troubleshooting

- **`edit_memory` refused (read-only)** — matches a `read_only_memory_patterns` entry. Report under Skipped.
- **Serena unavailable mid-batch** — fall back to direct `Edit` for the remaining memories in that agent's
  batch only; note the fallback in the coverage report.
- **Body accidentally changed** — the write replaced more than the front-matter span. Restore from the
  memory revision and redo the write matching only that span.
