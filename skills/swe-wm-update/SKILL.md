---
name: swe-wm-update
version: 3.0.0
description: Comprehensive Working Memory update with per-step checklists
workflow:
  aware: true
  callable_from:
    - WF_START
    - WF_CLASSIFY
    - WF_RESEARCH
    - WF_CONTINUE
    - WF_ARCH_REVIEW
    - WF_SWARM_ORCHESTRATE
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

**Single source of truth for WM updates. Replaces manual REF_WM reads.**

This skill ensures comprehensive WM updates with nothing missed. Every WF_*
transition MUST use this skill instead of manual updates.

---

## Step 1: Read Current WM

```
mcp__plugin_swe_serena__read_memory("WM_{session_id}")
```

Note these **daemon-managed fields** exactly as they appear (DO NOT MODIFY):

- `**Current State**:` — daemon updates on WF_* reads
- `**Previous State**:` — daemon updates automatically
- `### Transitions` — daemon appends automatically
- `**Edit Count Since Checkpoint**:` — daemon increments on file edits
- `**Last Updated**:` — daemon timestamps automatically

---

## Step 2: Gather Data Using Step-Specific Checklist

**Find the checklist matching your `--from` argument below. Complete ALL items.**

### WF_CLASSIFY

- [ ] Features identified from INDEX_FEATURES
- [ ] FEATURE_[KEY] loaded for each feature
- [ ] Supporting memories loaded (DOM_*, SYS_*, REF_*, ARCH_*, INDEX_*)
- [ ] Requirements validated against domain memories (or "none detected")
- [ ] Task type classified (simple / medium / large / operational)
- [ ] `### Affected Features` populated with Primary / Secondary
- [ ] `**Files:**` lists key file paths from feature memories
- [ ] `### Progress` updated with classification and feature loading steps completed

### WF_RESEARCH

- [ ] Research findings summarized in `### Notes`
- [ ] Symbols / patterns discovered noted
- [ ] `**Files:**` lists files examined
- [ ] `### Progress` updated with research outcomes

### WF_CONTINUE

- [ ] Previous state verified from WM
- [ ] Resume point identified
- [ ] Progress carried forward from previous session
- [ ] `**Files:**` lists files from previous work

### WF_ARCH_REVIEW

- [ ] Design documented with explicit file paths in `### Notes`
- [ ] `**Files:**` lists files to modify/create
- [ ] Layer compliance verified (pass / fail per criterion)
- [ ] Swarm assessment completed (needed / not needed)
- [ ] User approval status noted
- [ ] `### Progress` updated with review results

### WF_SWARM_ORCHESTRATE

- [ ] Swarm configuration documented in `### Notes`
- [ ] Agent assignments noted
- [ ] Topology selected
- [ ] `### Progress` updated with orchestration steps

### WF_EXECUTE

- [ ] Current subtask status
- [ ] `**Files:**` lists files modified / created with descriptions
- [ ] Tests written / run status
- [ ] Blockers noted (if any)
- [ ] `### Progress` updated with implementation steps

### WF_CHECKPOINT

- [ ] All work since last checkpoint summarized
- [ ] `**Files:**` lists files modified with change descriptions
- [ ] Current phase / subtask status
- [ ] `### Progress` updated comprehensively

### WF_VERIFY

- [ ] CLAUDE_OBLIGATIONS compliance verified
- [ ] Architecture compliance verified
- [ ] Test coverage verified
- [ ] All progress items marked complete or noted
- [ ] `**Files:**` is complete (every file touched in session)
- [ ] Status set to `[COMPLETED]` or `[VERIFY_COMPLETE]`

### WF_DONE

- [ ] Status set to `[COMPLETED]`
- [ ] Summary of all work done in `### Context`
- [ ] All memories updated during session listed in `### Notes`
- [ ] Follow-up items documented (if any)
- [ ] `### Progress` — all items checked off

### WF_CLARIFY

- [ ] Clarification question and user response noted
- [ ] Task description updated if scope changed
- [ ] `### Progress` updated with clarification outcome

---

## Step 3: Write Complete WM

**Use ONE `write_memory` call. Preserve all daemon-managed fields exactly.**

```
mcp__plugin_swe_serena__write_memory("WM_{session_id}", "<complete content>")
```

### Template — Fill ALL Sections

```markdown
# Working Memory

## Chat: {descriptor}

Session: {session_id}

## Workflow Context

- **Calling Step**: {calling_step}
- **Feature Key(s)**: {feature_keys}
- **Session ID**: {session_id}
- **Return Step**: {return_step}
- **Invocation Mode**: {invocation_mode}
- **Current State**: {PRESERVE FROM STEP 1}
- **Previous State**: {PRESERVE FROM STEP 1}
- **Task Iteration**: {iteration}
- **Edit Count Since Checkpoint:** {PRESERVE FROM STEP 1}
- **Last Updated**: {PRESERVE FROM STEP 1}

### Transitions

{PRESERVE FROM STEP 1}

## Current Task

**[{STATUS}]**: {task_name}

### Context

{1-2 sentence description of current work}

### Feature(s)

{feature key or comma-separated list}

### Affected Features (if multi-feature)

- **Primary**: {KEY1} - {reason}
- **Secondary**: {KEY2} - {reason}

### Progress

{updated checklist — mark completed items [x], in-progress items as current}

**Files:**

- `{path1}` - {description}
- `{path2}` - {description}

### Notes

{blockers, decisions, findings, memories updated — or "None"}

## Previous Task

**[{OUTCOME}]**: {task_name} - {summary}
```

---

## Step 4: Validate Before Writing

**If ANY of these fail, gather the missing data BEFORE calling write_memory:**

- [ ] Session ID matches existing WM file (`[a-f0-9]{8}`)
- [ ] ALL daemon-managed fields preserved exactly as read
- [ ] `Feature Key(s)` is NOT empty or "(to be determined)"
- [ ] `Task` description is NOT empty or "(awaiting user task)"
- [ ] `### Progress` has actual items (not placeholder text)
- [ ] `**Files:**` lists actual files (if any were touched)
- [ ] Status reflects reality (`IN_PROGRESS` / `COMPLETED` / `BLOCKED`)

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
