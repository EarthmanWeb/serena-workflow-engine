# WF_LOAD_FEATURE - Load Feature Context & Validate Requirements

> **📂 On step WF_LOAD_FEATURE**

⬆️ OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## 🛑 BLOCKING: Feature Loading Is MANDATORY

**You CANNOT proceed to WF_EXECUTE without loading feature memories.**

This step exists because feature memories contain:

- Architecture patterns specific to the feature
- File locations and directory structure
- Testing requirements and commands
- Coding standards and patterns
- Domain-specific context

**Skipping this step = writing code without understanding where it goes or how it should be structured.**

---

## Execute These Steps

### 1. Read Feature Index

```
mcp__plugin_swe_serena__read_memory("index/INDEX_FEATURES")
```

Identify which feature key(s) match your WM's `Feature Key(s)` field.

### 2. 🛑 MANDATORY: Load Primary Feature Memory

**For EACH feature key in your WM, you MUST read its FEATURE_[KEY] memory:**

```
# Single feature:
mcp__plugin_swe_serena__read_memory("feature/FEATURE_[KEY]")

# Multiple features:
mcp__plugin_swe_serena__read_memory("feature/FEATURE_[KEY1]")
mcp__plugin_swe_serena__read_memory("feature/FEATURE_[KEY2]")
```

**⛔ DO NOT PROCEED without reading ALL feature memories for your task.**

### 3. Load Supporting Memories From FEATURE_[KEY]

Each FEATURE_[KEY] memory lists related memories. Read those that are relevant:

| Memory Type    | When to Read                               |
| -------------- | ------------------------------------------ |
| `DOM_[DOMAIN]` | Always - contains domain-specific patterns |
| `SYS_[SYSTEM]` | For system/infrastructure work             |
| `REF_[TOPIC]`  | For coding standards and patterns          |
| `INDEX_[TYPE]` | For locating specific files/classes        |
| `ARCH_[AREA]`  | For multi-layer architecture work          |

```
# Example - read whatever is listed in your FEATURE_[KEY]:
mcp__plugin_swe_serena__read_memory("dom/DOM_[DOMAIN]")
mcp__plugin_swe_serena__read_memory("feature/FEATURE_DEV_STANDARDS")
```

### 4. Validate Requirements Against Domain Memories

**If WF_CLASSIFY detected requirements** (noted in WM), compare them to loaded domain memories:

1. **Check for existing domain memory:**
   Look for `DOM_*` memories that relate to the detected requirements.

2. **Compare requirement to domain knowledge:**
   - **NEW requirement**: Note it — will be added to domain memory after implementation
   - **CONFLICTING requirement**: Route to `WF_CLARIFY` — ask user before overriding existing domain rules
   - **EXISTING requirement**: Acknowledge — the domain already documents this behavior

3. **If no requirements were detected at WF_CLASSIFY**: Skip this step — pure implementation task.

### 5. Note Key Information for Implementation

From the feature memory, record in your understanding:

- Key file paths and directories
- Important class/function names for Serena lookups
- Testing commands
- Architecture patterns to follow

---

## Verification Checklist

Before proceeding, confirm:

- [ ] Read INDEX_FEATURES
- [ ] Read FEATURE_[KEY] for EACH feature in WM
- [ ] Read relevant DOM__, SYS__, REF_* memories
- [ ] Understand file locations and patterns
- [ ] Requirements validated against domain memories (or "none detected")

**If any checkbox is unchecked, DO NOT PROCEED.**

---

## ⛔ MANDATORY NEXT STEP — Route By Task Type

**YOU ARE NOT FINISHED.** After loading features, route based on what the task actually does:

| Task Type                   | Examples                                                                                       | MUST Read Next   |
| --------------------------- | ---------------------------------------------------------------------------------------------- | ---------------- |
| **Code changes**            | Bug fix, new feature, refactor, config change in code                                          | `WF_ARCH_REVIEW` |
| **Operational**             | Send test request, run CLI command, check config, verify endpoint, test webhook, run migration | `WF_EXECUTE`     |
| **Conflicting requirement** | Requirement conflicts with existing domain rule                                                | `WF_CLARIFY`     |

### Code Changes → Architecture Review

1. Read `WF_ARCH_REVIEW` (which handles design, compliance, swarm assessment, and approval)
2. On approval → `WF_EXECUTE`

### Operational Tasks → Direct Execute

Operational tasks **do not modify source code**. They use feature context (URLs, config keys, data formats) to perform actions like:

- Sending test HTTP requests to endpoints
- Running WP-CLI commands
- Checking database state
- Verifying webhook responses
- Running existing test suites

These skip architecture review because there is no architecture to review — no files are being changed.

**SKIPPING FEATURE LOADING IS STILL A VIOLATION** — operational tasks need feature context to know endpoints, config keys, data formats, etc.

📋 **WM:** The hook daemon auto-updates `Current State` when you read the next WF_* step. You do NOT need to manually update `Current State`.

## ⚠️ MANDATORY: WM UPDATE

**Before transitioning, invoke `/swe-wm-update --from WF_LOAD_FEATURE`** — provides
the step-specific checklist ensuring no fields are missed. Do NOT manually update WM
without it.

**SKIPPING WM UPDATE = WORKFLOW VIOLATION**

[CRITICAL: Did you load ALL FEATURE_[KEY] memories? Did you route correctly based on task type?]
