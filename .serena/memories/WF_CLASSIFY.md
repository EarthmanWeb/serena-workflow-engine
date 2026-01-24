# WF_CLASSIFY - Analyze Request

> **On step WF_CLASSIFY**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## Execute These Steps

1. **Is the request clear?**
   - No -> go to WF_CLARIFY
   - Yes -> continue

2. **Assess task complexity:**

   ### Research Tasks (Skill-Based)
   - Questions about how code works
   - Exploring patterns or architecture
   - Finding files or symbols
   - No code changes needed
   -> **Invoke `/research` skill** (see Skill Invocation below)

   ### Debugging Tasks (Skill-Based)
   - Tests failing on one environment but passing on another
   - Behavior differences between environments
   - Test-driven debugging needed
   -> **Invoke `/debug-tdd` skill** (see Skill Invocation below)

   ### Simple Tasks (Single Agent)
   - Bug fix in one file
   - Small code change
   - Documentation update
   - Single function modification
   -> **WF_DETECT_REQ**

   ### Medium Tasks (Architecture Required)

   **⚠️ MANDATORY: Development Standards**

   **For tasks involving code changes**, read dev standards and any subsections relevant to the task:

   ```
   mcp__serena__read_memory("REF_DEV_STANDARDS")
   ```

   **Skip only if:** Pure research/investigation with no code output.

   **⚠️ MANDATORY RESEARCH BEFORE ROUTING:**
   ```
   mcp__serena__read_memory("_INDEX")  # Full navigation hub
   ```
   - Read ALL relevant: `INDEX_*`, `ARCH_*`, `SYS_*`, `DOM_*`, `REF_*`, `SPEC_*`
   - Check skills: `/research`, `/arch-review`, test skills for helpers
   - Use `mcp__serena__find_symbol()` to verify existing implementations
   
   **NO IMAGINATION. NO INFERENCE. NO GUESSING. EVERYTHING IS DOCUMENTED.**
   - New feature spanning 2-5 files
   - Refactoring existing code structure
   - Multi-layer design changes
   -> **WF_PLAN_ARCHITECTURE**

   ### Large Tasks (Swarm Orchestration Required)

   **⚠️ MANDATORY RESEARCH BEFORE ROUTING:**
   ```
   mcp__serena__read_memory("_INDEX")  # Full navigation hub
   ```
   - Read ALL relevant: `INDEX_*`, `ARCH_*`, `SYS_*`, `DOM_*`, `REF_*`, `SPEC_*`
   - Check skills: `/research`, `/arch-review`, test skills for helpers
   - Use `mcp__serena__find_symbol()` to verify existing implementations
   
   **NO IMAGINATION. NO INFERENCE. NO GUESSING. EVERYTHING IS DOCUMENTED.**
   Use swarms when ANY of these apply:
   - **Scale**: 6+ files affected OR 3+ architectural layers
   - **Parallel Work**: Independent subtasks that can run concurrently
   - **Research-Heavy**: Requires analyzing multiple areas simultaneously
   - **Complexity**: Multi-domain coordination needed
   - **Time-Sensitive**: Needs parallel execution for efficiency

   **Swarm indicators:**
   - "analyze the entire codebase"
   - "refactor across all modules"
   - "research and implement"
   - "comprehensive audit/review"
   - "multi-component feature"
   -> **WF_SWARM_ORCHESTRATE**

3. **Identify affected area(s):**

   **⚠️ MULTI-FEATURE DETECTION:**
   
   Requests may span multiple features. Before loading feature memories:
   
   a. **Scan request for feature indicators:**
      - Explicit feature names (e.g., "blocks and context providers")
      - File paths spanning multiple feature directories
      - Cross-cutting concerns (e.g., "theme templates that use blocks")
      - Domain terminology from multiple features
   
   b. **Detect all related features:**
      ```
      mcp__serena__read_memory("INDEX_FEATURES")   # Get feature registry
      ```
      
      For EACH detected feature key:
      ```
      mcp__serena__read_memory("FEATURE_[KEY]")    # Load feature config
      ```
   
   c. **Load ALL relevant memories for EACH feature:**
      | Memory Type | Purpose |
      |-------------|---------|
      | `FEATURE_[KEY]` | Feature scope and config |
      | `ARCH_[KEY]` or shared `ARCH_*` | Architecture patterns |
      | `INDEX_[KEY]_*` | File/symbol indexes |
      | `DOM_[KEY]` | Domain-specific context |
      | `SYS_[KEY]` | System-level context |
   
   d. **Update WORKING_MEMORY with all features:**
      ```markdown
      ## Affected Features
      - **Primary**: [KEY1] - [reason]
      - **Secondary**: [KEY2] - [reason]
      - **Related**: [KEY3] - [reason]
      ```
   
   - Check each feature's Domains (DOM_*) for domain-specific context
   - Check each feature's Systems (SYS_*) for system-level context
   - Check shared References (REF_*) for patterns and standards (codebase-wide)
   
   **Single vs Multi-Feature Routing:**
   | Detected Features | Routing Consideration |
   |-------------------|----------------------|
   | 1 feature | Standard routing applies |
   | 2-3 features | Consider WF_PLAN_ARCHITECTURE for coordination |
   | 4+ features | Likely WF_SWARM_ORCHESTRATE territory |

