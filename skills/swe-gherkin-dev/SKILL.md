---
name: swe-gherkin-dev
version: 1.0.0
description: "TDD from Gherkin specs. Takes a .feature file or SPEC_* memory, builds a coverage map, implements both functionality and tests to achieve 100% compliance. Builds missing functionality, creates real tests (no fixme), follows all dev standards."
workflow:
  aware: true
  callable_from:
    - WF_CLASSIFY
    - WF_EXECUTE
    - WF_ARCH_REVIEW
  default_return: WF_VERIFY
  supports_standalone: true
  auto_transition: true
args:
  - name: spec
    description: "Spec filename, slug, or SPEC_* memory name (e.g., auth-login, auth-login.feature, SPEC_AUTH_LOGIN)"
---

## ⚠️ WORKFLOW INITIALIZATION

**If starting a new session**, first read workflow initialization:

```
mcp__plugin_swe_serena__read_memory("wf/WF_INIT")
```

Follow WF_INIT instructions before executing this skill.

---

# /swe-gherkin-dev [SPEC]

Implement functionality AND tests from a Gherkin `.feature` spec.
Full TDD — if the functionality doesn't exist, build it.

## Usage

```bash
/swe-gherkin-dev                          # List available specs, pick one
/swe-gherkin-dev auth-login               # Find spec by slug
/swe-gherkin-dev auth-login.feature       # Find spec by filename
/swe-gherkin-dev SPEC_AUTH_LOGIN          # Find spec by memory name
```

## Methodology

- **100% Gherkin compliance** — tests must cover every Given/When/Then/And line
- **No `test.fixme()` or `test.skip()`** — implement real tests with real functionality
- **If functionality doesn't exist, build it** — this is TDD, not stub writing
- **Can test more but not less** — keep all existing assertions, add missing ones
- **Continue through until complete** — all functionality and tests in place

## Step 0: Spec Selection

### 0a. Resolve the argument to a `.feature` file

Extract the slug from `$ARGUMENTS` by stripping `.feature` or `.spec.*` extensions.

**Strategy 1: Check SPEC_* memories**

```
mcp__plugin_swe_serena__list_memories(topic="spec")
```

If a SPEC_* memory matches the argument, read it to get the `.feature` file path.

**Strategy 2: Glob for .feature files**

```
Glob(pattern="tests/specs/**/*{slug}*.feature")
Glob(pattern="test/specs/**/*{slug}*.feature")
Glob(pattern="spec/**/*{slug}*.feature")
```

If a single match → proceed to Step 1.
If multiple matches → present them and ask user to pick.

### 0b. If no argument or no match found

List all available `.feature` files:

```
Glob(pattern="**/*.feature")
```

Present them grouped by directory:

```
Available Gherkin specs:

tests/specs/:
  1. auth-login-flow.feature
  2. auth-registration.feature
  ...

Which spec should I develop?
```

**Stop and wait for user input.**

## Step 1: Load and Parse Gherkin Spec

Read the `.feature` file:

```
Read(file_path="[spec_path]")
```

Parse into a structured coverage map:

| # | Type | Line | Covered | Implementation Exists |
|---|------|------|---------|-----------------------|
| 1 | Given | user is on the login page | No | ? |
| 2 | When | user enters valid credentials | No | ? |
| 3 | Then | user is redirected to dashboard | No | ? |
| 4 | And | session token is stored | No | ? |

**Every Given/When/Then/And line becomes a row.** Nothing is skipped.

For Scenario Outlines, each example row generates its own coverage entries.

## Step 2: Deep Research (Before Asking Questions)

**Exhaust all codebase research BEFORE asking the user anything.**

### 2a. Load Feature Context

Determine which feature(s) the spec targets from file paths, domain terms, or
explicit feature references in the spec.

```
mcp__plugin_swe_serena__read_memory("index/INDEX_FEATURES")
mcp__plugin_swe_serena__read_memory("feature/FEATURE_[KEY]")
```

Load ALL supporting memories referenced in the feature:
- `DOM_*` — domain patterns
- `SYS_*` — system architecture
- `REF_*` — coding standards
- `INDEX_*` — file/symbol indexes

### 2b. Verify Existing Implementation

For each Given/When/Then line, search the codebase:

```
mcp__plugin_swe_serena__search_for_pattern(substring_pattern="...", relative_path="...")
mcp__plugin_swe_serena__find_symbol(name_path_pattern="...", relative_path="...")
```

