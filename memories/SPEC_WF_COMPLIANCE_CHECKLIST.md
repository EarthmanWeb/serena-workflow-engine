# SPEC_WF_COMPLIANCE_CHECKLIST - Workflow Compliance Checklist Integration

## Problem

The workflow loads project-specific memories (DEV_*, DOM_*, SYS_*) but never instructs the agent to **extract actionable rules from them and write them down**. The agent is trusted to internalize and apply rules from potentially dozens of loaded memories — a pattern that fails silently when rules are missed.

Specifically:

1. **DEV_* memories are never explicitly loaded.** `FEATURE_DEV_STANDARDS` is loaded as an index, but no WF_ step says "follow the links to `DEV_PHP`, `DEV_JAVASCRIPT`, etc." The actual coding standards are orphaned from the workflow.
2. **WF_ARCH_REVIEW's compliance check is generic.** Three abstract questions ("Which layer owns this?") with no prompt to derive project-specific checks from loaded memories.
3. **WF_EXECUTE has no new-file-creation guidance.** Creating files requires naming conventions, boilerplate, and registration — all documented in DEV_* and DOM_* memories — but WF_EXECUTE doesn't flag this.
4. **WF_VERIFY checks architecture but not integration completeness.** New components can be correctly coded but never wired in (not enqueued, not registered, not discoverable).

## Solution

Add a **"Derive Project Compliance Checklist"** step to WF_ARCH_REVIEW that:

1. Forces the agent to read the specific `DEV_*` memories for affected languages/layers
2. Extracts concrete, checkable rules from DEV_*, DOM_*, SYS_* memories
3. Writes them as a `## Compliance Checklist` in WM
4. This checklist is then referenced at WF_EXECUTE (during implementation) and verified at WF_VERIFY (during review)

## Changes Made

### WF_ARCH_REVIEW

**Added Step 2b: Load Development Standards for Affected Languages/Layers**

- Reads `FEATURE_DEV_STANDARDS` (the index)
- Follows links to specific `DEV_*` memories based on which languages the task touches
- Provides a lookup table: PHP → `DEV_PHP`, JS → `DEV_JAVASCRIPT`, Blade → `DEV_BLADEONE`, etc.

**Added Step 2c: Derive Project Compliance Checklist**

- Instructions to scan loaded DEV_*, DOM_*, SYS_*, FEATURE_[KEY] memories
- Extract concrete rules relevant to THIS task
- Write as a checkable list in WM under `## Compliance Checklist`
- Includes an example showing what a good checklist looks like

**Updated Step 3: Design With Explicit File Paths**

- Added "naming convention source from DEV_*" for new files
- Added "Integration points" as a required design element

**Updated Step 4: Architecture Compliance Check**

- Generic questions preserved as baseline
- Added "verify compliance checklist is consistent with design"
- Added "Project-Specific Violations" to STOP CONDITIONS

### WF_EXECUTE

**Added "New File Creation" subsection under Rules**

- 4-step checklist: naming, boilerplate, registration, compliance verification
- Calls out that forgotten registration is the #1 post-implementation defect

**Added "Compliance Checklist Reference" subsection**

- Points to WM's `## Compliance Checklist` from WF_ARCH_REVIEW
- Instructs to consult during implementation, not just defer to WF_VERIFY

### WF_VERIFY

**Restructured Step 2 into three substeps:**

- **2a. Generic Layer Verification** — preserved original 3 questions as baseline
- **2b. Project Compliance Checklist Verification** — reads checklist from WM, verifies each item
- **2c. Integration Completeness Check** — new checklist for wiring: enqueued? registered? discoverable? instantiated?

### WF_CLASSIFY

**Updated Step 4d: Load Supporting Memories**

- Added instruction: "Read the Related Memories / Domains / Systems table inside each FEATURE_[KEY]"
- Changed guidance from "load relevant" (vague) to "follow the links in FEATURE_[KEY]" (explicit)
- Added "How to Find" column to the memory type table

### WF_ARCH_REVIEW Step 1 (prior change)

- Added `read_memory("arch/ARCH_INDEX")` to Step 1, aligning with ARCH_SWE dependency table

## Data Flow

```
WF_CLASSIFY
  └→ Loads FEATURE_[KEY] → reads Related Memories table → loads DOM_*, SYS_*

WF_ARCH_REVIEW
  ├→ Step 2b: Loads DEV_* for affected languages
  ├→ Step 2c: Extracts rules → writes ## Compliance Checklist to WM
  └→ Step 4: Verifies design against checklist

WF_EXECUTE
  └→ Consults WM ## Compliance Checklist during implementation
  └→ New file creation: checks DEV_* naming, boilerplate, registration

WF_VERIFY
  ├→ Step 2b: Re-reads WM ## Compliance Checklist, verifies each item
  └→ Step 2c: Checks integration completeness (enqueued, registered, discoverable)
```

## What This Does NOT Change

- No new workflow states added
- No new memory files required
- No changes to WM format (the checklist is a standard markdown section)
- No changes to state machine transitions
- Generic compliance questions preserved as fallback (for operational tasks that skip arch review)
- SPEC fast-path in WF_ARCH_REVIEW unchanged (specs already contain pre-approved architecture)
