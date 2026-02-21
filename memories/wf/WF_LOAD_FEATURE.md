# WF_LOAD_FEATURE - Load Feature Context

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
mcp__plugin_swe_serena__read_memory("INDEX_FEATURES")
```

Identify which feature key(s) match your WM's `Feature Key(s)` field.

### 2. 🛑 MANDATORY: Load Primary Feature Memory

**For EACH feature key in your WM, you MUST read its FEATURE_[KEY] memory:**

```
# Single feature:
mcp__plugin_swe_serena__read_memory("FEATURE_[KEY]")

# Multiple features:
mcp__plugin_swe_serena__read_memory("FEATURE_[KEY1]")
mcp__plugin_swe_serena__read_memory("FEATURE_[KEY2]")
mcp__plugin_swe_serena__read_memory("FEATURE_[KEY3]")
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
mcp__plugin_swe_serena__read_memory("DOM_[DOMAIN]")
mcp__plugin_swe_serena__read_memory("REF_DEV_STANDARDS")
```

### 4. Note Key Information for Implementation

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

**If any checkbox is unchecked, DO NOT PROCEED.**

---

## ⛔ MANDATORY NEXT STEP — Route By Task Type

**YOU ARE NOT FINISHED.** After loading features, route based on what the task actually does:

| Task Type        | Examples                                                                                       | MUST Read Next   |
| ---------------- | ---------------------------------------------------------------------------------------------- | ---------------- |
| **Code changes** | Bug fix, new feature, refactor, config change in code                                          | `WF_ARCH_REVIEW` |
| **Operational**  | Send test request, run CLI command, check config, verify endpoint, test webhook, run migration | `WF_EXECUTE`     |

### Code Changes → Architecture Review

1. Invoke `/arch-review` skill (or read `WF_ARCH_REVIEW` directly)
2. The skill verifies approach against architecture patterns
3. On approval → `WF_EXECUTE`

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

[CRITICAL: Did you load ALL FEATURE_[KEY] memories? Did you route correctly based on task type?]