Update the coverage map column "Implementation Exists" with:
- **Yes** — functionality exists, just needs test coverage
- **Partial** — some logic exists, needs completion
- **No** — must be built from scratch

### 2c. Verify Existing Tests

Glob for matching test files:

```
Glob(pattern="tests/**/*{slug}*.*")
```

Read every matched test file to understand:
- Which tests exist (names, structure)
- Which are real tests vs stubs
- Which spec lines they already cover
- What fixtures and helpers they use

Update the coverage map:
- Stubs (`fixme`, `skip`, `todo`) → Covered: **No**
- Passing real tests → Covered: **Yes**
- No matching test → Covered: **No**

### 2d. Load Dev Standards (BLOCKING)

**You MUST read development standards before writing ANY code:**

```
mcp__plugin_swe_serena__read_memory("feature/FEATURE_DEV_STANDARDS")
mcp__plugin_swe_serena__read_memory("feature/FEATURE_TESTS")
```

Load language-specific standards based on what needs building:

```
mcp__plugin_swe_serena__list_memories(topic="dev")
```

Read all DEV_* memories relevant to the affected languages.

### 2e. Use Existing Helpers

**Before writing ANY test setup code, check existing test helpers and fixtures.**

Read FEATURE_TESTS for documented helpers. Then explore the test directory:

```
mcp__plugin_swe_serena__get_symbols_overview("[test_root]/", depth=1)
```

**Rules:**
- Always use existing helper methods — never hand-roll setup that helpers already provide
- Each test must be self-contained — create its own state, never share across tests
- Check helper files for existing methods before creating inline functions
- If a helper method doesn't exist but should, add it to the helper following existing patterns

## Step 3: Identify Questions (Only If Research Was Insufficient)

**Only ask the user questions that could NOT be answered from the spec or codebase.**

Valid questions:
- Ambiguous behavior not specified in the Gherkin
- Missing acceptance criteria for edge cases
- Architectural choice between two valid patterns
- External system dependencies not documented

Invalid questions (answer from codebase):
- "Where should this file go?" — check existing patterns
- "What helper should I use?" — check test helpers
- "What naming convention?" — check DEV_* memories

Present questions grouped:

```
## Questions Before Implementation

### Behavior Clarification
1. [question] — researched [what you found], but spec is ambiguous about [specific gap]

### Architecture Decision
2. [question] — two valid approaches: [A] vs [B], spec doesn't indicate preference
```

**If no questions needed, skip directly to Step 4.**

## Step 4: Implementation Plan

Present a structured plan before writing code:

```
## Implementation Plan for [SPEC_NAME]

### Functionality to Build (TDD RED phase)
| # | Component | File | Type | Description |
|---|-----------|------|------|-------------|
| 1 | [name] | [path] | [language] | [what it does] |

### Tests to Create (TDD GREEN phase)
| # | Test Name | Spec Lines | File |
|---|-----------|------------|------|
| 1 | [test description] | Given #1, When #2, Then #3 | [path] |

### Existing Tests to Preserve
| # | Test Name | File | Status |
|---|-----------|------|--------|
| 1 | [existing test] | [path] | Keep as-is / Extend |

### Execution Order
1. [first thing to build/test]
2. [second thing]
...
```

**Wait for user approval before proceeding.**

## Step 5: Execute TDD Cycle

For each group of related spec lines:

### 5a. RED — Write the Test First

Create the test that will fail because functionality doesn't exist yet.

**Test Standards (from FEATURE_TESTS and DEV_*):**
- Follow the project's test file naming convention
- Use the project's test framework and fixtures
- Map each test to specific Given/When/Then lines via comments
- Three-phase pattern: Setup / Action / Verify

```
// Spec: Given [line], When [line], Then [line]
test('[description from spec line]', async () => {
  // Given: [setup from spec]
  // ...

  // When: [action from spec]
  // ...

  // Then: [assertion from spec]
  // ...
});
```

Adapt the test structure to the project's framework (pytest, jest, playwright, phpunit, etc.).

### 5b. GREEN — Build the Functionality

Implement the minimal functionality to make the test pass.

**Follow existing patterns:**
- Check codebase for similar implementations before creating new ones
- Use Serena tools (`find_symbol`, `get_symbols_overview`) to locate insertion points
- Follow DEV_* standards for the relevant language
- Follow DOM_* behavioral rules for the domain

### 5c. VERIFY — Run the Test

Use the test command from FEATURE_TESTS to run the specific test.

