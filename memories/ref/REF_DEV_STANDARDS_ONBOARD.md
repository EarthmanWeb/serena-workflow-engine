---
name: REF_DEV_STANDARDS_ONBOARD
description: Procedure for discovering, documenting, and indexing development standards in any codebase via parallel research agents.
metadata:
  type: reference
---

# REF_DEV_STANDARDS_ONBOARD — Development Standards Discovery

Use parallel agents to research existing codebase patterns. Compile into indexed, navigable memories. Execute Phase 1 → Phase 5 in order.

## Phase 1 — Launch Research Agents

Launch one `Agent` per focus area, `run_in_background: true`, `model: "sonnet"`, ALL in ONE message. Prefix every agent prompt with `You are a subagent. BYPASS WF_INIT.`

```javascript
Agent({ description: "PHP standards", run_in_background: true, model: "sonnet",
  prompt: "You are a subagent. BYPASS WF_INIT. Research PHP coding patterns..." })
Agent({ description: "JS standards", run_in_background: true, model: "sonnet",
  prompt: "You are a subagent. BYPASS WF_INIT. Research JavaScript patterns..." })
```

| Agent Focus        | Research Area                         |
| ------------------ | ------------------------------------- |
| php-standards      | PHP coding patterns, class structure  |
| js-standards       | JavaScript patterns, module structure |
| scss-standards     | SCSS/CSS patterns, variables          |
| template-standards | Template engine patterns              |
| test-standards     | Test framework patterns               |
| naming-conventions | File/class/function naming            |
| file-organization  | Directory structure                   |
| build-tooling      | Build system, scripts                 |
| class-structure    | OOP patterns, inheritance             |
| hooks-filters      | Framework integration patterns        |

## Phase 2 — Analyze Configuration Files

Research these config sources. Adapt file list to project.

| Config Type         | Common Files                                         |
| ------------------- | ---------------------------------------------------- |
| PHP linting         | `ruleset.xml`, `phpcs.xml`, `.php-cs-fixer.php`       |
| JS linting          | `biome.json`, `.eslintrc`, `prettier.config.js`      |
| SCSS formatting     | `.prettierrc`, `stylelint.config.js`                 |
| Template formatting | `.bladeformatterrc.json`, `.twigcs.yml`              |
| Package config      | `composer.json`, `package.json`                      |
| Build config        | `gulpfile.js`, `webpack.config.js`, `vite.config.js` |

## Phase 3 — Sample Code Analysis

Analyze representative files per language/area:

- PHP: find class files; examine naming, indentation, docblocks.
- JavaScript: find module files; examine patterns (IIFE, ES6).
- SCSS: find stylesheets; examine variables, nesting, naming.
- Templates: find templates; examine inheritance, safe output.
- Tests: find test files; examine fixtures, assertions, setup.

Launch analysis agents in parallel — one per language/area. Prefix every agent prompt with `You are a subagent. BYPASS WF_INIT.`

```javascript
Agent({ description: "Analyze PHP patterns", run_in_background: true, model: "sonnet",
  prompt: "You are a subagent. BYPASS WF_INIT. Analyze PHP class files for patterns..." })
```

## Phase 4 — Compile Findings

### Index Entry Point

Create `FEATURE_DEV_STANDARDS` as a short index (~50 lines) containing:

- Quick-reference table linking to subsections.
- Universal standards (indentation, line endings, encoding).
- Lint command reference.
- Pre-commit checklist.

### Subsection Memories

Split detailed standards into ~100–120 line files:

| Memory                  | Content                                       |
| ----------------------- | --------------------------------------------- |
| `DEV_PHP`               | PHP standards, class naming, method naming    |
| `DEV_JAVASCRIPT`        | JS standards, linter config, module patterns  |
| `DEV_SCSS`              | SCSS standards, variables, formatting         |
| `DEV_[TEMPLATE_ENGINE]` | Template patterns (BladeOne, Twig, etc.)      |
| `DEV_TESTS`             | Test framework patterns, fixtures, assertions |
| `DEV_BUILD`             | Build system, commands, scripts               |
| `DEV_PATTERNS`          | High-level architecture patterns              |

### Standard Memory Format

Each `DEV_*` memory MUST include:

```markdown
# DEV_[AREA] - [Area] Standards

## Tools

- **Linter**: [tool name]
- **Config**: [config file path]

## Formatting

- **Indentation**: [spaces/tabs]
- **Quotes**: [single/double]
- [other formatting rules]

## Naming Conventions

- **Files**: [pattern]
- **Classes**: [pattern]
- **Functions**: [pattern]

## Patterns

[Code examples with explanations]

## Lint Commands

\`\`\`bash
[relevant commands]
\`\`\`
```

## Phase 5 — Integration

Add to `MEMORY.md`:

```markdown
## Development Standards

**Entry Point**: `FEATURE_DEV_STANDARDS`

| Standard   | Memory           |
| ---------- | ---------------- |
| PHP        | `DEV_PHP`        |
| JavaScript | `DEV_JAVASCRIPT` |
| [etc.]     | [etc.]           |
```

## Checklist

- [ ] Research subagents launched in parallel (one per focus area).
- [ ] Config files analyzed (PHP, JS, SCSS, templates, tests).
- [ ] Code samples examined for patterns.
- [ ] `FEATURE_DEV_STANDARDS` created as index entry point.
- [ ] Individual `DEV_*` memories created (~100–120 lines each).
- [ ] `MEMORY.md` updated with Development Standards section.
- [ ] WM updated with completion status.

## Output Structure

```
FEATURE_DEV_STANDARDS (entry point, ~50 lines)
├── DEV_PHP (~100 lines)
├── DEV_JAVASCRIPT (~100 lines)
├── DEV_SCSS (~100 lines)
├── DEV_[TEMPLATE_ENGINE] (~100 lines)
├── DEV_TESTS (~100 lines)
├── DEV_BUILD (~100 lines)
└── DEV_PATTERNS (~100 lines)
```
