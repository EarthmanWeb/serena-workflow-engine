# WF_ARCH_REVIEW - Architecture Compliance Check

> **On step WF_ARCH_REVIEW**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## Execute These Steps

1. **Get feature architecture:**
   ```
   mcp__plugin_swe_serena__read_memory("INDEX_FEATURES")   # Get active feature
   mcp__plugin_swe_serena__read_memory("FEATURE_[KEY]")    # Get feature config with layers
   ```

2. **Identify layers touched** by proposed change:
   - Check which architectural layers from FEATURE_[KEY] are affected

3. **For each layer, read its documentation:**
   ```
   # Read relevant SYS_* (feature-specific) and REF_* (codebase-shared) memories
   mcp__plugin_swe_serena__read_memory("SYS_[SYSTEM]")     # System documentation (feature-specific)
   mcp__plugin_swe_serena__read_memory("REF_[TOPIC]")      # Reference patterns (codebase-shared)
   mcp__plugin_swe_serena__read_memory("REF_DEV_STANDARDS") # Coding standards (codebase-shared)
   ```

4. **Answer these questions:**
   - [ ] Which layer OWNS this logic?
   - [ ] Am I putting logic in the correct layer?
   - [ ] Am I following the project's documented data flow pattern?

## STOP CONDITIONS

**If any of these are true, REDESIGN before proceeding:**

### General Layer Violations
- Business logic in presentation layer (views/templates should only display data)
- Presentation layer calling data layer directly (should go through business logic)
- Data access layer containing business rules (should be in service/business layer)
- Cross-cutting concerns scattered instead of centralized

### Presentation Layer (check views/templates)
- View contains complex logic beyond simple conditionals
- View has data transformations that belong in business layer
- View imports services/functions directly instead of using provided context
- View is doing more than display/formatting

**Read REF_* memories (codebase-shared) for correct patterns.**

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| Approach is compliant | `WF_EXECUTE` |
| Needs redesign | Loop back, fix approach |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

## ⚠️ MANDATORY: WM UPDATE

**Before transitioning to another state, you MUST:**
1. Update `## Progress` with review outcomes
2. Update `**Files:**` with files reviewed
3. Verify `## Workflow Context` is current

**SKIPPING WM UPDATE = WORKFLOW VIOLATION**

The hooks will BLOCK your next action if WM is stale.

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
