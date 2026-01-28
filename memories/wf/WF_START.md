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

**Valid paths to WF_EXECUTE (ALL go through classification/planning first):**
1. WF_START → WF_CLASSIFY → WF_DETECT_REQ → WF_LOAD_FEATURE → WF_EXECUTE
2. WF_START → WF_CLASSIFY → WF_PLAN_ARCHITECTURE → WF_EXECUTE
3. WF_START → WF_CLASSIFY → WF_SWARM_ORCHESTRATE → WF_EXECUTE

**If your next step is WF_EXECUTE, you have violated the workflow.**

---

## ⚡ SWARM AGENT BYPASS

**How to know if you are a spawned agent:** Your prompt contains explicit agent role assignment (e.g., "You are the researcher agent") and task-specific instructions from a coordinator.

**IF you are an agent spawned as part of a swarm initiated from a workflow:**
- ✅ You MAY bypass this workflow entirely
- ✅ Adhere ONLY to the specific instructions provided by the initiating agent
- ✅ Read CLAUDE_FLOW, CLAUDE_OBLIGATIONS, _INDEX, and only read other memories if they assist with your specific task
- ❌ Do NOT create WM files (the coordinator handles this)

**IF you are NOT a swarm agent, ALWAYS continue below.**

---

> **🚀 On step WF_START**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## Execute These Steps

### 1. Check Feature Registry

```
mcp__plugin_swe_serena__read_memory("INDEX_FEATURES")
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

If any FEATURE_[KEY] doesn't exist → `WF_ONBOARD`

### 3. Read CLAUDE_OBLIGATIONS

```
mcp__plugin_swe_serena__read_memory("CLAUDE_OBLIGATIONS")
```

### 4. ⚠️ MANDATORY: Create/Read WM

**THIS IS NOT OPTIONAL. YOU CANNOT PROCEED WITHOUT A WM FILE.**

---

#### 🔄 New Task After WF_DONE (Same Session)

**If you are arriving here from WF_DONE with a new task in the SAME session:**

1. **DO NOT create a new WM** - the existing one for this session is still valid
2. **UPDATE with SINGLE write_memory call:**
   ```python
   # ⛔ DO NOT use multiple edit_memory calls - each triggers daemon!
   # ✅ Use ONE write_memory with complete updated content:
   mcp__plugin_swe_serena__write_memory("WM_{session}_{descriptor}", "<full content>")
   ```
   Include in the update:
   - Increment `Task Iteration` (e.g., 1 → 2)
   - Move previous task to `## Completed Tasks (This Session)` section
   - Add new task to `## Active Task`
   - Reset `Edit Count Since Checkpoint` to 0
   - Update `Current State` to `WF_CLASSIFY`
3. **Skip to step 5** (Classify Task Type) after updating

**How to detect this scenario:**
- WM file exists for current session ID
- Previous state was WF_DONE or WF_CLEANUP
- User has provided a new task/request

---

**🛑 BLOCKING REQUIREMENT: READ REF_WM FIRST**

```
mcp__plugin_swe_serena__read_memory("REF_WM")
```

**DO NOT create a WM file until you have read REF_WM.**
**DO NOT use any other template or format - ONLY the one in REF_WM.**
**DO NOT invent sections, formats, or naming conventions.**
**THERE IS NO INLINE TEMPLATE HERE - THE ONLY SOURCE OF TRUTH IS REF_WM.**

---

**After reading REF_WM:**

1. Get session ID from hook context (e.g., `Session: cccdb36a`) - this is an 8-char UUID, NOT a date
2. **Placeholder WM is auto-created** as `WM_{session}_session` when you transition to WF_START
3. Follow the EXACT template from REF_WM - no modifications
4. Echo to chat: `📋 Working Memory: WM_<SESSION_ID>_session`

**⚠️ NOTE: Proper WM naming happens in WF_CLASSIFY**

The placeholder `_session` suffix will be replaced with a meaningful task descriptor (e.g., `_auth_fix`, `_block_tests`) at the END of WF_CLASSIFY, before transitioning to the next state. This ensures the task is understood before naming.

```
# Check for existing:
mcp__plugin_swe_serena__list_memories()  # Look for WM_* files

# If continuing work, read existing file
```

**CREATING WM WITHOUT READING REF_WM = WORKFLOW VIOLATION**

### 5. Classify Task Type

See routing table below.

## ⛔ MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** Before responding to user:

| Condition | MUST Read Next |
|-----------|----------------|
| No features registered | `WF_ONBOARD` |
| Feature not found | `WF_ONBOARD` |
| Simple lookup ("find X", "show Y") | `WF_RESEARCH` |
| WM not created/updated | **CREATE IT NOW** |
| Continue previous work | `WF_CONTINUE` |
| Research/question only | `WF_RESEARCH` |
| **Code change/feature/bug** | **`WF_CLASSIFY`** ← THIS IS MANDATORY |
| New task after WF_DONE (same session) | **UPDATE existing WM** → `WF_CLASSIFY` |

**⚡ LITE MODE (User-Requested Only):** `WF_RESEARCH_LITE` is ONLY available when the user explicitly requests it.

---

## 🛑 BLOCKED PATHS - These Do NOT Exist

| Invalid Path | Why It's Invalid |
|--------------|------------------|
| WF_START → WF_EXECUTE | **Features not loaded. WF_CLASSIFY must run first.** |
| WF_START → WF_LOAD_FEATURE | **Classification must happen first.** |
| WF_START → WF_CHECKPOINT | **No work has been done yet.** |
| WF_START → WF_VERIFY | **Nothing to verify yet.** |

**If you find yourself wanting to go to any of these, STOP. Go to WF_CLASSIFY.**

---

1. Determine which condition applies
2. **VERIFY WM exists and is current**
3. Read that WF_* memory NOW
4. Report the new step to user

**PROCEEDING WITHOUT WM = WORKFLOW VIOLATION**
**SKIPPING WF_CLASSIFY FOR CODE CHANGES = WORKFLOW VIOLATION**
**GOING DIRECTLY TO WF_EXECUTE = WORKFLOW VIOLATION**

[CRITICAL: Does WM exist? Is your next step WF_CLASSIFY (for code changes)? Did you report on it?]
