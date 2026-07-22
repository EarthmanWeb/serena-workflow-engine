---
name: swe-feature-onboard
version: 2.1.0
description: Feature onboarding wizard with optional quick mode
workflow:
  aware: true
  callable_from:
    - WF_ONBOARD
    - WF_CLASSIFY
  default_return: WF_CLASSIFY
  supports_standalone: true
  auto_transition: true
args:
  - name: key
    description: Feature key (optional, will prompt if not provided)
  - name: quick
    description: Skip parallel-subagent analysis, minimal memory creation
    type: boolean
    default: false
---

## ⚠️ WORKFLOW INITIALIZATION

**If starting a new session**, first read workflow initialization:

```
mcp__plugin_swe_serena__read_memory("wf/WF_INIT")
```

Follow WF_INIT instructions before executing this skill.

---

# /swe-feature-onboard [KEY] [--quick]

Interactive wizard for registering features in the workflow system.

## Usage

```bash
/swe-feature-onboard              # Full interactive wizard
/swe-feature-onboard MYAPP        # Start with key pre-filled
/swe-feature-onboard MYAPP --quick # Quick mode (30 sec, minimal)
```

## Quick Mode vs Full Mode

| Aspect          | Quick Mode                  | Full Mode              |
| --------------- | --------------------------- | ---------------------- |
| Time            | ~30 sec                     | 2-5 min                |
| Parallel subagents | No                       | Optional (10 subagents)|
| DOM_* memories  | No                          | Yes (if domains found) |
| SYS_* memories  | No                          | Yes (if systems found) |
| Layer detection | Basic                       | Detailed               |
| Best for        | Small features, prototyping | Large codebases        |

---

## Stage 1: Basic Info

**Use AskUserQuestion for feature information (skip if provided via args):**

```javascript
AskUserQuestion({
  questions: [
    {
      question: "What is the Feature Key? (Short identifier used in memory names, e.g., BACKEND, AUTH, BLOCKS)",
      header: "Feature Key",
      options: [
        { label: "BACKEND", description: "For backend/API features" },
        { label: "FRONTEND", description: "For UI/client features" },
        { label: "AUTH", description: "For authentication features" }
      ],
      multiSelect: false
    },
    {
      question: "What type of codebase is this feature?",
      header: "Type",
      options: [
        { label: "web_app", description: "Web application" },
        { label: "wordpress_theme", description: "WordPress theme" },
        { label: "wordpress_plugin", description: "WordPress plugin" },
        { label: "api", description: "API/Backend service" }
      ],
      multiSelect: false
    }
  ]
})
```

**Then ask for paths:**

```javascript
AskUserQuestion({
  questions: [
    {
      question: "Where is the code located? (Root path for this feature)",
      header: "Root Path",
      options: [
        { label: "src/", description: "Standard source directory" },
        { label: "wp-content/themes/", description: "WordPress themes" },
        { label: "wp-content/plugins/", description: "WordPress plugins" }
      ],
      multiSelect: false
    }
  ]
})
```

**Validation:**

- Key: UPPERCASE, underscores allowed, 2-20 chars
- Path: Must exist in project

---

## Stage 2: Tech Stack

**Use AskUserQuestion for technology selection:**

```javascript
AskUserQuestion({
  questions: [
    {
      question: "What is the primary programming language?",
      header: "Language",
      options: [
        { label: "php", description: "PHP (WordPress, Laravel, etc.)" },
        { label: "typescript", description: "TypeScript/JavaScript" },
        { label: "python", description: "Python" }
      ],
      multiSelect: false
    },
    {
      question: "What framework is used (if any)?",
      header: "Framework",
      options: [
        { label: "wordpress", description: "WordPress CMS" },
        { label: "react", description: "React.js" },
        { label: "nextjs", description: "Next.js" },
        { label: "none", description: "No framework / vanilla" }
      ],
      multiSelect: false
    }
  ]
})
```

**Auto-detection:** Scan root path for:

- `package.json` → Node/TypeScript
- `composer.json` → PHP
- `Cargo.toml` → Rust
- `go.mod` → Go
- `style.css` with `Theme Name:` → WordPress theme

---

## Stage 3: Analysis Mode

**Skip in quick mode** - go directly to Stage 5.

**Use AskUserQuestion for analysis mode selection:**

```javascript
AskUserQuestion({
  questions: [
    {
      question: "How should I analyze the codebase?",
      header: "Analysis",
      options: [
        {
          label: "Parallel Subagents (Recommended)",
          description: "10 subagents analyze in parallel via the Agent tool, creates DOM_*/SYS_* memories (2-5 min)"
        },
        {
          label: "Quick Scan",
          description: "Basic directory structure and layer detection (~30 sec)"
        },
        {
          label: "Manual Configuration",
          description: "You describe the architecture, I create memories from your input"
        }
      ],
      multiSelect: false
    }
  ]
})
```

