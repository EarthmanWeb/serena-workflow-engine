# SPEC_MEMORY_INDEX_FORMAT - Restructure Memory Indexes to Claude System Format

## Problem

Serena's current memory index format (`FEATURE_DEV_STANDARDS`, `INDEX_FEATURES`, etc.) uses markdown tables with columns like `Memory | Status | Description`. This format:

1. **Is verbose** — each entry takes a full table row with pipe delimiters, alignment, and redundant "✅ Active" status columns
2. **Doesn't self-describe** — individual memory files have no frontmatter metadata; their purpose is only documented in the index table
3. **Requires manual sync** — if a memory's purpose changes, you must update both the file content AND the index table description
4. **Isn't scannable** — table format forces equal visual weight on every column, burying the one thing that matters: what does this memory help with?
5. **Doesn't support relevance filtering** — the index has no structured metadata an agent could use to decide whether to load a memory without reading it

Claude's auto-memory system uses a different pattern that solves all of these:

- **Individual files have frontmatter** (`name`, `description`, `type`) that makes each file self-describing
- **The index (MEMORY.md) is a flat list** of one-line pointers: `- [Title](file.md) — one-line hook`
- **The description field is specifically designed** for relevance filtering ("used to decide relevance in future conversations")

## Proposed Format

### Individual Memory Files: Add Frontmatter

Every memory file (DEV_*, DOM_*, SYS_*, REF_*, ARCH_*, FEATURE_*, SPEC_*) gets a YAML frontmatter block:

```markdown
---
name: DEV_PHP
description: PHP file structure, class patterns, security (nonce/sanitize/escape), AJAX handlers, hooks, formatting rules
type: dev-standard
scope: codebase
languages: [php]
layers: [business-logic, data-access, infrastructure]
---

# DEV_PHP - PHP Development Standards
...
```

**Fields:**

| Field         | Purpose                                                                 | Required |
| ------------- | ----------------------------------------------------------------------- | -------- |
| `name`        | Memory identifier (matches filename without extension)                  | Yes      |
| `description` | One-line relevance hook — what does this help with? Be specific.        | Yes      |
| `type`        | Category: `dev-standard`, `domain`, `system`, `reference`, `architecture`, `feature`, `index` | Yes |
| `scope`       | `codebase` (shared) or `feature` (feature-specific)                     | Yes      |
| `languages`   | Languages this applies to (for DEV_* and DOM_*)                         | No       |
| `layers`      | Architecture layers this applies to (from ARCH_INDEX)                   | No       |
| `features`    | Feature keys this relates to (for feature-specific memories)            | No       |

### Index Files: Flat One-Line Pointers

Replace table-based indexes with flat scannable lists grouped by category:

```markdown
# FEATURE_DEV_STANDARDS - Development Standards Index

## Workflow & Style
- [DEV_WORKFLOW](../dev/DEV_WORKFLOW) — local dev workflow, review gates, commit format
- [DEV_WORKING_STYLE](../dev/DEV_WORKING_STYLE) — quality standards, KISS/YAGNI/DRY priority, parallel processing

## Language Standards
- [DEV_PHP](../dev/DEV_PHP) — PHP file structure, classes, security, AJAX, hooks, formatting
- [DEV_JAVASCRIPT](../dev/DEV_JAVASCRIPT) — JS/jQuery modules, events, AJAX, linting (Biome/ESLint)
- [DEV_SCSS](../dev/DEV_SCSS) — SCSS/CSS, Bootstrap 5.3, variables, build pipeline, stylelint
- [DEV_BLADEONE](../dev/DEV_BLADEONE) — BladeOne templates, escaping, includes, data passing
- [DEV_PYTHON](../dev/DEV_PYTHON) — Python (SWE hooks only), type hints, atomic I/O
- [DEV_TYPESCRIPT](../dev/DEV_TYPESCRIPT) — TypeScript (Playwright tests only), ESM imports

## Testing & Build
- [DEV_TESTS](../dev/DEV_TESTS) — Playwright E2E, data-id selectors, content-first validation
- [DEV_BUILD](../dev/DEV_BUILD) — pnpm workspace, esbuild, SCSS pipeline, Docker
- [DEV_PATTERNS](../dev/DEV_PATTERNS) — cross-language patterns: coordinator, singleton, hooks, events, REST

## References
- [REF_DEV_STANDARDS_ONBOARD](../ref/REF_DEV_STANDARDS_ONBOARD) — onboarding instructions for dev standards
- [REF_MCP_BROWSER](../ref/REF_MCP_BROWSER) — Browser MCP reference (Playwright/DevTools)
- [REF_XSS_CSRF](../ref/REF_XSS_CSRF) — security patterns: XSS/CSRF prevention
```

**Rules:**
- Each entry is one line, under ~120 characters after the link
- The hook after `—` matches the `description` field in the file's frontmatter
- No status columns (if a memory exists, it's active; if removed, it's gone)
- Group by semantic category, not alphabetically
- The full "Key Rules Summary" section in FEATURE_DEV_STANDARDS stays — it's a quick-reference, not an index concern