4. **⚠️ MANDATORY: _INDEX for Unknown Features**

   **If ALL of these conditions are true:**
   - Feature is unknown/unregistered (no FEATURE_[KEY] exists)
   - Task requires codebase knowledge (investigation, research, codebase analysis)
   
   **THEN you MUST read _INDEX before proceeding:**
   ```
   mcp__serena__read_memory("_INDEX")
   ```
   
   **This applies to:**
   - Investigation tasks ("where is X handled?", "how does Y work?")
   - Codebase exploration ("find all instances of...", "analyze...")
   - Research tasks requiring code understanding
   - Any task where you need to navigate unfamiliar code
   
   **Skip _INDEX only if:**
   - Feature is already known and loaded
   - Task is purely documentation/non-code
   - User explicitly provides all file paths needed

---

## Swarm Type Selection Guide

| Task Type | Recommended Swarm | Topology |
|-----------|-------------------|----------|
| Codebase analysis | Claude-Flow | mesh |
| Feature implementation | Claude-Flow | hierarchical |
| Research + implement | RUV-Swarm DAA | mesh |
| Pattern discovery | RUV-Swarm + neural | adaptive |
| Distributed refactoring | Hive-Mind | hierarchical |
| Consensus-required tasks | Hive-Mind | mesh |

**Read `REF_SWARM_PATTERNS` for detailed swarm usage patterns.**

---

## Skill Invocation Protocol

When routing to a workflow-aware skill (e.g., `/research`):

### 1. Set Workflow Context in WORKING_MEMORY

Update the `## Workflow Context` section:

```markdown
## Workflow Context
- **Calling Step**: WF_CLASSIFY
- **Feature Key**: [from INDEX_FEATURES or detected]
- **Session ID**: [from WORKING_MEMORY filename]
- **Return Step**: WF_DETECT_REQ
- **Invocation Mode**: workflow
```

### 2. Inform User

```
> Routing to /research skill for exploration. Will return to WF_DETECT_REQ on completion.
```

### 3. Skill Executes

The skill will:
1. Detect workflow context
2. Execute its task
3. Write `## Skill Return` section
4. Output return signal
5. Read and follow return step

### 4. Handle Skill Return

After skill completes, check `## Skill Return` in WORKING_MEMORY:

| Status | Action |
|--------|--------|
| `success` / `success_with_findings` | Continue to `return_step` |
| `needs_clarification` | Go to `WF_CLARIFY` |
| `blocked` | Go to `WF_CLARIFY` |
| `escalate_complexity` | Go to `WF_SWARM_ORCHESTRATE` |

See `REF_SKILL_PROTOCOLS` for full specification.


---

## MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** Before responding to user:

| Condition | MUST Read Next |
|-----------|----------------|
| Request unclear | `WF_CLARIFY` |
| Test debugging needed | `WF_DEBUG_TDD` |
| Large task (swarm needed) | `WF_SWARM_ORCHESTRATE` |
| Needs architecture | `WF_PLAN_ARCHITECTURE` |
| Simple change | `WF_DETECT_REQ` |

1. Determine which condition applies
2. Read that WF_* memory NOW
3. Report the new step to user

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

## ⚠️ MANDATORY: WORKING_MEMORY UPDATE

**Before transitioning to another state, you MUST:**
1. Update `## Progress` with completed steps
2. Update `**Files:**` with new files edited
3. Verify `## Workflow Context` is current

**SKIPPING WORKING_MEMORY UPDATE = WORKFLOW VIOLATION**

The hooks will BLOCK your next action if WORKING_MEMORY is stale.

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
