# REF_DEV_STANDARDS_ONBOARD - Development Standards Discovery

**Generic guide for discovering and documenting development standards in any codebase.**

## Overview

This workflow uses a multi-agent swarm to research existing codebase patterns and compile them into indexed, navigable documentation.

## Phase 1: Initialize Research Swarm

```
mcp__ruv-swarm__swarm_init(topology: "mesh", maxAgents: 10, strategy: "balanced")
```

Spawn specialized research agents:

| Agent Type | Focus Area |
|------------|------------|
| php-standards | PHP coding patterns, class structure |
| js-standards | JavaScript patterns, module structure |
| scss-standards | SCSS/CSS patterns, variables |
| template-standards | Template engine patterns |
| test-standards | Test framework patterns |
| naming-conventions | File/class/function naming |
| file-organization | Directory structure |
| build-tooling | Build system, scripts |
| class-structure | OOP patterns, inheritance |
| hooks-filters | Framework integration patterns |

## Phase 2: Analyze Configuration Files

Research these config sources (adapt to project):

| Config Type | Common Files |
|-------------|--------------|
| PHP linting | `ruleset.xml`, `phpcs.xml`, `.php-cs-fixer.php` |
| JS linting | `biome.json`, `.eslintrc`, `prettier.config.js` |
| SCSS formatting | `.prettierrc`, `stylelint.config.js` |
| Template formatting | `.bladeformatterrc.json`, `.twigcs.yml` |
| Package config | `composer.json`, `package.json` |
| Build config | `gulpfile.js`, `webpack.config.js`, `vite.config.js` |

## Phase 3: Sample Code Analysis

For each language/area, analyze representative files:

1. **PHP**: Find class files, examine naming, indentation, docblocks
2. **JavaScript**: Find module files, examine patterns (IIFE, ES6, etc.)
3. **SCSS**: Find stylesheets, examine variables, nesting, naming
4. **Templates**: Find templates, examine inheritance, safe output
5. **Tests**: Find test files, examine fixtures, assertions, setup

Use swarm orchestration:
```
mcp__ruv-swarm__task_orchestrate(task: "[specific research task]", strategy: "parallel")
```

## Phase 4: Compile Findings

### Create Index Entry Point

Create `REF_DEV_STANDARDS` as short index (~50 lines):
- Quick reference table linking to subsections
- Universal standards (indentation, line endings, encoding)
- Lint command reference
- Pre-commit checklist

### Create Subsection Memories

Split detailed standards into ~100-120 line files:

| Memory | Content |
|--------|---------|
| `DEV_PHP` | PHP standards, class naming, method naming |
| `DEV_JAVASCRIPT` | JS standards, linter config, module patterns |
| `DEV_SCSS` | SCSS standards, variables, formatting |
| `DEV_[TEMPLATE_ENGINE]` | Template patterns (BladeOne, Twig, etc.) |
| `DEV_TESTS` | Test framework patterns, fixtures, assertions |
| `DEV_BUILD` | Build system, commands, scripts |
| `DEV_PATTERNS` | High-level architecture patterns |

### Standard Memory Format

Each DEV_* memory should include:
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

## Phase 5: Integration

### Update Navigation Index

Add to `_INDEX`:
```markdown
## Development Standards

**Entry Point**: `REF_DEV_STANDARDS`

| Standard | Memory |
|----------|--------|
| PHP | `DEV_PHP` |
| JavaScript | `DEV_JAVASCRIPT` |
| [etc.] | [etc.] |
```

## Checklist

- [ ] Swarm initialized with 8-10 specialized agents
- [ ] Config files analyzed (PHP, JS, SCSS, templates, tests)
- [ ] Code samples examined for patterns
- [ ] `REF_DEV_STANDARDS` created as index entry point
- [ ] Individual `DEV_*` memories created (~100-120 lines each)
- [ ] `_INDEX` updated with Development Standards section
- [ ] WM updated with completion status

## Output Structure

```
REF_DEV_STANDARDS (entry point, ~50 lines)
├── DEV_PHP (~100 lines)
├── DEV_JAVASCRIPT (~100 lines)
├── DEV_SCSS (~100 lines)
├── DEV_[TEMPLATE_ENGINE] (~100 lines)
├── DEV_TESTS (~100 lines)
├── DEV_BUILD (~100 lines)
└── DEV_PATTERNS (~100 lines)
```
