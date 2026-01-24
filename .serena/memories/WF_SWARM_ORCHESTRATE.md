# WF_SWARM_ORCHESTRATE - Multi-Agent Swarm Coordination

> **🐝 On step WF_SWARM_ORCHESTRATE**

⬆️ OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## ⚠️ CRITICAL: EXPLICIT TOOL SELECTION RULE

**When user explicitly requests a specific swarm system, USE THOSE EXACT MCP TOOLS.**

| User Says | YOU MUST USE | NOT |
|-----------|--------------|-----|
| "launch ruv-swarm" / "ruv swarm" | `mcp__plugin_serena-workflow-engine_ruv-swarm__*` tools | Task/Explore agents |
| "launch claude-flow swarm" | `mcp__claude-flow__*` tools | Task/Explore agents |
| "use hive-mind" | `mcp__claude-flow__hive-mind_*` tools | Task/Explore agents |

**FAILURE MODE TO AVOID:**
```
❌ User: "Launch ruv-swarm to detect features"
❌ Agent: [Uses Task({ subagent_type: "Explore" }) instead]
```

**CORRECT BEHAVIOR:**
```
✅ User: "Launch ruv-swarm to detect features"
✅ Agent: [Uses mcp__plugin_serena-workflow-engine_ruv-swarm__swarm_init(), etc.]
```

**Why this matters:** MCP swarm tools provide coordination metadata, learning, and state persistence. Task agents are for file work AFTER swarm setup. Substituting one for the other breaks the coordination model.

---

## When To Use

This workflow applies when:
- Task affects 6+ files OR 3+ architectural layers
- Independent subtasks can run in parallel
- Research and implementation need to happen concurrently
- Multi-domain coordination is required
- Consensus or collective intelligence is needed

**Read `REF_SWARM_PATTERNS` for detailed MCP tool reference.**

---

## ⛔ MANDATORY PRE-SWARM RESEARCH

**BEFORE planning ANY swarm, you MUST exhaustively research what exists.**

```
mcp__serena__read_memory("_INDEX")           # Navigation hub - find all relevant memories
```

**Then read ALL relevant memories for affected areas:**
- `INDEX_*` - Classes, functions, templates, hooks inventories
- `ARCH_*` - Architecture documentation  
- `SYS_*` - System documentation
- `DOM_*` - Domain-specific context
- `REF_*` - Reference patterns, standards, test helpers
- `SPEC_*` - Existing specifications

**Also check relevant skills:**
- `/research` - Deep codebase exploration
- `/arch-review` - Architecture compliance
- `/verify` - Standards verification
- Test skills for test patterns and helpers

**NO IMAGINATION. NO INFERENCE. NO GUESSING.**
- Every existing class, function, helper, and pattern is documented
- Auth/login helpers, test content helpers, all documented in `REF_TESTS_*`
- All architecture decisions are in `ARCH_*` memories
- If you cannot find documentation for something, ASK before assuming

**DRY/YAGNI ENFORCEMENT:**
- Search for existing implementations before creating new ones
- Use `mcp__serena__find_symbol()` to verify nothing similar exists
- Each swarm agent MUST be instructed to research before implementing

**CRITICAL FOR SWARM AGENTS:**
When spawning agents, include in their prompts:
> "Research existing patterns in INDEX_*, ARCH_*, SYS_* memories before implementing. DO NOT create anything that already exists."

---

## Execute These Steps

### Step 1: Select Swarm System

| System | When to Use | MCP Tool Prefix |
|--------|-------------|-----------------|
| **Claude-Flow** | General orchestration, parallel tasks | `mcp__claude-flow__*` |
| **RUV-Swarm** | Learning/adaptation needed, DAA patterns | `mcp__plugin_serena-workflow-engine_ruv-swarm__*` |
| **Hive-Mind** | Consensus, collective intelligence, distributed memory | `mcp__claude-flow__hive-mind_*` |

### Step 2: Select Topology

| Topology | Structure | Best For |
|----------|-----------|----------|
| **mesh** | All agents peer-to-peer | Collaborative analysis, exploration |
| **hierarchical** | Tree with coordinator | Complex projects, orchestrated changes |
| **star** | Central hub + workers | Quick parallel tasks |
| **ring** | Circular chain | Sequential processing pipelines |

### Step 3: Plan Agent Roles

Common agent types:
```
researcher    - Information gathering, pattern detection
analyst       - Code analysis, data processing  
coder         - Code generation, implementation
tester        - Validation, verification
coordinator   - Orchestration, synthesis
optimizer     - Performance analysis
reviewer      - Quality assurance, security audit
```

---

## Swarm Initialization Patterns

### Pattern A: Claude-Flow (Recommended for most tasks)

