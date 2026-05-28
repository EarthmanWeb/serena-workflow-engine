# FEATURE_DEV_STANDARDS - Development Standards Index

## Project: {{project_name}}

**Primary Language:** {{primary_language}}

## Standards by Language

<!-- Add DEV_* memories for each language used in the project -->

| Language               | Memory          | Status      |
| ---------------------- | --------------- | ----------- |
| {{primary_language}}   | `DEV_{{primary_language_upper}}` | TODO: Create |

## General Standards

### Code Style

- Follow existing project conventions (check existing files first)
- Use the project's configured linter/formatter if available
- Consistent naming: match the casing convention already in use

### File Organization

- New files follow existing directory structure patterns
- Group related functionality together
- Keep files focused on a single responsibility

### Error Handling

- Fail fast with clear error messages
- No silent failures or empty catch blocks
- Log errors at appropriate severity levels

### Testing

- See `FEATURE_TESTS` for test runner and patterns
- New functional code should have corresponding tests
- Follow existing test patterns in the project

## Per-Project Customization

1. **Create `DEV_*` memories** for each language (e.g., `DEV_PHP`, `DEV_PYTHON`)
2. **Add project-specific standards** (naming conventions, file headers, etc.)
3. **Document CI/CD requirements** (lint checks, coverage thresholds)
4. **Remove this section** after customization
