---
name: swe-feature-onboard
version: 2.1.0
description: Feature onboarding wizard with optional quick mode
workflow:
  aware: true
  callable_from:
    - WF_ONBOARD
    - WF_START
  default_return: WF_START
  supports_standalone: true
  auto_transition: true
args:
  - name: key
    description: Feature key (optional, will prompt if not provided)
  - name: quick
    description: Skip swarm analysis, minimal memory creation
    type: boolean
    default: false
---

## ⚠️ WORKFLOW INITIALIZATION

**If starting a new session**, first read workflow initialization:
```
mcp__plugin_swe_serena__read_memory("WF_INIT")
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

| Aspect | Quick Mode | Full Mode |
|--------|------------|-----------|
| Time | ~30 sec | 2-5 min |
| Swarm analysis | No | Optional (10 agents) |
| DOM_* memories | No | Yes (if domains found) |
| SYS_* memories | No | Yes (if systems found) |
| Layer detection | Basic | Detailed |
| Best for | Small features, prototyping | Large codebases |

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
          label: "Full DAA Swarm (Recommended)",
          description: "10 agents analyze in parallel, creates DOM_*/SYS_* memories (2-5 min)"
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

### If "Full DAA Swarm" selected:

```javascript
mcp__ruv-swarm__daa_init({ enableLearning: true })

mcp__ruv-swarm__task_orchestrate({
  task: "Analyze feature architecture",
  agents: [
    "config-analyzer",    // Parse config files
    "architecture-mapper", // Detect layers
    "pattern-detector",   // Find conventions
    "domain-extractor",   // Extract domains
    "system-finder",      // Identify systems
    "test-analyzer",      // Test patterns
    "import-tracer",      // Dependency graph
    "convention-learner", // Style detection
    "file-indexer",       // File inventory
    "synthesizer"         // Compile results
  ],
  context: { featureKey: "[KEY]", rootPath: "[PATH]" }
})
```

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

| Property | Value |
|----------|-------|
| **Name** | [Feature Name] |
| **Key** | [KEY] |
| **Type** | [type] |
| **Language** | [language] |
| **Framework** | [framework or "none"] |

## Scope Definition

### Primary Directories

| Directory | Purpose |
|-----------|---------|
| [dir] | [purpose] |

## Architecture Layers

[ASCII diagram or table of layers]

## Key Files

| File | Purpose |
|------|---------|
| [file] | [purpose] |

## Related Memories

| Memory | Content |
|--------|---------|
| DOM_[KEY]_* | Domain behaviors |
| SYS_[KEY]_* | System references |
| INDEX_[KEY]_* | Indexes |

## Testing

| Suite | File | Focus |
|-------|------|-------|
| [suite] | [file] | [focus] |
```

### Create via Serena:

```javascript
mcp__plugin_swe_serena__write_memory("FEATURE_[KEY]", "<content>")
```

### Additional memories (full mode only):

If domains detected:
```javascript
mcp__plugin_swe_serena__write_memory("DOM_[KEY]_[DOMAIN]", "<content>")
```

If systems detected:
```javascript
mcp__plugin_swe_serena__write_memory("SYS_[KEY]_[SYSTEM]", "<content>")
```

---

## Stage 6: Index Update

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
- **Memories Created**: FEATURE_[KEY], [DOM_*, SYS_* if applicable]
- **Next Step Hint**: WF_START
```

---

## Exit

```
> **Skill /swe-feature-onboard complete** - Feature [KEY] registered
```

---

## Troubleshooting

### Swarm MCP unavailable
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
