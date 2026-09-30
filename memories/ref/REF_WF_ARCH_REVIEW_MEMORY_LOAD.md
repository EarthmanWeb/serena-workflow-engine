---
name: WF_ARCH_REVIEW Feature/Layer/Standards Memory Load
description: Steps 1-2c — gap-fill feature architecture, layer docs, DEV_* standards, and compliance-checklist derivation. Skipped entirely by the SPEC Fast-Path.
metadata:
  type: reference
obligations:
  - Skip memories already loaded by the WF_CLASSIFY Step 4d sweep — check WM `Memories loaded` before re-reading.
---

# WF_ARCH_REVIEW — Steps 1-2c: Memory Load & Compliance Checklist Derivation

Run only when no `SPEC_*` memory is loaded (SPEC Fast-Path skips this).

## 1. Get Feature Architecture

Gap-fill ONLY what the Step 4d sweep missed:

```
mcp__plugin_swe_serena__read_memory("index/INDEX_FEATURES")   # active feature
mcp__plugin_swe_serena__read_memory("feature/FEATURE_[KEY]")  # feature config with layers
mcp__plugin_swe_serena__read_memory("arch/ARCH_SWE")           # architecture overview (if exists)
```

## 2. Read Layer Documentation

For each layer in the design, read its rules — skip memories already read in the Step 4d sweep:

```
mcp__plugin_swe_serena__read_memory("sys/SYS_[SYSTEM]")   # system docs (feature-specific)
mcp__plugin_swe_serena__read_memory("ref/REF_[TOPIC]")    # reference patterns (codebase-shared)
mcp__plugin_swe_serena__read_memory("dom/DOM_[DOMAIN]")   # domain context (feature-specific)
```

## 2b. Load Development Standards

Read `feature/FEATURE_DEV_STANDARDS` (index of all `DEV_*`), then read each standard for the languages/layers this task touches:

| Task involves...        | Read                 |
| ----------------------- | -------------------- |
| PHP classes/functions   | `dev/DEV_PHP`        |
| JavaScript/jQuery       | `dev/DEV_JAVASCRIPT` |
| SCSS/CSS                | `dev/DEV_SCSS`       |
| Blade/templates         | `dev/DEV_BLADEONE`   |
| Tests                   | `dev/DEV_TESTS`      |
| Cross-language patterns | `dev/DEV_PATTERNS`   |

If a `DEV_*` memory does not exist for a language, skip it and note the gap.

## 2c. Derive Project Compliance Checklist

- Extract concrete rules applicable to this task from the loaded `DEV_*`, `DOM_*`, `SYS_*`, `FEATURE_[KEY]` memories.
- Write as a checklist in WM under `## Compliance Checklist` — one item per rule (naming conventions, boilerplate, security patterns, registration contracts, integration points, required interfaces, testing commands, file patterns).
- Verified at `WF_VERIFY`.

Example (format + specificity to match):

```markdown
## Compliance Checklist

- [ ] PHP file header with @package and @since (DEV_PHP)
- [ ] Handler implements getFieldHTML + initField (DOM_BUILDER_FIELDS)
- [ ] Blade template has variable defaults block at top (DEV_BLADEONE)
- [ ] filemtime() for asset versioning, not hardcoded (DEV_PHP)
- [ ] Handler registered via registerComponentHandler (DOM_BUILDER_FIELDS)
- [ ] New JS/CSS enqueued in builder-assets.php (FEATURE_builder)
- [ ] Nonce verification in any AJAX handler (DEV_PHP)
```
