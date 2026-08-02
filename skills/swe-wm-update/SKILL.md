---
name: swe-wm-update
version: 4.1.0
description: Comprehensive Working Memory update with per-step checklists using swe-wm MCP tools
workflow:
  aware: true
  callable_from:
    - WF_CLASSIFY
    - WF_RESEARCH
    - WF_CONTINUE
    - WF_ARCH_REVIEW
    - WF_EXECUTE
    - WF_CHECKPOINT
    - WF_VERIFY
    - WF_DONE
    - WF_CLARIFY
  default_return: null
  supports_standalone: false
  auto_transition: false
args:
  - name: from
    description: Current WF_* step name — identifies which checklist to use (required)
    required: true
---

# /swe-wm-update

**Single source of truth for WM updates. Uses `swe-wm` MCP tools for targeted section
updates — never overwrites daemon-managed fields.**

Every WF_* transition MUST use this skill instead of manual updates.

---

## ⚠️ CRITICAL: Use MCP Tools, NOT write_memory

**NEVER use `write_memory` or `edit_memory` to update WM files.** These overwrite the
entire file and risk clobbering daemon-managed fields.

**ALWAYS use `swe-wm` MCP tools:**

| Tool                      | Purpose                                       |
| ------------------------- | --------------------------------------------- |
| `swe_wm_update`           | **CANONICAL** — batched status + all section updates in ONE call; returns post-update state |
| `swe_wm_read`             | Read WM state + content (only when you need existing content to decide) |
| `swe_wm_update_section`   | Legacy single-section update (agent-owned only) |
| `swe_wm_update_status`    | Legacy status-only update of `**[STATUS]**:` tag |

**Daemon-managed fields** (updated automatically by Python hooks — DO NOT touch):

- `**Current State**:` — updated on WF_* reads
- `**Previous State**:` — updated automatically
- `### Transitions` — appended automatically
- `**Edit Count Since Checkpoint**:` — incremented on file edits
- `**Last Updated**:` — timestamped automatically

---

## Step 1: Read Current WM (only if needed)

Skip this step by default — `swe_wm_update` (Step 3) returns the post-update
state. Read ONLY when an update decision depends on existing section content
(e.g. carrying forward progress in WF_CONTINUE):

```
mcp__swe-wm__swe_wm_read(session_id="{session_id}")
```

---

## Step 2: Gather Data Using Step-Specific Checklist

**Find the checklist matching your `--from` argument below. Complete ALL items.**

### WF_CLASSIFY

- [ ] Feature(s) identified from INDEX_FEATURES
- [ ] Task description captured
- [ ] FEATURE_[KEY] loaded for each feature (incl. fuzzy-fallback hits outside INDEX_FEATURES)
- [ ] Feature Knowledge Sweep (Step 4d) completed — related FEATURE_*/REF_*/DOM_*/SYS_*/ARCH_* memories READ, list recorded in `Memories loaded`
- [ ] No spec/report/research/project memories read (unless the task explicitly targets one)
- [ ] Requirements validated against domain memories (or "none detected")
- [ ] Task type classified (simple / medium / large / operational)
- [ ] Update `Current Task` section with task + context
- [ ] Update `Feature(s)` / `Affected Features` with Primary / Secondary
- [ ] Update `Files` with key file paths from feature memories
- [ ] Update `Progress` with classification and feature loading steps completed

### WF_RESEARCH

- [ ] Research findings summarized
- [ ] Symbols / patterns discovered noted
- [ ] Update `Files` with files examined
- [ ] Update `Progress` with research outcomes
- [ ] Update `Notes` with findings

### WF_CONTINUE

- [ ] Previous state verified from WM
- [ ] Resume point identified
- [ ] Progress carried forward from previous session
- [ ] Update `Files` with files from previous work

### WF_ARCH_REVIEW

- [ ] Design documented with explicit file paths
- [ ] Update `Files` with files to modify/create
- [ ] Layer compliance verified (pass / fail per criterion)
- [ ] Parallel-subagent assessment completed (needed / not needed)
- [ ] User approval status noted
- [ ] Update `Progress` with review results
- [ ] Update `Notes` with design decisions

### WF_EXECUTE

- [ ] Current subtask status
- [ ] Update `Files` with files modified / created with descriptions
- [ ] Tests written / run status
- [ ] Blockers noted (if any)
- [ ] Update `Progress` with implementation steps

### WF_CHECKPOINT

- [ ] All work since last checkpoint summarized
- [ ] Update `Files` with files modified with change descriptions
- [ ] Current phase / subtask status
- [ ] Update `Progress` comprehensively

### WF_VERIFY

- [ ] CLAUDE_OBLIGATIONS compliance verified
- [ ] Architecture compliance verified
- [ ] Test coverage verified
- [ ] All progress items marked complete or noted
- [ ] Update `Files` — complete list of every file touched in session
- [ ] Update status to `VERIFY_COMPLETE` or `COMPLETED`

### WF_DONE

- [ ] Update status to `COMPLETED`
- [ ] Update `Context` with summary of all work done
- [ ] Update `Notes` with memories updated during session
- [ ] Follow-up items documented (if any)
- [ ] All `Progress` items checked off

### WF_CLARIFY

- [ ] Clarification question and user response noted
- [ ] Task description updated if scope changed
- [ ] Update `Progress` with clarification outcome

---

## Step 3: Write ALL Updates in ONE Batched Call

**Use `swe_wm_update` — status + every changed section together. Do NOT issue
serial `swe_wm_update_section`/`swe_wm_update_status` calls.**

```
mcp__swe-wm__swe_wm_update(
  session_id="{session_id}",
  status="IN_PROGRESS",                       # optional
  sections=[
    {"section": "Current Task", "content": "**[IN_PROGRESS]** ..."},
    {"section": "Progress", "content": "- [x] Step 1 done\n- [ ] Step 2 pending"},
    {"section": "Notes", "content": "- New finding: ...", "append": true},
  ]
)
```

- Sections apply in order; the call stops at the first error and reports what
  was applied.
- The response includes the post-update workflow state — no follow-up read.
- The legacy single-purpose tools remain available but are NOT the standard path.

**Agent-owned sections** (safe to update):

`Current Task`, `Progress`, `Files`, `Notes`, `Requirements`,
`Implementation Notes`, `Previous Task`, `Task Context`,
`Affected Features`, `Context`, `Feature(s)`

**Protected sections** (tool will reject these):

`Workflow Context`, `Transitions`

---

## Step 4: Validate

Check the `state` returned by `swe_wm_update` (re-read via `swe_wm_read` only
if the response was lost):

- [ ] Session ID is correct
- [ ] Feature Key(s) is NOT empty or "(to be determined)"
- [ ] Task description is NOT empty
- [ ] Progress has actual items
- [ ] Files lists actual files (if any were touched)
- [ ] Status reflects reality

---

## Step 5: Confirm & Resume

Output: `📋 Updated Working Memory: WM_{session_id}`

**⚠️ CRITICAL: DO NOT STOP HERE. This skill is a utility — you MUST continue.**

---

## Exit

**IMMEDIATELY resume the workflow step you were on before invoking this skill.**
This is a utility skill — no state change occurs. Your calling step's instructions
told you to invoke `/swe-wm-update` as a sub-step, NOT as a stopping point.

After outputting the confirmation line above:

1. **Do NOT wait for user input**
2. **Do NOT end your response**
3. **Continue with the next action from the calling WF** step_*

If you were invoked from a WF_* step's "MANDATORY NEXT STEP" table, proceed to
the transition listed there. If you were invoked mid-step, continue where you
left off in that step's instructions.
