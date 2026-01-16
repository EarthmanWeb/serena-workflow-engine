# WF_START - Entry Point

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

> **On step WF_START**

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

See `REF_WORKING_MEMORY` for format.

```
# First, try to find existing:
mcp__serena__list_memories()  # Look for WORKING_MEMORY_* files

# If continuing work, read existing file
# If new conversation, CREATE NOW:
mcp__serena__write_memory("WORKING_MEMORY_<timestamp>_<descriptor>", "<content>")
```

**Required WORKING_MEMORY content:**
```markdown
# WORKING_MEMORY - [Date] [Descriptor]

## Session Context
- **Task**: [Brief description from user]
- **Feature(s)**: [Feature key(s) from INDEX_FEATURES - comma-separated if multiple]
- **Status**: Starting
- **Session ID**: [Timestamp from filename, e.g., 20260109_145230]

## Affected Features (if multi-feature)
- **Primary**: [KEY1] - [reason this is primary]
- **Secondary**: [KEY2] - [reason for involvement]
- **Related**: [KEY3] - [reason for involvement]

## Progress Tracking
- ⏳ [First task item]

## Workflow Context
- **Calling Step**: WF_START
- **Feature Key(s)**: [Feature key(s) from INDEX_FEATURES]
- **Session ID**: [Same as above]
- **Return Step**: [To be set by WF_CLASSIFY]
- **Invocation Mode**: workflow

## Last Updated
[Timestamp]
```

**Note:** The `## Affected Features` section is optional for single-feature tasks but REQUIRED for multi-feature requests.

**Note:** The `## Workflow Context` section enables workflow-aware skills to detect they are running within a workflow and return to the correct step. See `REF_SKILL_PROTOCOLS` for details.

**Echo filename to chat**: `Working Memory: WORKING_MEMORY_<timestamp>_<descriptor>`
**Store the current feature key in WORKING_MEMORY** for reference during conversation

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
