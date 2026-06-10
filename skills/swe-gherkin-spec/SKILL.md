---
name: swe-gherkin-spec
version: 1.0.0
description: Write Gherkin BDD specs for a feature. Creates .feature files in tests/specs/ from requirements, user stories, or free-form descriptions.
workflow:
  aware: true
  callable_from:
    - WF_CLASSIFY
    - WF_ARCH_REVIEW
    - WF_EXECUTE
  default_return: WF_ARCH_REVIEW
  supports_standalone: true
  auto_transition: true
args:
  - name: feature
    description: Feature key or name to spec (optional, will prompt if not provided)
  - name: slug
    description: Spec slug for the .feature filename (optional, derived from feature if not provided)
---

## ⚠️ WORKFLOW INITIALIZATION

**If starting a new session**, first read workflow initialization:

```
mcp__plugin_swe_serena__read_memory("wf/WF_INIT")
```

Follow WF_INIT instructions before executing this skill.

---

# /swe-gherkin-spec [FEATURE] [--slug SLUG]

Write Gherkin BDD specifications for a feature. Creates `.feature` files in the project's `tests/specs/` directory.

## Usage

```bash
/swe-gherkin-spec                        # Interactive — prompts for feature and requirements
/swe-gherkin-spec AUTH                    # Spec the AUTH feature
/swe-gherkin-spec AUTH --slug login-flow  # Spec with explicit filename slug
```

## When to Use

- New feature being planned or designed
- Requirements exist but no formal spec
- User describes behavior that needs to be captured as testable scenarios
- WF_ARCH_REVIEW detects missing specs for a feature

## Step 0: Resolve Feature Context

### 0a. Identify the feature

If `$ARGUMENTS` includes a feature key, use it. Otherwise:

```
mcp__plugin_swe_serena__read_memory("index/INDEX_FEATURES")
```

Present registered features and ask:

```javascript
AskUserQuestion({
  questions: [{
    question: "Which feature should I write Gherkin specs for?",
    header: "Feature",
    options: [
      // Populate from INDEX_FEATURES
    ],
    multiSelect: false
  }]
})
```

### 0b. Load feature context

```
mcp__plugin_swe_serena__read_memory("feature/FEATURE_[KEY]")
```

Load all supporting memories from the feature's Related Memories table (DOM_*, SYS_*, ARCH_*).

### 0c. Determine spec directory

Check for existing specs directory:

```
Glob(pattern="tests/specs/**/*.feature")
Glob(pattern="test/specs/**/*.feature")
Glob(pattern="spec/**/*.feature")
```

**Convention:** Use `tests/specs/` as the default. If the project already has `.feature` files elsewhere, use that location instead.

If the directory doesn't exist, create it:

```bash
mkdir -p tests/specs
```

### 0d. Check for existing specs

If specs already exist for this feature:

```
Glob(pattern="tests/specs/*[feature-key]*.feature")
```

Present them and ask whether to extend or create new.

## Step 1: Gather Requirements

### 1a. From user input

Parse the user's request for behavioral requirements. Look for:

- User stories ("As a... I want... So that...")
- Acceptance criteria ("should", "must", "when X then Y")
- Behavioral descriptions
- Edge cases and error scenarios

### 1b. From codebase (if feature exists)

If the feature already has implementation, research it:

```
mcp__plugin_swe_serena__get_symbols_overview("[feature root path]", depth=1)
mcp__plugin_swe_serena__search_for_pattern(substring_pattern="...", relative_path="[feature path]")
```

Extract implicit requirements from existing code behavior.

### 1c. From domain memories

Check DOM_* memories for behavioral rules that apply:

```
mcp__plugin_swe_serena__list_memories(topic="dom")
```

Read any that relate to this feature's domain.

## Step 2: Structure Scenarios

Organize requirements into Gherkin features and scenarios:

```gherkin
Feature: [Feature name]
  [Brief description of the feature's purpose]

  Background:
    [Common preconditions shared across scenarios]

  Scenario: [Descriptive scenario name]
    Given [precondition]
    When [action]
    Then [expected outcome]
    And [additional assertion]

  Scenario Outline: [Parameterized scenario name]
    Given [precondition with <parameter>]
    When [action with <parameter>]
    Then [expected outcome with <parameter>]

    Examples:
      | parameter | expected |
      | value1    | result1  |
      | value2    | result2  |
```