### If "Parallel Subagents" selected:

**Load the subagent guidance first:**

```javascript
mcp__plugin_swe_serena__read_memory("feature/FEATURE_SUBAGENTS")
```

This loads subagent types, model selection, and parallel-launch patterns.

Launch 10 read-only analysis subagents in ONE message via the `Agent` tool (`run_in_background: true`, `model: "haiku"` for read-only scans). Each covers one focus area; a final synthesis pass compiles their results into DOM_*/SYS_* memories. Prefix every prompt with `You are a subagent. BYPASS WF_INIT. Do NOT read CLAUDE.md workflow.`

```javascript
// Launch ALL in ONE message for parallel execution.
Agent({ description: "config-analyzer", run_in_background: true, model: "haiku",
  prompt: "You are a subagent. BYPASS WF_INIT. Parse config files for [KEY] at [PATH]..." })
Agent({ description: "architecture-mapper", run_in_background: true, model: "haiku",
  prompt: "You are a subagent. BYPASS WF_INIT. Detect architectural layers for [KEY]..." })
Agent({ description: "pattern-detector", run_in_background: true, model: "haiku",
  prompt: "You are a subagent. BYPASS WF_INIT. Find coding conventions for [KEY]..." })
Agent({ description: "domain-extractor", run_in_background: true, model: "haiku",
  prompt: "You are a subagent. BYPASS WF_INIT. Extract domain concepts for [KEY]..." })
Agent({ description: "system-finder", run_in_background: true, model: "haiku",
  prompt: "You are a subagent. BYPASS WF_INIT. Identify systems/integrations for [KEY]..." })
Agent({ description: "test-analyzer", run_in_background: true, model: "haiku",
  prompt: "You are a subagent. BYPASS WF_INIT. Analyze test patterns for [KEY]..." })
Agent({ description: "import-tracer", run_in_background: true, model: "haiku",
  prompt: "You are a subagent. BYPASS WF_INIT. Trace the dependency graph for [KEY]..." })
Agent({ description: "convention-learner", run_in_background: true, model: "haiku",
  prompt: "You are a subagent. BYPASS WF_INIT. Detect style/naming conventions for [KEY]..." })
Agent({ description: "file-indexer", run_in_background: true, model: "haiku",
  prompt: "You are a subagent. BYPASS WF_INIT. Inventory files for [KEY] at [PATH]..." })
Agent({ description: "synthesizer", run_in_background: true, model: "sonnet",
  prompt: "You are a subagent. BYPASS WF_INIT. Compile the analysis results for [KEY] into DOM_*/SYS_* memory drafts..." })
```

Collect results from the background task notifications, then synthesize into memories.

---

## Stage 4: Architecture Confirmation

**Skip in quick mode.**

Present detected architecture and confirm with AskUserQuestion:

```javascript
// First, display the detected architecture in text:
// "I detected the following architecture for [FEATURE_NAME]:
//  Layers: [table]
//  Data Flow: [diagram]
//  Dependencies: [list]"

AskUserQuestion({
  questions: [
    {
      question: "Is the detected architecture correct?",
      header: "Confirm",
      options: [
        {
          label: "Yes, correct",
          description: "Proceed with memory creation using this architecture"
        },
        {
          label: "No, needs changes",
          description: "I'll provide corrections to the architecture"
        },
        {
          label: "Start over",
          description: "Re-run analysis with different settings"
        }
      ],
      multiSelect: false
    }
  ]
})
```

If user selects "No, needs changes", gather corrections manually.

---

## Stage 5: Memory Creation

### Create FEATURE_[KEY].md

```markdown
# FEATURE_[KEY] - [Name]

## Feature Overview

| Property      | Value                 |
| ------------- | --------------------- |
| **Name**      | [Feature Name]        |
| **Key**       | [KEY]                 |
| **Type**      | [type]                |
| **Language**  | [language]            |
| **Framework** | [framework or "none"] |

## Scope Definition

### Primary Directories

| Directory | Purpose   |
| --------- | --------- |
| [dir]     | [purpose] |

## Architecture Layers

[ASCII diagram or table of layers]

## Key Files

| File   | Purpose   |
| ------ | --------- |
| [file] | [purpose] |

## Related Memories

| Memory        | Content           |
| ------------- | ----------------- |
| dom/DOM_[KEY]_*   | Domain behaviors  |
| sys/SYS_[KEY]_*   | System references |
| index/INDEX_[KEY]_* | Indexes           |

## Testing

| Suite   | File   | Focus   |
| ------- | ------ | ------- |
| [suite] | [file] | [focus] |
```

