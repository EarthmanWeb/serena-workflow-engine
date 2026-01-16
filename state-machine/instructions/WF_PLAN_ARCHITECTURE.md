# WF_PLAN_ARCHITECTURE - Design Phase

> **On step WF_PLAN_ARCHITECTURE**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## When To Use

- New feature spanning multiple files
- Refactoring existing code structure
- Adding new components that span architectural layers
- Changing data flow between system components

## Execute These Steps

1. **Get feature configuration:**
   ```
   mcp__serena__read_memory("INDEX_FEATURES")   # Get active feature
   mcp__serena__read_memory("FEATURE_[KEY]")    # Get architecture, layers, memories
   ```

2. **Read relevant specification (if exists):**
   ```
   mcp__serena__read_memory("SPEC_[NAME]")      # Check for existing specs
   ```

3. **Read relevant system context from FEATURE_[KEY]:**
   ```
   mcp__serena__read_memory("SYS_[SYSTEM]")     # System documentation (feature-specific)
   ```

4. **For EACH layer in design, read its rules:**
   ```
   mcp__serena__read_memory("REF_[TOPIC]")      # Reference patterns (codebase-shared)
   mcp__serena__read_memory("REF_DEV_STANDARDS") # Coding standards (codebase-shared)
   mcp__serena__read_memory("DOM_[DOMAIN]")     # Domain-specific context (feature-specific)
   ```
   Example: New component for Domain X -> read SYS_[SYSTEM], DOM_[DOMAIN], REF_[PATTERN]

5. **Design with explicit file paths** - define which files/components affected

6. **Assess if swarm is needed:**
   - 6+ files OR 3+ layers → Consider swarm orchestration
   - Parallel independent subtasks → Swarm beneficial
   - Research + implementation → RUV-Swarm DAA recommended
   - Consensus needed → Hive-Mind recommended

7. **Present to user** with:
   - Files to be modified table
   - Key architectural constraints applied
   - **Swarm recommendation** (if applicable): topology, agent types, parallelization strategy

## MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** Before responding to user:

| Condition | MUST Read Next |
|-----------|----------------|
| User approves design (simple) | `WF_DETECT_REQ` |
| User approves design (swarm needed) | `WF_SWARM_ORCHESTRATE` |
| User rejects/modifies | `WF_CLARIFY` |

1. Wait for user approval
2. Read that WF_* memory NOW
3. Report the new step to user

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

WORKING_MEMORY: Update if task state changed (see `REF_WORKING_MEMORY`)

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
