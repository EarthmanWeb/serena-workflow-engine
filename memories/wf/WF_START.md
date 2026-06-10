# WF_START - Entry Point

> **On step WF_START**

---

## Execute These Steps

### 1. Check Feature Registry

```
mcp__plugin_swe_serena__read_memory("index/INDEX_FEATURES")
```

If INDEX_FEATURES doesn't exist or has no registered features, go to `WF_ONBOARD`. Do not proceed with other steps.

### 2. Identify Relevant Feature(s)

Determine which feature(s) this conversation is about:

1. **From user context** — Did user mention feature names, keys, or file paths?
2. **From file paths** — If files are mentioned, which feature(s) contain them?
3. **Cross-feature indicators** — Does request span multiple areas?
4. **Ask if unclear** — "Which feature(s) are you working on? [list from INDEX_FEATURES]"

Record the feature key(s) in WM. Feature memories will be loaded in WF_CLASSIFY.

**Fallback:** If a feature is NOT found in MEMORY.md or INDEX_FEATURES, call `list_memories(topic="feature")` to discover feature memories that exist but are not yet indexed. If the feature memory exists but is missing from MEMORY.md, add the index entry to MEMORY.md before proceeding. If, after checking `list_memories()`, the FEATURE_[KEY] still doesn't exist, go to `WF_ONBOARD`.

### 3. Read CLAUDE_OBLIGATIONS

```
mcp__plugin_swe_serena__read_memory("claude/CLAUDE_OBLIGATIONS")
```

### 4. WM File

The WM file is required before proceeding.

---

#### HOW WM STATE UPDATES WORK

The hook daemon manages `Current State` automatically. When you read any `WF_*` memory, the `swe_post_read_state` hook validates the transition, updates `**Current State**:` in the WM file, and appends a transition log entry.

Do not manually rewrite the WM file to update `Current State`. The daemon handles this.

**What you own in WM:**

- `## Current Task` — task description, affected features
- `## Progress` — status updates on work done (not `### Transitions`)
- `## Previous Task` — completed tasks

**What the daemon owns in WM:**

- `**Current State**:` — updated on each WF_* read
- `**Previous State**:` — updated automatically
- `### Transitions` — appended automatically
- `**Edit Count Since Checkpoint**:` — incremented on each file edit
- `**Last Updated**:` — timestamp updated automatically

To update task context (not state), invoke `/swe-wm-update`. Do not manually update WM with `edit_memory` or `write_memory`.

---

#### WM Auto-Creation

The WM file is auto-created as `WM_{session}.md` when you first read `WF_START`. The hook creates it with the correct format including `## Workflow Context` and `**Current State**: WF_START`.

Do not create your own WM file from scratch. The auto-created file has the exact format the init gate expects.

After auto-creation, update the task-specific sections:

```
/swe-wm-update --from WF_START
```

Do not rename the WM file. The `WM_{session}` name is permanent for the session.

---

#### New Task After WF_DONE (Same Session)

Do not create a new WM. Update the existing one: increment `Task Iteration`, move previous task to `## Previous Task`, update `## Current Task`, reset `Edit Count Since Checkpoint` to 0. Do not change `Current State` — the daemon updates it. Then skip to step 5.

### 5. Classify Task Type

See routing table below.

---

## Routing

| Condition                                | Next Step                                |
| ---------------------------------------- | ---------------------------------------- |
| No features registered                   | `WF_ONBOARD`                             |
| Feature not found                        | `WF_ONBOARD`                             |
| Simple lookup ("find X", "show Y")       | `WF_RESEARCH`                            |
| WM not created/updated                   | Create it now, then re-evaluate          |
| Continue previous work                   | `WF_CONTINUE`                            |
| Research/question only                   | `WF_RESEARCH`                            |
| Code change / feature / bug              | `WF_CLASSIFY`                            |
| Operational task (test, run, verify)     | `WF_CLASSIFY`                            |
| New task after WF_DONE (same session)    | Update existing WM, then `WF_CLASSIFY`   |

**Lite mode:** `WF_RESEARCH_LITE` is only available when the user explicitly requests it.

Update WM via `/swe-wm-update` before transitioning.
