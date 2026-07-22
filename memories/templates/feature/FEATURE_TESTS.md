---
name: Test Suite
description: Test runner, verification approach, and task-completion checklist for this project.
metadata:
  type: feature
---

# FEATURE_TESTS - Test Suite (Template)

## Feature Overview

| Property      | Value                  |
| ------------- | ---------------------- |
| **Name**      | Test Suite             |
| **Key**       | TESTS                  |
| **Type**      | infrastructure         |
| **Language**  | python   |
| **Framework** | unknown     |

## Running Tests

**ALWAYS use project scripts. All commands run from the project root.**

```bash
# TODO: Customize these per project
# TODO: Add test commands
```

### Test Gate

The test gate hook (`swe_pre_bash_test_gate.py`) **blocks** direct test runner
commands until this memory has been read in the current session.

**How it works:**

1. `swe_pre_bash_test_gate.py` intercepts Bash commands matching test patterns
2. Checks for sentinel file: `.serena/streams/.test_feature_{session_id}`
3. If missing -> **blocks** with instruction to read FEATURE_TESTS
4. When FEATURE_TESTS is read, `swe_post_read_state.py` calls
   `create_feature_sentinel(session_id, 'test')` which creates the sentinel
5. Subsequent test commands pass instantly (file existence check)

## Per-Project Customization

When adapting this template for a project:

1. **Replace remaining placeholders** with actual values
2. **Add test scripts table** -- list all test scripts from your package manager
3. **Add fixtures section** -- document available fixtures and their APIs
4. **Add test categories** -- list spec files with descriptions
5. **Add config details** -- document runner config (timeouts, workers, etc.)
6. **Add auth setup** -- document how authentication storage state works (if applicable)
7. **Remove this section** after customization

## Gherkin BDD Specs

Gherkin `.feature` files define testable behavioral specifications using Given/When/Then syntax.

| Property | Value |
| -------- | ----- |
| **Specs Directory** | `tests/specs/` |
| **File Pattern** | `[feature-key]-[slug].feature` |
| **Spec Authoring** | `/swe-gherkin-spec [KEY]` |
| **TDD from Spec** | `/swe-gherkin-dev [slug]` |

### Workflow Integration

- **New features**: Gherkin specs are prompted during `/swe-feature-onboard` and enforced at `WF_ARCH_REVIEW`
- **Feature additions**: `WF_VERIFY` checks if existing specs need new scenarios for changed behavior
- **Spec memories**: Each spec creates a `SPEC_[KEY]_[SLUG]` memory tracking coverage status

### Convention

- One `.feature` file per logical feature area
- Scenarios cover happy path, error cases, edge cases, and state transitions
- Each Given/When/Then step maps 1:1 to a test assertion
- No `test.fixme()` or `test.skip()` — 100% coverage required

## Scope Definition

### Primary Directories

| Directory           | Purpose                        |
| ------------------- | ------------------------------ |
| `tests/`    | Root of the test suite         |
| `tests/specs/` | Gherkin BDD specification files |

## Test Runner Config

| Setting      | Value                  |
| ------------ | ---------------------- |
| **Framework**| `unknown`   |
| **Root**     | `tests/`        |

## Test Suites

| Suite   | File   | Focus   |
| ------- | ------ | ------- |
| _TODO: Add test suites_ | | |