- If test passes: update coverage map, move to next spec line group
- If test fails: diagnose root cause, fix, re-run
- **Fix the app, not the test** — failing test = application bug until proven otherwise
- **NEVER weaken assertions** to make a test pass

### 5d. Repeat

Continue the RED/GREEN cycle until ALL spec lines are covered.

## Step 6: Final Validation

**You are NOT done until every test passes. No exceptions.**

### 6a. Run Each New Test Individually

Run every new or modified test one at a time using the project's test runner.

**For EACH test:**
- **PASS** → mark as passing, move to next
- **FAIL** → enter the TDD fix loop (6b)

### 6b. TDD Fix Loop (Mandatory on Failure)

When a test fails:

1. **Read the failure output** — exact error, line number, actual vs expected
2. **Diagnose root cause** — use logging, debugger, or tracepoints as appropriate
3. **Identify whether test bug or app bug:**
   - **Test bug** (wrong selector, wrong assertion, wrong API method): fix the test
   - **Implementation bug** (code doesn't behave as spec requires): fix the implementation
4. **Make the fix** — one targeted change, not a rewrite
5. **Re-run the same test**
6. **Repeat until it passes**

**Rules:**
- **NEVER skip a failing test**
- **NEVER add arbitrary delays or sleep to fix timing issues** — use proper waits
- **NEVER weaken assertions** to make a test pass — fix the code
- **NEVER mark a test as fixme/skip** — make it work
- **Max 3 fix attempts per test** — if still failing after 3 targeted fixes, stop and ask the user

### 6c. Run the Full Spec's Test File

Only after ALL individual tests pass, run the full test file:

- **All pass** → proceed to 6d
- **Failures** → fix using the TDD fix loop (6b), then re-run

### 6d. Coverage Map Audit

Re-check the coverage map — every row must show:
- **Covered: Yes**
- **Implementation Exists: Yes**

Any row with "No" is a failure. Go back and implement.

### 6e. Update SPEC_* Memory

Update the SPEC_* memory with final coverage status:

```
mcp__plugin_swe_serena__edit_memory(
  "spec/SPEC_[KEY]_[SLUG]",
  "**Status** | draft",
  "**Status** | complete",
  "literal"
)
```

Update all coverage map rows to show Implemented: Yes, Tested: Yes.

### 6f. Compliance Checklist

- [ ] Every Given/When/Then/And line has a corresponding test assertion
- [ ] **All new tests passing** (verified by running each one)
- [ ] **Full test file passing** (all tests together)
- [ ] No `test.fixme()` or `test.skip()` in any new tests
- [ ] New functionality follows existing codebase patterns
- [ ] Dev standards followed (DEV_* memories)
- [ ] No timeout hacks (arbitrary delays, sleep)
- [ ] SPEC_* memory updated with complete status

### 6g. Present Results

```
## Gherkin Dev Complete: [SPEC_NAME]

### Coverage Map (Final)
| # | Type | Line | Covered | Implementation |
|---|------|------|---------|---------------|
| 1 | Given | ... | Yes | Built / Existed |
| ... |

### Files Created/Modified
| File | Action | Description |
|------|--------|-------------|
| [path] | Created/Modified | [what changed] |

### Test Results
- New tests: [count] passing
- Full file: all passing
- Spec coverage: 100%
```

## Edge Cases

### Spec references functionality that spans multiple features
Load ALL affected feature memories. Follow cross-feature patterns from ARCH_INDEX.

### Spec line is a duplicate of an existing test
Keep the existing test. Add a comment mapping it to the spec line.

### Existing test covers spec line partially
Extend the test with additional assertions. Never remove existing assertions.

### Functionality exists but has no test
Write the test. Verify it passes. If it fails, the functionality has a bug — fix the bug (TDD).

### No test framework configured
Stop and inform the user. FEATURE_TESTS must be configured with a test runner before TDD can proceed. Suggest running `/swe-feature-onboard` or manually updating FEATURE_TESTS.

## Skill Return Format

```markdown
## Skill Return

- **Skill**: swe-gherkin-dev
- **Status**: [success|needs_clarification|blocked]
- **Spec File**: [path to .feature file]
- **Coverage**: [N/N steps covered — 100%]
- **Tests Created**: [count]
- **Files Modified**: [count]
- **Next Step Hint**: WF_VERIFY
```

## Exit

```
> **Skill /swe-gherkin-dev complete** - [spec name] at 100% coverage
```