### Create via Serena:

```javascript
mcp__plugin_swe_serena__write_memory("FEATURE_[KEY]", "<content>")
```

### Additional memories (full mode only):

If domains detected:

```javascript
mcp__plugin_swe_serena__write_memory("dom/DOM_[KEY]_[DOMAIN]", "<content>")
```

If systems detected:

```javascript
mcp__plugin_swe_serena__write_memory("sys/SYS_[KEY]_[SYSTEM]", "<content>")
```

---

## Stage 5b: Gherkin Spec Setup

After creating feature memories, prompt for Gherkin BDD spec setup:

```javascript
AskUserQuestion({
  questions: [{
    question: "Should this feature use Gherkin BDD specs for test-driven development?",
    header: "Gherkin BDD",
    options: [
      {
        label: "Yes, write specs now (Recommended)",
        description: "Creates tests/specs/ directory and invokes /swe-gherkin-spec to write .feature files"
      },
      {
        label: "Yes, but later",
        description: "Sets up tests/specs/ directory, adds SPEC convention to feature memory. Write specs before implementation."
      },
      {
        label: "No, skip Gherkin",
        description: "Feature will use standard test patterns without formal BDD specs"
      }
    ],
    multiSelect: false
  }]
})
```

### If "Yes, write specs now":

1. Create the specs directory:
```bash
mkdir -p tests/specs
```

2. Invoke `/swe-gherkin-spec [KEY]` — the spec authoring skill will guide the user through writing `.feature` files.

### If "Yes, but later":

1. Create the specs directory:
```bash
mkdir -p tests/specs
```

2. Add a note to FEATURE_[KEY] memory:
```
mcp__plugin_swe_serena__edit_memory(
  "feature/FEATURE_[KEY]",
  "## Testing",
  "## Testing\n\n**Gherkin BDD:** Enabled — specs go in `tests/specs/[key]-*.feature`\nRun `/swe-gherkin-spec [KEY]` before starting implementation.\n",
  "literal"
)
```

### If "No, skip Gherkin":

Continue to Stage 6. No spec setup needed.

---

## Stage 6: Symbol Index (Related Docs)

**After creating FEATURE_[KEY] and any DOM__/SYS__ memories, generate the Related Docs table.**

Invoke the `/swe-symbol-index` skill:

```
/swe-symbol-index [KEY]
```

This will:

1. Read all linked memories listed in FEATURE_[KEY]'s Related Memories section
2. Extract heading symbols from each via `get_symbols_overview` with `depth=1`
3. Build a summary table and insert it as `## Related Docs` after Feature Overview

**Depth guidance:** Use `depth=1` for memory markdown files to capture H2+H3 headings. For code file indexes, `depth=1` on PHP/Python/TS returns classes + methods; SCSS/CSS language servers return empty — fall back to `search_for_pattern`.

**Skip if no Related Memories were created** (e.g., quick mode with no DOM__/SYS__).

---

## Stage 7: Index Update

Update INDEX_FEATURES.md:

```javascript
mcp__plugin_swe_serena__edit_memory(
  "INDEX_FEATURES",
  "## Registered Features",
  "## Registered Features\n\n| [KEY] | [Name] | [Type] | [Language] | Active |",
  "literal"
)
```

---

## Skill Return

```markdown
## Skill Return

- **Skill**: swe-feature-onboard
- **Status**: success
- **Feature Key**: [KEY]
- **Mode**: [full|quick]
- **Memories Created**: FEATURE_[KEY], [DOM__, SYS__ if applicable]
- **Next Step Hint**: WF_CLASSIFY
```

**Routing after onboarding:**

- Always → `WF_CLASSIFY` (normal entry). Parallel subagent work, if any, runs later inside `WF_EXECUTE`.

---

## Exit

```
> **Skill /swe-feature-onboard complete** - Feature [KEY] registered
```

---

## Troubleshooting

### Subagents unavailable

Fall back to quick mode or manual configuration.

### Path doesn't exist

```bash
ls -la [path]
```

Ask user to correct.

### INDEX_FEATURES.md missing

Create it first:

```javascript
mcp__plugin_swe_serena__write_memory("INDEX_FEATURES", "# INDEX_FEATURES\n\n## Registered Features\n\n| Key | Name | Type | Language | Status |\n|-----|------|------|----------|--------|\n")
```