### INDEX_FEATURES: Same Treatment

The feature registry table becomes:

```markdown
## Registered Features

### Theme Features
- [FEATURE_builder](feature/FEATURE_builder) — Atlas page builder: sections, fields, content model, toolbar, layouts
- [FEATURE_builder_fields](feature/FEATURE_builder_fields) — field handler system: registration, interfaces, data flow
- [FEATURE_forms](feature/FEATURE_forms) — form system: CPT, submission pipeline, validation, email, field types
- [FEATURE_forms_notifications](feature/FEATURE_forms_notifications) — form notification system: email templates, notification UI
- [FEATURE_blocks](feature/FEATURE_blocks) — Atlas theme blocks: categories, JSON configs, Blade templates
- [FEATURE_bootstrap](feature/FEATURE_bootstrap) — Bootstrap 5.3 integration: SCSS, JS, PHP

### Plugin Features
- [FEATURE_icold](feature/FEATURE_icold) — ICO Logo Designer: REST API, artifact generation, team management

### Infrastructure
- [FEATURE_swe](feature/FEATURE_swe) — Serena Workflow Engine: state machine, hooks, memories
- [FEATURE_devcontainer](feature/FEATURE_devcontainer) — BroadSword DevContainer: Docker, scripts, VS Code
- [FEATURE_tests](feature/FEATURE_tests) — Playwright E2E test suites: builder + logo designer
```

The detailed metadata table (Root Path, Language/Framework) moves into each FEATURE_[KEY]'s own frontmatter:

```yaml
---
name: FEATURE_forms
description: Form system — CPT, submission pipeline, validation, email, 14 field types
type: feature
scope: feature
root_path: content/themes/atlas/builder/
languages: [php, javascript]
framework: WordPress with Blade templating
---
```

## Migration Plan

### Phase 1: Add Frontmatter to All Memory Files

For each memory file type:

1. Read existing file
2. Generate frontmatter from the file's content (name from filename, description from first section, type from prefix)
3. Prepend frontmatter block
4. Verify the file's `# Title` line still follows frontmatter

**Scope:** All files in `memories/` directories: `dev/`, `dom/`, `sys/`, `ref/`, `arch/`, `feature/`, `index/`

**Automation:** A script can generate frontmatter from existing content:
- `name` = filename without `.md`
- `description` = first sentence of the Overview or first table's Description column
- `type` = mapped from prefix (DEV_ → dev-standard, DOM_ → domain, etc.)
- `scope` = `codebase` for REF_/DEV_, `feature` for DOM_/SYS_/INDEX_/ARCH_

### Phase 2: Convert Index Files to Flat Format

1. `FEATURE_DEV_STANDARDS` — convert tables to one-line pointers (preserve Key Rules Summary)
2. `INDEX_FEATURES` — convert feature registry table to grouped one-line pointers (preserve metadata in FEATURE_[KEY] frontmatter)
3. `MEMORY.md` — already close to flat format, minor cleanup
4. Any other index-style files

### Phase 3: Update Workflow References

1. WF_CLASSIFY Step 4d now says "read the Related Memories table in FEATURE_[KEY]" — verify this works with new flat format
2. WF_ARCH_REVIEW Step 2b lookup table (`DEV_PHP`, `DEV_JAVASCRIPT`, etc.) — no change needed, already uses direct memory names
3. Onboarding tooling (`/swe-feature-onboard`) — update to generate frontmatter in new files

### Phase 4: Update Templates

1. `templates/FEATURE_DEV_STANDARDS.md` — update to show new flat index format
2. FEATURE_[KEY] template in INDEX_FEATURES — update to include frontmatter
3. Any onboarding scripts that generate memory files

## Benefits

1. **Self-describing files** — frontmatter tells you what a file is for without reading the index
2. **Scannable indexes** — one-line pointers are faster to scan than tables
3. **Relevance filtering** — `description`, `languages`, `layers` fields let agents decide what to load without reading the full file
4. **Less maintenance** — no status columns to keep in sync, no duplicate descriptions
5. **Consistent with Claude's own patterns** — agents already understand this format from the auto-memory system
6. **Future: programmatic filtering** — frontmatter enables scripts/hooks to filter memories by type, scope, language, or layer

## What This Does NOT Change

- Memory file naming conventions (DEV_*, DOM_*, SYS_*, etc.)
- Memory content structure (headings, sections, tables within files)
- Workflow state machine or transitions
- The separation of concerns between memory types
- How `read_memory()` calls work (still by name)

## Risks

- **Migration effort** — touching every memory file across all projects using SWE
- **Frontmatter parsing** — Serena's `read_memory` returns raw content; frontmatter is informational, not programmatically filtered (yet)
- **Onboarding scripts** — any automation that generates memories needs updating

## Open Questions

1. Should frontmatter be enforced by a hook (reject memory writes without frontmatter)?
2. Should `list_memories` be enhanced to return frontmatter fields for filtering?
3. Should the `languages` and `layers` fields be standardized enums or free-text?
