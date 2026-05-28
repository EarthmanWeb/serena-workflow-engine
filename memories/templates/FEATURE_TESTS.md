# FEATURE_TESTS - Test Suite (Template)

## Feature Overview

| Property      | Value                  |
| ------------- | ---------------------- |
| **Name**      | Test Suite             |
| **Key**       | TESTS                  |
| **Type**      | infrastructure         |
| **Language**  | {{primary_language}}   |
| **Framework** | {{test_framework}}     |

## Running Tests

**ALWAYS use project scripts. All commands run from the project root.**

```bash
# TODO: Customize these per project
{{test_commands}}
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

## Scope Definition

### Primary Directories

| Directory           | Purpose                        |
| ------------------- | ------------------------------ |
| `{{test_root}}/`    | Root of the test suite         |

## Test Runner Config

| Setting      | Value                  |
| ------------ | ---------------------- |
| **Framework**| `{{test_framework}}`   |
| **Root**     | `{{test_root}}`        |

## Test Suites

| Suite   | File   | Focus   |
| ------- | ------ | ------- |
| _TODO: Add test suites_ | | |
