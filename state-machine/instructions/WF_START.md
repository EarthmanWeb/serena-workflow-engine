# WF_START - Entry Point

---

## 🚫 ANTI-RATIONALIZATION - See WF_INIT

**If you did not read WF_INIT before this file, STOP and read it now.**

The anti-rationalization block is in WF_INIT. If you skipped WF_INIT to get here, you have already violated the workflow.

---

## ⚡ SWARM AGENT BYPASS

**How to know if you are a spawned agent:** Your prompt contains explicit agent role assignment (e.g., "You are the researcher agent") and task-specific instructions from a coordinator.

**IF you are an agent spawned as part of a swarm initiated from a workflow:**
- ✅ You MAY bypass this workflow entirely
- ✅ Adhere ONLY to the specific instructions provided by the initiating agent
- ✅ Read CLAUDE_FLOW, CLAUDE_OBLIGATIONS, _INDEX, and only read other memories if they assist with your specific task
- ❌ Do NOT create WORKING_MEMORY files (the coordinator handles this)

**IF you are NOT a swarm agent, ALWAYS continue below.**

---

> **🚀 On step WF_START**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## Execute These Steps

### 1. Check Feature Registry

```
mcp__serena__read_memory("INDEX_FEATURES")
```

**If INDEX_FEATURES doesn't exist or has no registered features:**
- Go to `WF_ONBOARD` immediately
- Do not proceed with other steps

### 2. Identify Relevant Feature(s)

Determine which feature(s) this conversation is about:

1. **From user context** - Did user mention feature names, keys, or file paths?
2. **From file paths** - If files are mentioned, which feature(s) contain them?
3. **Cross-feature indicators** - Does request span multiple areas? (e.g., "blocks and templates", "context providers for themes")
4. **Ask if unclear** - "Which feature(s) are you working on? [list from INDEX_FEATURES]"

**For single feature:**
```
mcp__serena__read_memory("FEATURE_[KEY]")  # Replace [KEY] with detected feature key
```

**For multiple features:**
```
# Load ALL relevant feature memories
mcp__serena__read_memory("FEATURE_[KEY1]")
mcp__serena__read_memory("FEATURE_[KEY2]")
# ... continue for each detected feature
```

If any FEATURE_[KEY] doesn't exist -> `WF_ONBOARD`

**Note:** Multi-feature requests are further analyzed in WF_CLASSIFY step 3.

### 3. Read CLAUDE_OBLIGATIONS

```
mcp__serena__read_memory("CLAUDE_OBLIGATIONS")
```

### 4. ⚠️ MANDATORY: Create/Read WORKING_MEMORY

**THIS IS NOT OPTIONAL. YOU CANNOT PROCEED WITHOUT A WORKING_MEMORY FILE.**

---

**🛑 BLOCKING REQUIREMENT: READ REF_WORKING_MEMORY FIRST**

```
mcp__serena__read_memory("REF_WORKING_MEMORY")
```

**DO NOT create a WORKING_MEMORY file until you have read REF_WORKING_MEMORY.**
**DO NOT use any other template or format - ONLY the one in REF_WORKING_MEMORY.**
**DO NOT invent sections, formats, or naming conventions.**
**THERE IS NO INLINE TEMPLATE HERE - THE ONLY SOURCE OF TRUTH IS REF_WORKING_MEMORY.**

---

**After reading REF_WORKING_MEMORY:**

1. Get session ID from hook context (e.g., `Session: cccdb36a`) - this is an 8-char UUID, NOT a date
2. Use naming: `WORKING_MEMORY_<SESSION_ID>_<descriptor>` 
3. Follow the EXACT template from REF_WORKING_MEMORY - no modifications
4. Echo to chat: `📋 Working Memory: WORKING_MEMORY_<SESSION_ID>_<descriptor>`

```
# Check for existing:
mcp__serena__list_memories()  # Look for WORKING_MEMORY_* files

# If continuing work, read existing file
# If new conversation, CREATE using REF_WORKING_MEMORY template ONLY
```

**CREATING WORKING_MEMORY WITHOUT READING REF_WORKING_MEMORY = WORKFLOW VIOLATION**

### 5. Classify Task Type

See routing table below.

## MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** Before responding to user:

| Condition | MUST Read Next |
|-----------|----------------|
| No features registered | `WF_ONBOARD` |
| Feature not found | `WF_ONBOARD` |
| WORKING_MEMORY not created/updated | **CREATE IT NOW** |
| Continue previous work | `WF_CONTINUE` |
| Research/question only | `WF_RESEARCH` |
| Code change/feature/bug | `WF_CLASSIFY` |

1. Determine which condition applies
2. **VERIFY WORKING_MEMORY exists and is current**
3. Read that WF_* memory NOW
4. Report the new step to user

**PROCEEDING WITHOUT WORKING_MEMORY = WORKFLOW VIOLATION**
**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Does WORKING_MEMORY exist? Are you on a WF_* workflow step? Did you report on it?]
