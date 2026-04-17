---
name: swe-symbol-index
version: 1.0.0
description: Generate a tabular symbol index of all linked docs for a feature, inserted into the FEATURE_[KEY] memory
workflow:
  aware: true
  callable_from:
    - WF_START
    - WF_CLASSIFY
    - WF_EXECUTE
    - WF_CONTINUE
  default_return: WF_START
  supports_standalone: true
  auto_transition: true
args:
  - name: key
    description: Feature key (REQUIRED - e.g., CALENDAR, BLOCKS, THEME_DISTRICT)
    required: true
---

## Workflow Initialization

**If starting a new session**, first read workflow initialization:

```
mcp__plugin_swe_serena__read_memory("wf/WF_INIT")
```

Follow WF_INIT instructions before executing this skill.

---

# /swe-symbol-index [KEY]

Generate a tabular view of all symbols found in a feature's linked documentation memories, and insert it into the feature's main `FEATURE_[KEY]` memory as a "Related Docs" section after "Feature Overview".

## Usage

```bash
/swe-symbol-index CALENDAR        # Index all CALENDAR linked docs
/swe-symbol-index BLOCKS           # Index all BLOCKS linked docs
/swe-symbol-index THEME_DISTRICT   # Index all THEME_DISTRICT linked docs
```

## Purpose

- Provide a quick-reference symbol map for feature documentation
- Link each heading/symbol back to its source memory file
- Make feature navigation faster by surfacing structure of related docs

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

## Stage 2: Load Feature Memory

```javascript
mcp__plugin_swe_serena__read_memory("feature/FEATURE_[KEY]")
```

**Extract the "Related Memories" section** (typically a table at the bottom of the feature memory). This contains the list of linked doc names (e.g., `DOM_CALENDAR_DISTRICT`, `SYS_CALENDAR_ICS`).

**Build linked docs list** from:

1. The `Related Memories` table in FEATURE_[KEY] (Memory column values)
2. The `Quick Lookup` row for this KEY in INDEX_FEATURES (INDEX Memory column)

Deduplicate the combined list. These are all the memory files to index.

---

## Stage 3: Extract Symbols From Each Linked Doc

**For each linked memory file**, use Serena's symbolic tools with `depth=1` to capture nested headings:

```javascript
mcp__plugin_swe_serena__get_symbols_overview({
  relative_path: ".serena/swe/[memory_subdir]/[MEMORY_NAME].md",
  depth: 1
})
```

### Depth Parameter Reference

| depth | Returns |
|-------|---------|
| `0` (default) | Top-level symbols only |
| `1` | Top-level + immediate children (recommended for indexes) |
| `2+` | Deeper nesting — rarely needed for memory docs |

**Memory subdirectory mapping:**

| Prefix     | Subdirectory |
| ---------- | ------------ |
| `DOM_`     | `dom/`       |
| `SYS_`     | `sys/`       |
| `REF_`     | `ref/`       |
| `ARCH_`    | `arch/`      |
| `INDEX_`   | `index/`     |
| `SPEC_`    | `spec/`      |
| `MAP_`     | `map/`       |
| `FEATURE_` | `feature/`   |
| `WF_`      | `wf/`        |

**If `get_symbols_overview` fails** for a memory (file not in .serena/swe/), try the plugin path:

```javascript
mcp__plugin_swe_serena__get_symbols_overview({
  relative_path: "$SWE_PLUGIN_ROOT/memories/[subdir]/[MEMORY_NAME].md"
})
```

**Collect from each file:**

- All heading symbols (H2 `##` and H3 `###` level)
- Symbol name (the heading text)
- Symbol depth/level

---

## Stage 4: Build the Related Docs Table

**Construct a markdown table** with the following format:

```markdown
## Related Docs

| Memory                                         | Key Sections                                     | Description                         |
| ---------------------------------------------- | ------------------------------------------------ | ----------------------------------- |
| [DOM_CALENDAR_DISTRICT](DOM_CALENDAR_DISTRICT) | Board Meetings, School Year Dates, URL Routes    | District-specific calendar behavior |
| [SYS_CALENDAR_ICS](SYS_CALENDAR_ICS)           | ICS Feed Generation, Rewrite Rules, School Dates | ICS feed system documentation       |
| ...                                            | ...                                              | ...                                 |
```

