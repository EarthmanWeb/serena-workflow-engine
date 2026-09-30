---
name: swe-workflow-research
version: 1.0.0
description: Code exploration and research without making changes
workflow:
  aware: true
  callable_from:
    - WF_CLASSIFY
    - WF_CONTINUE
  default_return: WF_CLASSIFY
  supports_standalone: true
  auto_transition: true
---

## ⚠️ WORKFLOW INITIALIZATION

**If starting a new session**, first read workflow initialization:

```
mcp__plugin_swe_serena__read_memory("wf/WF_INIT")
```

Follow WF_INIT instructions before executing this skill.

---

# Workflow Research Skill

Explore and analyze codebase without making any changes.

## Purpose

- Understand code structure and patterns
- Find relevant files and functions
- Analyze dependencies and relationships
- Document findings for later use

## Actions

1. **Explore codebase structure**: `mcp__plugin_swe_serena__get_symbols_overview(relative_path="<dir>")`, `mcp__plugin_swe_serena__find_symbol(name_path_pattern="<name>")`.
2. **Search for patterns**: `mcp__plugin_swe_serena__search_for_pattern(substring_pattern="<pattern>", relative_path="<scope>")`, or `Grep`/`Glob` when Serena symbolic search doesn't apply (e.g. non-code files).
3. **Read relevant files**: `Read(file_path="<path>")` for files identified above.
4. **Document findings**: fill the Skill Return section below (no separate write step).

## Restrictions

- **NO edits allowed** - read-only exploration
- **NO file creation** - documentation only
- Must update WORKING_MEMORY with findings

## Skill Return Format

```markdown
## Skill Return

- **Skill**: swe-workflow-research
- **Status**: [success|success_with_findings|needs_clarification]
- **Findings Summary**: [2-3 sentences describing what was found]
- **Artifacts**: [list of relevant files, patterns discovered]
- **Next Step Hint**: WF_CLASSIFY
```

## Exit

Output: `> **Skill /swe-workflow-research complete** - returning to WF_CLASSIFY`
