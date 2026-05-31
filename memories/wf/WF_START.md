# WF_START - Entry Point

---

## 🚫 ANTI-RATIONALIZATION - See WF_INIT

**If you did not read WF_INIT before this file, STOP and read it now.**

The anti-rationalization block is in WF_INIT. If you skipped WF_INIT to get here, you have already violated the workflow.

---

## ⛔ CRITICAL: NO DIRECT PATH TO WF_EXECUTE

**READ THIS CAREFULLY:**

There is **NO VALID PATH** from WF_START directly to WF_EXECUTE.

If you are thinking of going to WF_EXECUTE from here:

- ❌ **STOP. That path does not exist.**
- ❌ "The task is simple enough" - **NO. Simple tasks still go through WF_CLASSIFY.**
- ❌ "I already know what to do" - **NO. WF_CLASSIFY loads features. You need them.**
- ❌ "The WM has the feature key" - **Having the key ≠ loading the FEATURE_[KEY] memory.**

**Valid paths to WF_EXECUTE (ALL go through classification and feature loading first):**

1. **Code changes:** WF_START → WF_CLASSIFY → WF_ARCH_REVIEW → WF_EXECUTE
2. **Operational tasks:** WF_START → WF_CLASSIFY → WF_EXECUTE
3. **Large/swarm:** WF_START → WF_CLASSIFY → WF_ARCH_REVIEW → WF_SWARM_ORCHESTRATE → WF_EXECUTE

**If your next step is WF_EXECUTE, you have violated the workflow.**

---

## ⚡ SPAWNED AGENT BYPASS

**How to detect you are a spawned agent — ANY of these in your initial prompt:**

- `"You are a swarm agent"` or `"BYPASS WF_INIT"`
- `"You are the [role] agent"` (e.g., "You are the researcher agent")
- `"Do NOT follow CLAUDE.md workflow"`
- Agent role assignment from a coordinator with task-specific instructions
- No user conversation — just a task prompt from another agent

**IF you are a spawned agent (Claude Code `Agent` tool, `claude -p`, or Ruflo `agent_execute`):**

- ✅ **STOP HERE. Do NOT continue reading this file.**
- ✅ **SKIP ALL workflow steps** (WF_INIT, WF_START, WF_CLASSIFY, WF_ARCH_REVIEW, etc.)
- ✅ **Do NOT create WM files** (the coordinator handles this)
- ✅ **Do NOT read CLAUDE_OBLIGATIONS** (wastes your context)
- ✅ **Execute ONLY the task in your initial prompt**
- ✅ You MAY read Serena memories (`read_memory`) if they help your specific task
- ✅ You MAY use any tool (Read, Grep, Glob, Serena, etc.) immediately

**⛔ WARNING: If you are a spawned agent and you continue past this point, you will waste your entire context window on workflow initialization instead of your assigned task. This is the #1 cause of swarm agent failure.**

**IF you are NOT a swarm agent, ALWAYS continue below.**

---

> **🚀 On step WF_START**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## Execute These Steps

### 1. Check Feature Registry

```
mcp__plugin_swe_serena__read_memory("index/INDEX_FEATURES")
```

**If INDEX_FEATURES doesn't exist or has no registered features:**

- Go to `WF_ONBOARD` immediately
- Do not proceed with other steps

### 2. Identify Relevant Feature(s)

Determine which feature(s) this conversation is about:

1. **From user context** - Did user mention feature names, keys, or file paths?
2. **From file paths** - If files are mentioned, which feature(s) contain them?
3. **Cross-feature indicators** - Does request span multiple areas?
4. **Ask if unclear** - "Which feature(s) are you working on? [list from INDEX_FEATURES]"

**Record the feature key(s) in WM. Feature memories will be loaded in WF_CLASSIFY.**

**⚠️ FALLBACK: If a feature is NOT found in MEMORY.md or INDEX_FEATURES**, call `list_memories(topic="feature")` to discover feature memories that exist but are not yet indexed. MEMORY.md can fall out of sync — `list_memories()` is the authoritative source for what actually exists. If the feature memory exists but is missing from MEMORY.md, **add the index entry to MEMORY.md immediately** before proceeding.

If, after checking `list_memories()`, the FEATURE_[KEY] still doesn't exist → `WF_ONBOARD`

**📌 MEMORY.md Maintenance:** MEMORY.md MUST be kept up to date whenever new memories are created. Every `write_memory()` call MUST be followed by adding a corresponding one-line index entry to MEMORY.md. A memory without an index entry is invisible to future sessions that rely on MEMORY.md for discovery.

### 3. Read CLAUDE_OBLIGATIONS

```
mcp__plugin_swe_serena__read_memory("claude/CLAUDE_OBLIGATIONS")
```

