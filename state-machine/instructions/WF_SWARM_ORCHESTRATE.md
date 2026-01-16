# WF_SWARM_ORCHESTRATE - Multi-Agent Swarm Coordination

> **🐝 On step WF_SWARM_ORCHESTRATE**

⬆️ OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

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

| System | When to Use | MCP Tools |
|--------|-------------|-----------|
| **Claude-Flow** | General orchestration, parallel tasks | `mcp__claude-flow__*` |
| **RUV-Swarm** | Learning/adaptation needed, DAA patterns | `mcp__ruv-swarm__*` |
| **Hive-Mind** | Consensus, collective intelligence, distributed memory | `/hive-mind-init`, `/hive-mind-spawn` |

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
mcp__claude-flow__agent_spawn({ type: "researcher", name: "agent-1", capabilities: [...] })
mcp__claude-flow__agent_spawn({ type: "coder", name: "agent-2", capabilities: [...] })
mcp__claude-flow__agent_spawn({ type: "tester", name: "agent-3", capabilities: [...] })

// Step 3: Orchestrate tasks
mcp__claude-flow__task_orchestrate({ task: "...", strategy: "parallel", priority: "high" })

// Step 4: Store coordination state
mcp__claude-flow__memory_usage({ action: "store", namespace: "swarm", key: "state", value: "..." })
```

### Pattern B: RUV-Swarm DAA (For learning/adaptation)

```javascript
// Step 1: Initialize with DAA
mcp__ruv-swarm__swarm_init({ topology: "mesh", strategy: "specialized" })
mcp__ruv-swarm__daa_init({ enableLearning: true, enableCoordination: true })

// Step 2: Create autonomous agents
mcp__ruv-swarm__daa_agent_create({ id: "agent-1", cognitivePattern: "adaptive", enableMemory: true })
mcp__ruv-swarm__daa_agent_create({ id: "agent-2", cognitivePattern: "critical", enableMemory: true })

// Step 3: Orchestrate with adaptation
mcp__ruv-swarm__task_orchestrate({ task: "...", strategy: "adaptive" })

// Step 4: Share knowledge between agents
mcp__ruv-swarm__daa_knowledge_share({ sourceAgentId: "agent-1", targetAgentIds: ["agent-2"] })
```

### Pattern C: Hive-Mind (For consensus/collective intelligence)

```javascript
// Step 1: Initialize hive
/hive-mind-init  // Skill invocation

// Step 2: Spawn hive agents
/hive-mind-spawn { type: "worker", count: 3 }

// Step 3: Coordinate via consensus
/hive-mind-consensus { proposal: "...", agents: [...] }

// Step 4: Access collective memory
/hive-mind-memory { action: "store", key: "...", value: "..." }
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

📋 **WORKING_MEMORY:** Update with swarm state (agent IDs, topology, task assignments)

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