**Rules for building the table:**

1. **Memory column:** Memory name as a markdown link `[NAME](NAME)` (Serena memory ref format)
2. **Key Sections column:** Comma-separated list of H2 heading symbols from that memory (max 5, pick most descriptive). Skip generic headings like "Overview", "Related Memories", "Execute These Steps".
3. **Description column:** Extract from INDEX_FEATURES or FEATURE_[KEY] Related Memories table description column. If not available, derive from the first H2 heading content.

---

## Stage 5: Insert Into Feature Memory

**Target location:** First section after `## Feature Overview` (or after the first table following the feature overview heading).

**Check if "## Related Docs" already exists** in FEATURE_[KEY]:

### If exists — Replace it:

```javascript
mcp__plugin_swe_serena__edit_memory("FEATURE_[KEY]", {
  needle: "## Related Docs\\n\\n\\|.*?(?=\\n## |\\Z)",
  repl: "<new Related Docs section>",
  mode: "regex"
})
```

### If does not exist — Insert it:

Find the insertion point: after `## Feature Overview` section's content (after the metadata table that follows it), before the next `##` heading.

```javascript
mcp__plugin_swe_serena__edit_memory("FEATURE_[KEY]", {
  needle: "<end of Feature Overview section content>",
  repl: "<end of Feature Overview section content>\n\n## Related Docs\n\n<table content>",
  mode: "literal"
})
```

**Use `edit_memory` with literal mode** when possible for precision. Use regex mode only when the exact text is uncertain.

---

## Stage 6: Summary Report

Output to user:

```markdown
## Symbol Index Complete: [KEY]

### Indexed Memories

| Memory | Symbols Found |
| ------ | ------------- |
| [name] | [count]       |
| ...    | ...           |

### Related Docs Table

[Show the generated table]

### Inserted Into

- `FEATURE_[KEY]` — after "Feature Overview" section
```

---

## Skill Return

```markdown
## Skill Return

- **Skill**: swe-symbol-index
- **Status**: success
- **Feature Key**: [KEY]
- **Memories Indexed**: [count]
- **Symbols Found**: [total count]
- **Next Step Hint**: WF_START
```

---

## Exit

```
> **Skill /swe-symbol-index complete** - Related Docs table inserted into FEATURE_[KEY]
```

---

## Troubleshooting

### Feature not found

```
Feature [KEY] is not registered in INDEX_FEATURES.
Run: /swe-feature-onboard [KEY]
```

### No Related Memories section

```
FEATURE_[KEY] has no Related Memories section. Cannot determine linked docs.
Consider running /swe-feature-update [KEY] first.
```

### Symbol extraction fails for a memory

- Memory may not exist in .serena/swe/ or plugin memories/
- Try `search_for_pattern` as fallback to find heading patterns: `^##`
- Log skipped memories in the summary report

### Symbol extraction returns empty for code files

Not all language servers expose symbols equally. Known limitations:

| File Type | Symbol Quality | Fallback |
|-----------|---------------|----------|
| **PHP** | Excellent | — |
| **Python/TS/JS** | Good | Named exports work; jQuery wrappers may be empty |
| **SCSS/CSS** | Poor | Use `search_for_pattern` with `^\\.classname` or `^\\$variable` |
| **Markdown** | Limited | Headings only (H2/H3) |
| **JSON/Config** | None | Use `Read` or `search_for_pattern` |

When indexing **code files** (not memory docs), use `depth=1` on `get_symbols_overview` and `find_symbol` to capture class methods and nested symbols. Fall back to `search_for_pattern` for SCSS/CSS assets.

### No symbols found

```
> No heading symbols found in any linked docs for [KEY]. Table not inserted.
```

Exit with `success` status (no symbols is a valid result).