```javascript
// Step 1: Initialize swarm
mcp__claude-flow__swarm_init({ topology: "mesh", maxAgents: 5 })

// Step 2: Spawn agents IN ONE MESSAGE (parallel)
mcp__claude-flow__agent_spawn({ agentType: "researcher", agentId: "agent-1" })
mcp__claude-flow__agent_spawn({ agentType: "coder", agentId: "agent-2" })
mcp__claude-flow__agent_spawn({ agentType: "tester", agentId: "agent-3" })

// Step 3: Orchestrate tasks
mcp__claude-flow__task_orchestrate({ task: "...", strategy: "parallel", priority: "high" })

// Step 4: Store coordination state
mcp__claude-flow__memory_store({ key: "swarm:state", value: { status: "agents_spawned", topology: "mesh" } })
```

### Pattern B: RUV-Swarm DAA (For learning/adaptation)

```javascript
// Step 1: Initialize with DAA
mcp__plugin_serena-workflow-engine_ruv-swarm__swarm_init({ topology: "mesh", strategy: "specialized" })
mcp__plugin_serena-workflow-engine_ruv-swarm__daa_init({ enableLearning: true, enableCoordination: true })

// Step 2: Create autonomous agents
mcp__plugin_serena-workflow-engine_ruv-swarm__daa_agent_create({ id: "agent-1", cognitivePattern: "adaptive", enableMemory: true })
mcp__plugin_serena-workflow-engine_ruv-swarm__daa_agent_create({ id: "agent-2", cognitivePattern: "critical", enableMemory: true })

// Step 3: Orchestrate with adaptation
mcp__plugin_serena-workflow-engine_ruv-swarm__task_orchestrate({ task: "...", strategy: "adaptive" })

// Step 4: Share knowledge between agents
mcp__plugin_serena-workflow-engine_ruv-swarm__daa_knowledge_share({ sourceAgentId: "agent-1", targetAgentIds: ["agent-2"] })
```

### Pattern C: Hive-Mind (For consensus/collective intelligence)

```javascript
// Step 1: Initialize hive
mcp__claude-flow__hive-mind_init({ topology: "mesh" })

// Step 2: Spawn hive workers (combined spawn + join)
mcp__claude-flow__hive-mind_spawn({ count: 3, role: "worker", agentType: "worker" })

// Step 3: Coordinate via consensus
mcp__claude-flow__hive-mind_consensus({ action: "propose", type: "decision", value: "..." })

// Step 4: Access collective memory
mcp__claude-flow__hive-mind_memory({ action: "set", key: "...", value: "..." })

// Step 5: Broadcast to all workers
mcp__claude-flow__hive-mind_broadcast({ message: "...", priority: "normal" })
```

---

## ⛔ NEVER RUN INIT COMMANDS

**NEVER run `npx claude-flow init`, `npx ruv-swarm init`, or similar initialization CLI commands.**

These commands modify repository files by:
- Creating configuration files in the project root
- Adding boilerplate that conflicts with existing code
- Modifying package.json or other project files

**Use MCP tools directly instead** - they coordinate in-memory without touching repo files:
```javascript
// ✅ CORRECT: MCP tool (no repo changes)
mcp__claude-flow__swarm_init({ topology: "mesh" })

// ❌ WRONG: CLI init command (modifies repo files)
npx claude-flow init
```

---

## CRITICAL: Execution Rules

### DO:
1. **Initialize swarm FIRST** before spawning agents
2. **Spawn ALL agents in ONE message** (parallel execution)
3. **Use Claude Code Task tool** for actual file work
4. **Store coordination state** to memory
5. **Monitor with non-blocking calls** during work
6. **Collect results with blocking calls** at end

### DON'T:
1. Spawn swarm then revert to single-agent work
2. Block on first agent before spawning others
3. Skip memory persistence for swarm state
4. Forget to track agent IDs for result collection
5. Mix swarm systems without clear handoff

---

## Agent Execution via Task Tool

**MCP coordinates, Claude Code Task tool executes:**

```javascript
// After MCP swarm setup, launch ACTUAL work agents
Task({ 
  subagent_type: "Explore", 
  run_in_background: true, 
  prompt: "Research module A patterns..." 
})
Task({ 
  subagent_type: "general-purpose", 
  run_in_background: true, 
  prompt: "Implement feature X..." 
})

// Monitor progress
mcp__claude-flow__swarm_status({})

// Collect results
TaskOutput({ task_id: "...", block: true })
```

---

## Coordination Hooks Protocol

### BEFORE Work:
```bash
npx claude-flow@alpha hooks pre-task --description "[task]"
npx claude-flow@alpha hooks session-restore --session-id "swarm-[id]"
```

### DURING Work:
```bash
npx claude-flow@alpha hooks post-edit --file "[file]" --memory-key "swarm/[agent]/[step]"
npx claude-flow@alpha hooks notify --message "[status]"
```

### AFTER Work:
```bash
npx claude-flow@alpha hooks post-task --task-id "[task]"
npx claude-flow@alpha hooks session-end --export-metrics true
```

---

## MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** Before responding to user:

| Condition | MUST Read Next |
|-----------|----------------|
| User approves swarm plan | `WF_EXECUTE` (with swarm active) |
| User wants simpler approach | `WF_PLAN_ARCHITECTURE` |
| Need clarification | `WF_CLARIFY` |
| Swarm work complete | `WF_VERIFY` |

1. Present swarm plan to user for approval
2. After approval, read next WF_* memory
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
