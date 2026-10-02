---
name: REF_WM
description: Working Memory (WM) file spec — naming, lifecycle, update rules, template, and Stop-hook fields.
obligations:
  - Name WM files exactly `WM_<SESSION_ID>.md` — NEVER add a suffix, NEVER rename.
  - NEVER update WM manually with `edit_memory`/`write_memory` — ALWAYS update via the `/swe-wm-update` skill.
metadata:
  type: reference
---

# REF_WM

## Naming

- Filename: `WM_<SESSION_ID>.md`. NEVER add a suffix. NEVER rename.
- `SESSION_ID`: 8-char prefix from the `transcript_path` UUID (e.g. `3fe6b3c5`).

## Lifecycle

| Stage       | When                    | Action                                                                            |
| ----------- | ----------------------- | --------------------------------------------------------------------------------- |
| Auto-Create | Entry into WF_CLASSIFY  | Prompt hook creates `WM_{session_id}.md` on the first transition into WF_CLASSIFY |
| Load        | Session resume          | Read file → verify session ID matches → echo to chat                              |
| Update      | After edits/transitions | Write changes. Output nothing; resume the calling step immediately.               |

- Update WM after EVERY: memory edit, file edit, workflow transition, state change.

## Anti-Patterns

- NEVER update WM manually with `edit_memory` or `write_memory`. Manual updates bypass step-specific checklists and clobber daemon-managed fields.
- ALWAYS update WM via the `/swe-wm-update` skill. It supplies step-specific checklists (no missed fields) and coordinates the daemon. Invoke as `/swe-wm-update --from WF_<STATE>`. One skill call = correct.

## Template

```markdown
# Working Memory

## Chat: <descriptor>

Session: <SESSION_ID>

## Workflow Context

- **Calling Step**: WF_CLASSIFY
- **Feature Key(s)**: BLOCKS
- **Session ID**: 3fe6b3c5
- **Return Step**: WF_CLASSIFY
- **Invocation Mode**: workflow
- **Current State**: WF_EXECUTE
- **Task Iteration**: 1
- **Edit Count Since Checkpoint:** 0

## Current Task

**[STATUS]**: [Task Name]

### Context

[1-2 sentences]

### Feature(s)

[Single feature key OR comma-separated list]

## Open Decisions

- [ ] <decision> — options: <A> | <B>
- [x] <decision> — resolved: <choice>

### Progress

- [ ] Step 1
- [x] Step 2

**Files:** `path/to/file.php` - [note]

## Previous Task

**[OUTCOME]**: [Task name] - [summary]

## Completed Tasks (This Session)

<!-- Used when multiple tasks are completed in same session -->

### Iteration 1: [Task Title]

- Status: ✅ Completed
- Summary: [What was done]
- Files Modified: [list]
```

## Workflow Context Fields (REQUIRED for Stop Hook)

| Field                         | Purpose                                         |
| ----------------------------- | ----------------------------------------------- |
| `Calling Step`                | Which WF_* invoked the current action           |
| `Current State`               | CRITICAL — active state, read by the stop hook  |
| `Feature Key(s)`              | Active feature(s) from `INDEX_FEATURES`         |
| `Session ID`                  | 8-char unique ID                                |
| `Return Step`                 | Where to return after completion                |
| `Invocation Mode`             | `workflow` \| `standalone` \| `subagent`        |
| `Task Iteration`              | Counter for tasks in same session (starts at 1) |
| `Edit Count Since Checkpoint` | Edits since last WM update (reset on new task)  |

## Stop Hook Behavior

| State                                     | Behavior                   |
| ----------------------------------------- | -------------------------- |
| `WF_DONE`, `WF_CLEANUP`                   | Clean exit                 |
| `WF_EXECUTE`, `WF_DEBUG_TDD`, `WF_VERIFY` | ⚠️ Warning: incomplete work |

## Skill Return Section (Optional)

```markdown
## Skill Return

- **Skill**: research
- **Status**: success_with_findings
- **Findings Summary**: [brief]
- **Artifacts**: [list]
- **Next Step Hint**: WF_CLASSIFY
```

- Status codes: `success`, `success_with_findings`, `needs_clarification`, `blocked`, `escalate_complexity`.

## Open Decisions Ledger

Section heading: `## Open Decisions`.

- Record on discovery: `- [ ] <decision> — options: <A> | <B>`
- Under blanket consent (`blanket_consent: true`): record, act, ask at WF_DONE — pick the most logical option, act on it, record `- [ ] <decision> — options: <A> | <B> — deferred: chose <A>`, keep working. Deferred entries do NOT block the stop gate before WF_DONE; in WF_DONE every unchecked entry blocks.
- Resolve via AskUserQuestion, then mark: `- [x] <decision> — resolved: <choice>`. For a deferred entry list the provisional choice first as recommended; a different answer → apply the change before ending.
- Record a decision the moment an option/follow-up for the user is identified — in ANY state.
- NEVER leave an option in reply prose without a ledger entry.
- Resolve every `- [ ]` entry via AskUserQuestion before ending the task; mark `[x]` with the chosen option.
- Stop gate blocks turn end while unchecked entries exist.

## Rules

- One WM file per conversation.
- Echo the session ID on every WM operation.
- Verify session ID on load.
- Update WM after significant actions.
- NEVER do single-field state edits.
- WM filename is always `WM_{session_id}` — NEVER add suffixes or rename.
