---
name: swe-feature-update
version: 1.1.0
description: Update a specific feature's memory files to reflect current codebase state
workflow:
  aware: true
  callable_from:
    - WF_CLASSIFY
    - WF_CONTINUE
  default_return: WF_CLASSIFY
  supports_standalone: true
  auto_transition: true
args:
  - name: key
    description: Feature key (REQUIRED - e.g., BLOCKS, THEME_DISTRICT)
    required: true
---

# /swe-update-feature [KEY]

Update a specific feature's memory files to accurately reflect current codebase state.

## Usage

```bash
/swe-update-feature BLOCKS           # Update BLOCKS feature memories
/swe-update-feature THEME_DISTRICT   # Update THEME_DISTRICT feature memories
/swe-update-feature TESTS            # Update TESTS feature memories
```

## Purpose

Synchronize feature documentation with actual codebase:

- Update directory listings and file inventories
- Refresh architecture layers and patterns
- Update entry points and key files
- Sync related memories (ARCH__, INDEX__, DOM_*)

---

## Stage 1: Validate Feature

**Verify feature exists:**

```javascript
mcp__plugin_swe_serena__read_memory("index/INDEX_FEATURES")
```

**Check:** Feature key exists in registered features table.

**If not found:**

```
> Feature [KEY] not registered. Use /swe-feature-onboard [KEY] to register it first.
```

Exit skill with `needs_clarification` status.

---

## Stage 2: Load Current Feature Memory

```javascript
mcp__plugin_swe_serena__read_memory("feature/FEATURE_[KEY]")
```

**Extract from current memory:**

- Root path(s)
- Primary language
- Framework
- Type
- Architecture layers
- Related memories list

---

## Stage 3: Analyze Current Codebase State

**For each root path in the feature:**

### 3.1 Directory Structure

```javascript
mcp__plugin_swe_serena__list_dir({ relative_path: "[root_path]", depth: 2 })
```

### 3.2 Key Files Inventory

```javascript
mcp__plugin_swe_serena__get_symbols_overview({ relative_path: "[root_path]" })
```

### 3.3 Pattern Detection

Use the Stage 3.1/3.2 output (`list_dir`, `get_symbols_overview`) plus targeted lookups:

- Entry points (main/index files): filenames matching `index.*`, `main.*`, or the entry point named in the feature memory's Key Files table.
- Configuration files: `mcp__plugin_swe_serena__search_for_pattern(substring_pattern="^\\[.*\\]|^{", relative_path="[root_path]")` or check the directory listing from 3.1 for known config filenames (`*.config.*`, `*.conf`, `*.yml`, `*.yaml`, `*.json`).
- Test files: filenames under the test root documented in `feature/FEATURE_TESTS`.
- Template files: filenames matching the framework's template convention (e.g. `*.tpl`, `*.blade.php`, `*.twig`) from the 3.1 directory listing.

---

## Stage 4: Compare and Identify Changes

**Compare current state vs. documented state:**

| Aspect       | Check For                               |
| ------------ | --------------------------------------- |
| Directories  | New directories, removed directories    |
| Key files    | New files, renamed files, removed files |
| Layers       | Layer changes, new components           |
| Dependencies | New internal/external dependencies      |
| Entry points | Changed entry points                    |

**Report changes found:**

```
Changes detected for [KEY]:
- [+] Added: [new items]
- [-] Removed: [removed items]
- [~] Modified: [changed items]
```

---

## Stage 5: Update Feature Memory

### Site-Data Rule (MANDATORY)

See `mem:ref/REF_NO_SITE_DATA`. Before any `write_memory`/`edit_memory` call in this stage, re-read every updated memory body against it. Replace real hostnames/IPs/IDs/org names/credentials with placeholders or generic role names. Report a sensitive-value finding to the user IN CHAT ONLY — NEVER write it into a memory section, to-do, or inventory. A `[site-data]` hook denial means a value slipped through — fix the draft, NEVER work around it.

### ⚠️ SPECIAL CASE: SWE Feature

When updating the **SWE** feature itself, memories follow a dual-location architecture:

1. **Edit FIRST** in the plugin folder: `$SWE_PLUGIN_ROOT/memories/`
2. **Then sync** to local project using `/swe-sync`

This ensures changes are preserved in the portable plugin and propagated correctly.

**DO NOT** edit SWE memories directly in `.serena/memory/` - they will be overwritten on sync.

### 5.1 Update FEATURE_[KEY]

`<updated content>` MUST carry the `obligations:` front-matter field (1-2 imperative lines, or `obligations: []`) per `mem:ref/REF_MEMORY_STYLE` "Obligations Field" — `swe_pre_memory_index_gate.py` denies a full-rewrite write without it; carry forward the existing field's value if present.

MUST refresh `paths:` when Stage 4 found directory or key-file changes — regenerate the glob list from the current Primary Directories / Key Files rather than carrying the stale value forward. Add the field when the feature governs source files and has none; drop a glob when its directory is absent from the current Stage 4 listing.

```javascript
mcp__plugin_swe_serena__write_memory("FEATURE_[KEY]", "<updated content>")
```

**Preserve:**

- Feature name and metadata
- Workflow context sections
- Related memories list

**Update:**

- Directory listings
- Key files table
- Architecture layers (if changed)
- Last updated timestamp

### 5.2 Update Related Memories (if needed)

For each memory below, `mcp__plugin_swe_serena__read_memory("<name>")`, compare against the Stage 4 change list (judgment), and `mcp__plugin_swe_serena__write_memory` / `edit_memory` only if Stage 4 found a significant change affecting that memory:

- `arch/ARCH_[KEY]` - Architecture documentation
- `index/INDEX_[KEY]_*` - File/symbol indexes
- `dom/DOM_[KEY]_*` - Domain documentation (rule-bearing: a full `write_memory` rewrite here MUST carry `obligations:` per `mem:ref/REF_MEMORY_STYLE`)

**Only update if significant changes detected.**

---

## Stage 6: Symbol Index (Related Docs)

**After updating FEATURE_[KEY] and related memories, regenerate the Related Docs table.**

Invoke the `/swe-symbol-index` skill:

```
/swe-symbol-index [KEY]
```

This will:

1. Read all linked memories listed in FEATURE_[KEY]'s Related Memories section
2. Extract heading symbols from each via `get_symbols_overview`
3. Build/replace the `## Related Docs` table after Feature Overview

**This ensures the symbol index stays in sync with any memory changes.**

---

## Stage 7: Summary Report

Output to user:

```markdown
## Feature Update Complete: [KEY]

### Changes Applied

- FEATURE_[KEY]: [summary of changes]
-

### Current State

| Property     | Value       |
| ------------ | ----------- |
| Root Path(s) | [paths]     |
| Key Files    | [count]     |
| Last Updated | [timestamp] |
```

---

## Skill Return

```markdown
## Skill Return

- **Skill**: swe-feature-update
- **Status**: success
- **Feature Key**: [KEY]
- **Memories Updated**: [list]
- **Changes Summary**: [brief description]
- **Next Step Hint**: WF_CLASSIFY
```

---

## Exit

```
> **Skill /swe-feature-update complete** - Feature [KEY] memories updated
```

---

## Troubleshooting

### Feature not found

```
Feature [KEY] is not registered in INDEX_FEATURES.
Run: /swe-feature-onboard [KEY]
```

### Root path doesn't exist

- Check if paths have moved
- Update FEATURE_[KEY] with correct paths
- Suggest re-onboarding if structure changed significantly

### No changes detected

```
> Feature [KEY] is up to date. No changes needed.
```

Exit with `success` status (no changes to make is still success).
