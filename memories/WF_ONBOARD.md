# WF_ONBOARD - New Feature Onboarding

> **On step WF_ONBOARD**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## When To Use

This workflow runs when:
- No feature is indexed in INDEX_FEATURES
- User explicitly requests feature setup
- Active feature has no FEATURE_[KEY] memory

## Memory Scope Reminder

| Prefix | Scope |
|--------|-------|
| `REF_*` | **Codebase-shared** - applies to ALL features |
| `DOM_*`, `SYS_*`, `INDEX_*`, `ARCH_*` | Feature-specific |

## Execute These Steps

### Step 1: Gather Feature Information

Ask the user:

```
I need to set up this feature in the workflow system. Please provide:

1. **Feature Name**: What should this feature be called?
2. **Feature Key**: Short identifier (e.g., "myapp", "website") - used in memory names
3. **Feature Type**: (web app, library, service, API, CMS, etc.)
4. **Primary Language**: (typescript, python, php, go, rust, etc.)
5. **Framework** (if any): (react, nextjs, django, laravel, express, etc.)
```

### Step 2: Identify Architecture

Ask about architectural layers:

```
What are the main architectural layers in this feature?

Common examples:
- **Frontend/Presentation**: Views, Templates, Components, Pages
- **Business Logic**: Services, Controllers, Handlers, UseCases
- **Data Access**: Repositories, Models, DAOs, Database
- **Infrastructure**: Config, Middleware, Utilities

Please describe your feature's layers and their typical data flow.
```

### Step 3: Identify Key Directories

Ask about important folders:

```
Which directories should I index for quick reference?

Categories to consider:
- **Source code**: Where is the main application code?
- **Tests**: Where are test files located?
- **Configuration**: Where are config files?
- **Documentation**: Where is documentation?

For each, I can create:
- ARCH_[LAYER] - Architecture documentation (feature-specific)
- INDEX_[TYPE] - File/symbol indexes (feature-specific)
- DOM_[DOMAIN] - Domain documentation (feature-specific)
```

### Step 4: Create Feature Configuration

Create the FEATURE_[KEY].md memory:

```
mcp__serena__write_memory("FEATURE_[KEY]", "<content from template>")
```

Use the template from INDEX_FEATURES.md.

### Step 5: Create Core Memories

Based on user input, create:

1. **ARCH_INDEX.md** - Feature architecture overview (feature-specific)
2. **_INDEX.md** - Feature-specific routing table

**Note:** REF_* files (like REF_DEV_STANDARDS) are codebase-shared. Only create/update them if the standards apply to the entire codebase, not just this feature.

### Step 6: Register Feature

Update INDEX_FEATURES.md:
- Add to Registered Features table
- Set as Active Feature if desired

```
mcp__serena__edit_memory("INDEX_FEATURES", "<old>", "<new>", "literal")
```

### Step 7: Initial Indexing (Optional)

Ask user if they want automatic indexing:

```
Would you like me to scan and index the codebase now?

This will create feature-specific indexes:
- INDEX_FUNCTIONS - Function inventory
- INDEX_CLASSES - Class inventory
- INDEX_FILES - File structure

This may take a few minutes for large codebases.
```

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| Feature configured | `WF_START` (restart workflow) |
| User cancelled | End conversation |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
