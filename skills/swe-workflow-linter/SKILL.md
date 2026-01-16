---
name: swe-workflow-linter
version: 1.0.0
description: Run code linting and formatting checks
workflow:
  aware: true
  callable_from:
    - WF_VERIFY
  default_return: WF_DONE
  supports_standalone: true
  auto_transition: false
---

# Workflow Linter Skill

Run code quality checks and linting.

## Purpose

- Check code style compliance
- Find potential issues
- Verify formatting
- Report quality metrics

## Actions

1. **Detect linter** - Find configured linter (eslint, phpcs, etc.)
2. **Run linter** - Execute on changed files
3. **Parse output** - Extract issues
4. **Report findings** - Document in Skill Return

## Supported Linters

| Language | Linter |
|----------|--------|
| JavaScript/TypeScript | ESLint |
| PHP | PHPCS, PHPStan |
| Python | pylint, flake8 |
| Go | golint |
| Rust | clippy |

## Skill Return Format

```markdown
## Skill Return
- **Skill**: swe-workflow-linter
- **Status**: [success|success_with_findings|blocked]
- **Findings Summary**: [lint results summary]
- **Artifacts**: [issues found, files checked]
- **Next Step Hint**: WF_DONE
```

## Exit

`> **Skill /swe-workflow-linter complete** - returning to WF_DONE`