### 4. ⚠️ MANDATORY: WM File

**THIS IS NOT OPTIONAL. YOU CANNOT PROCEED WITHOUT A WM FILE.**

---

#### ⚙️ HOW WM STATE UPDATES WORK

**The hook daemon manages `Current State` automatically.** When you read any `WF_*` memory, the `swe_post_read_state` hook:

1. Validates the transition against `states.json`
2. Updates `**Current State**:` in the WM file
3. Appends a transition log entry to the Progress section

**YOU MUST NOT manually rewrite the WM file just to update `Current State`.** The daemon does this. If you overwrite the WM with `write_memory`, you may clobber the daemon's format and cause the init gate to reject the file.

**What YOU own in WM:**

- `## Current Task` — task description, affected features
- `## Progress` — status updates on work done (but NOT `### Transitions`)
- `## Previous Task` — completed tasks

**What the DAEMON owns in WM:**

- `**Current State**:` — updated automatically on each WF_* read
- `**Previous State**:` — updated automatically
- `### Transitions` — appended automatically
- `**Edit Count Since Checkpoint**:` — incremented on each file edit
- `**Last Updated**:` — timestamp updated automatically

**If you need to update task context** (not state), invoke `/swe-wm-update` which provides step-specific checklists ensuring no fields are missed. Do NOT manually update WM with `edit_memory` or `write_memory`.

---

#### 🆕 WM Auto-Creation

**The WM file is auto-created** as `WM_{session}.md` when you first read `WF_START`. The hook creates it with the correct format including `## Workflow Context` and `**Current State**: WF_START`.

**DO NOT create your own WM file from scratch.** The auto-created file has the exact format the init gate expects (`**Current State**:` with double-asterisk bold markers inside `## Workflow Context`).

After auto-creation, update the task-specific sections by invoking:

```
/swe-wm-update --from WF_START
```

**DO NOT rename the WM file.** The `WM_{session}` name is permanent for the session. Renaming breaks state tracking.

---

#### 🔄 New Task After WF_DONE (Same Session)

**If you are arriving here from WF_DONE with a new task in the SAME session:**

1. **DO NOT create a new WM** - the existing one for this session is still valid
2. **UPDATE with SINGLE write_memory call** (preserve all daemon-managed fields):
   - Increment `Task Iteration`
   - Move previous task to `## Previous Task` section
   - Update `## Current Task` with new task
   - Reset `Edit Count Since Checkpoint` to 0
   - **DO NOT change `Current State`** — the daemon updates it when you read the next WF_* step
3. **Skip to step 5** (Classify Task Type) after updating

### 5. Classify Task Type

See routing table below.

## ⛔ MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** Before responding to user:

| Condition                                | MUST Read Next                                              |
| ---------------------------------------- | ----------------------------------------------------------- |
| No features registered                   | `WF_ONBOARD`                                                |
| Feature not found                        | `WF_ONBOARD`                                                |
| Simple lookup ("find X", "show Y")       | `WF_RESEARCH`                                               |
| WM not created/updated                   | **CREATE IT NOW**                                           |
| Continue previous work                   | `WF_CONTINUE`                                               |
| Research/question only                   | `WF_RESEARCH`                                               |
| **Code change/feature/bug**              | **`WF_CLASSIFY`** ← THIS IS MANDATORY                       |
| **Operational task (test, run, verify)** | **`WF_CLASSIFY`** ← STILL MANDATORY (needs feature context) |
| New task after WF_DONE (same session)    | **UPDATE existing WM** → `WF_CLASSIFY`                      |

**⚡ LITE MODE (User-Requested Only):** `WF_RESEARCH_LITE` is ONLY available when the user explicitly requests it.

---

## 🛑 BLOCKED PATHS - These Do NOT Exist

| Invalid Path               | Why It's Invalid                                     |
| -------------------------- | ---------------------------------------------------- |
| WF_START → WF_EXECUTE      | **Features not loaded. WF_CLASSIFY must run first.** |
| WF_START → WF_CHECKPOINT   | **No work has been done yet.**                       |
| WF_START → WF_VERIFY       | **Nothing to verify yet.**                           |

**If you find yourself wanting to go to any of these, STOP. Go to WF_CLASSIFY.**

---

1. Determine which condition applies
2. **VERIFY WM exists and is current**
3. Read that WF_* memory NOW
4. Report the new step to user

**PROCEEDING WITHOUT WM = WORKFLOW VIOLATION**
**SKIPPING WF_CLASSIFY FOR CODE CHANGES = WORKFLOW VIOLATION**
**GOING DIRECTLY TO WF_EXECUTE = WORKFLOW VIOLATION**

[CRITICAL: Does WM exist? Is your next step WF_CLASSIFY (for code changes) or WF_RESEARCH? Did you report on it?]