### Structuring Rules

- **One Feature per file** — each `.feature` file covers one logical feature area
- **Descriptive scenario names** — name describes the behavior, not the implementation
- **Given/When/Then discipline** — Given = preconditions, When = actions, Then = assertions
- **And/But for continuation** — use And/But to extend Given/When/Then, not to start new flows
- **Background for shared setup** — extract common Given steps into Background
- **Scenario Outline for data-driven** — use when the same flow applies to multiple inputs
- **Tags for categorization** — use `@tag` for grouping (e.g., `@smoke`, `@regression`, `@wip`)
- **No implementation details** — specs describe WHAT, not HOW

### Coverage Completeness

Every spec must include:

- **Happy path** — the primary success scenario
- **Error cases** — invalid inputs, missing data, permission failures
- **Edge cases** — boundary values, empty states, concurrent access
- **State transitions** — before/after states for stateful operations

## Step 3: Present Draft for Review

Present the draft spec with a coverage summary:

```markdown
## Gherkin Spec Draft: [FEATURE_KEY] / [slug]

### File: `tests/specs/[feature-key]-[slug].feature`

[Full Gherkin content]

### Coverage Summary

| # | Scenario | Type | Requirement Source |
|---|----------|------|--------------------|
| 1 | [name]   | Happy path | User request / DOM_* / Existing code |
| 2 | [name]   | Error case | Inferred from domain rules |
| ...

### Questions

[Any ambiguities that need clarification before finalizing]
```

**Wait for user approval before writing the file.**

## Step 4: Write the Spec File

### 4a. Filename convention

```
tests/specs/[feature-key]-[slug].feature
```

- Feature key: lowercase, from FEATURE_[KEY]
- Slug: lowercase, hyphenated, descriptive (e.g., `auth-login-flow`, `cart-checkout`)

### 4b. Write the file

```
Write(file_path="[project_root]/tests/specs/[feature-key]-[slug].feature", content="[gherkin content]")
```

### 4c. Create SPEC_* memory

Create a tracking memory for this spec:

```
mcp__plugin_swe_serena__write_memory("spec/SPEC_[KEY]_[SLUG]", "<content>")
```

Memory content:

```markdown
# SPEC_[KEY]_[SLUG] - [Feature Name]: [Spec Title]

## Spec File

| Property | Value |
|----------|-------|
| **File** | `tests/specs/[feature-key]-[slug].feature` |
| **Feature Key** | [KEY] |
| **Created** | [date] |
| **Status** | draft |

## Coverage Map

| # | Type | Line | Implemented | Tested |
|---|------|------|-------------|--------|
| 1 | Given | [step text] | No | No |
| 2 | When | [step text] | No | No |
| 3 | Then | [step text] | No | No |

## Linked Artifacts

| Type | Path |
|------|------|
| Spec file | `tests/specs/[filename].feature` |
| Test file | _(not yet created)_ |
| Feature memory | `feature/FEATURE_[KEY]` |
```

### 4d. Update FEATURE_[KEY] memory

If the feature memory has a Testing section, append the new spec reference:

```
mcp__plugin_swe_serena__edit_memory(
  "feature/FEATURE_[KEY]",
  "## Testing",
  "## Testing\n\n| Suite | File | Focus |\n|...\n| Gherkin Spec | tests/specs/[filename].feature | [description] |",
  "literal"
)
```

## Step 5: Multiple Specs

If the feature requires multiple spec files (large feature with distinct areas):

1. Create one `.feature` file per logical area
2. Create one `SPEC_*` memory per file
3. Use consistent tagging across files (`@feature-key`)

## Skill Return Format

```markdown
## Skill Return

- **Skill**: swe-gherkin-spec
- **Status**: [success|needs_clarification]
- **Feature Key**: [KEY]
- **Spec Files Created**: [list of .feature file paths]
- **SPEC Memories Created**: [list of SPEC_* memory names]
- **Coverage**: [N scenarios, M steps total]
- **Next Step Hint**: WF_ARCH_REVIEW (plan implementation) or /swe-gherkin-dev (start TDD)
```

## Exit

```
> **Skill /swe-gherkin-spec complete** - [N] spec(s) written to tests/specs/
```
