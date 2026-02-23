# FEATURE_TESTS - E2E Test Suite (Template)

> **Plugin template.** Copy to project Serena memories and customize placeholders.

## Feature Overview

| Property | Value |
|----------|-------|
| **Name** | E2E Test Suite |
| **Key** | TESTS |
| **Type** | infrastructure |
| **Language** | TypeScript |
| **Framework** | Playwright |

## ⚠️ MANDATORY: Running Tests

**ALWAYS use npm scripts. All commands run from the test root directory.**

```bash
# Customize these per project in package.json
npm test                                    # Run all tests
npm run test:suite -- <path>                # Specific test file
npm run test:single -- "<pattern>"          # Single test by grep pattern
```

**❌ DO NOT USE (bypasses test runner):**
- `npx playwright test ...` directly
- Running from project root instead of test directory

### Test Gate

The test gate hook (`swe_pre_bash_test_gate.py`) **blocks** `npx playwright test`
commands until this memory has been read in the current session.

**How it works:**
1. `swe_pre_bash_test_gate.py` intercepts Bash commands matching `npx playwright test`
2. Checks for sentinel file: `.serena/streams/.test_feature_{session_id}`
3. If missing → **blocks** with instruction to read FEATURE_TESTS
4. When FEATURE_TESTS is read, `swe_post_read_state.py` calls `create_feature_sentinel(session_id, 'test')` which creates the sentinel
5. Subsequent test commands pass instantly (file existence check)

**Sentinel naming:** `.test_feature_{session_id}` — session-scoped, no cross-session leakage.

**Gate command patterns** (in `TEST_COMMAND_PATTERNS`):
```python
r'\bnpx\s+playwright\s+test\b'
```

To gate additional commands (e.g., `npm run test`), add patterns to the list in the pre-hook.

## Per-Project Customization

When adapting this template for a project:

1. **Replace placeholders** (`{test_root}`, `{base_url}`, etc.) with actual values
2. **Add npm scripts table** — list all `test:*` scripts from `package.json`
3. **Add fixtures section** — document available fixtures and their APIs
4. **Add test categories** — list spec files with descriptions
5. **Add Playwright config** — document baseURL, workers, timeouts, projects
6. **Add auth setup** — document how authentication storage state works
7. **Remove this section** after customization

## Scope Definition

### Primary Directories

| Directory | Purpose |
|-----------|---------|
| `{test_root}/` | Root of the E2E test suite |
| `{test_root}/tests/` | Test spec files |
| `{test_root}/fixtures/` | Reusable test fixtures/helpers |
| `{test_root}/storage-state/` | Persisted auth state (gitignored) |

## Playwright Config

| Setting | Value |
|---------|-------|
| **Base URL** | `{base_url}` |
| **Workers** | `{workers}` |
| **Timeout** | `{timeout}` |
| **Browser** | Desktop Chrome |

## Testing

| Suite | File | Focus |
|-------|------|-------|
| _suite_ | _file_ | _focus_ |
