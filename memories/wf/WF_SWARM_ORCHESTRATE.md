# WF_SWARM_ORCHESTRATE - Multi-Agent Swarm Coordination

> **🐝 On step WF_SWARM_ORCHESTRATE**

⬆️ OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## ⚠️ CRITICAL: EXPLICIT TOOL SELECTION RULE

**When user explicitly requests a specific swarm system, USE THOSE EXACT MCP TOOLS.**

| User Says | YOU MUST USE | NOT |
|-----------|--------------|-----|
| "launch ruv-swarm" / "ruv swarm" | `mcp__plugin_swe_ruv-swarm__*` tools | Task/Explore agents |
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
✅ Agent: [Uses mcp__plugin_swe_ruv-swarm__swarm_init(), etc.]
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
mcp__plugin_swe_serena__read_memory("_INDEX")           # Navigation hub - find all relevant memories
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
- Use `mcp__plugin_swe_serena__find_symbol()` to verify nothing similar exists
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
| **RUV-Swarm** | Learning/adaptation needed, DAA patterns | `mcp__plugin_swe_ruv-swarm__*` |
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

### Pattern A: Claude-Flow V3 (Recommended for most tasks)

**⚠️ V3 API - Uses `tasks/create` for task assignment, NOT `task_orchestrate`**

Claude-Flow V3 orchestration approach:
- `swarm/init` - Initialize swarm with topology (hierarchical-mesh default)
- `agent/spawn` - Create agents
- `tasks/create` - Create tasks with `assignToAgent` or `assignToAgentType`
- `tasks/dependencies` - Manage task execution order
- `workflow/create` + `workflow/execute` - For complex multi-step workflows

**V3 Key Tools:**

| Category | Tools |
|----------|-------|
| **Swarm** | `swarm/init`, `swarm/status`, `swarm/scale` |
| **Agents** | `agent/spawn`, `agent/list`, `agent/status`, `agent/terminate` |
| **Tasks** | `tasks/create`, `tasks/assign`, `tasks/status`, `tasks/results`, `tasks/dependencies` |
| **Federation** | `broadcast`, `propose`, `vote` (consensus coordination) |

```javascript
// Step 1: Initialize swarm
mcp__claude-flow__swarm_init({ topology: "hierarchical-mesh", maxAgents: 15 })

// Step 2: Spawn agents IN ONE MESSAGE (parallel)
mcp__claude-flow__agent_spawn({ agentType: "researcher", agentId: "agent-1" })
mcp__claude-flow__agent_spawn({ agentType: "coder", agentId: "agent-2" })
mcp__claude-flow__agent_spawn({ agentType: "tester", agentId: "agent-3" })

// Step 3: Create tasks and assign to agents (parallel execution)
mcp__claude-flow__tasks_create({
  type: "analyze",
  description: "Analyze codebase patterns",
  assignToAgent: "agent-1",
  priority: 8
})
mcp__claude-flow__tasks_create({
  type: "analyze",
  description: "Review security patterns",
  assignToAgent: "agent-2",
  priority: 8
})

// Step 4: For sequential execution, add dependencies
mcp__claude-flow__tasks_dependencies({
  taskId: "task-2",
  action: "add",
  dependencies: ["task-1"]
})

// Step 5: Launch ACTUAL work via Task tool (in background)
Task({ subagent_type: "researcher", run_in_background: true, prompt: "..." })

// Step 6: Monitor status
mcp__claude-flow__swarm_status({ includeAgents: true, includeMetrics: true })
mcp__claude-flow__tasks_status({ taskId: "task-1", includeMetrics: true })

// Step 7: Collect results
mcp__claude-flow__tasks_results({ taskId: "task-1", format: "detailed" })
TaskOutput({ task_id: "...", block: true })

// Step 8: Store coordination state
mcp__claude-flow__memory_store({ key: "swarm:state", value: { status: "completed" } })
```

**For complex workflows:** Use `workflow/create` + `workflow/execute` with step definitions.

### Pattern B1: RUV-Swarm Task Orchestration (For parallel tasks)

**⚠️ CRITICAL: `task_orchestrate` ONLY works with agents from `agent_spawn`, NOT `daa_agent_create`**

```javascript
// Step 1: Initialize swarm
mcp__ruv-swarm__swarm_init({ topology: "mesh", strategy: "balanced", maxAgents: 5 })

// Step 2: Spawn swarm agents (REQUIRED before task_orchestrate)
mcp__ruv-swarm__agent_spawn({ type: "researcher", name: "researcher-1" })
mcp__ruv-swarm__agent_spawn({ type: "analyst", name: "analyst-1" })
mcp__ruv-swarm__agent_spawn({ type: "coder", name: "coder-1" })

// Step 3: NOW orchestrate tasks (agents must exist first!)
mcp__ruv-swarm__task_orchestrate({ task: "...", strategy: "parallel", priority: "high", maxAgents: 3 })

// Step 4: Monitor and collect
mcp__ruv-swarm__task_status({ detailed: true })
mcp__ruv-swarm__task_results({ taskId: "task-xxx", format: "detailed" })
```

### Pattern B2: RUV-Swarm DAA Workflow (For autonomous learning)

**⚠️ CRITICAL: DAA agents are SEPARATE from swarm agents. Use `daa_workflow_execute`, NOT `task_orchestrate`**

```javascript
// Step 1: Initialize DAA (no swarm_init needed for pure DAA)
mcp__ruv-swarm__daa_init({ enableLearning: true, enableCoordination: true })

// Step 2: Create autonomous agents (these are NOT swarm agents)
mcp__ruv-swarm__daa_agent_create({ id: "daa-1", cognitivePattern: "adaptive", enableMemory: true })
mcp__ruv-swarm__daa_agent_create({ id: "daa-2", cognitivePattern: "critical", enableMemory: true })

// Step 3: Create and execute DAA workflow (NOT task_orchestrate!)
mcp__ruv-swarm__daa_workflow_create({ id: "wf-1", name: "Analysis Workflow", strategy: "adaptive" })
mcp__ruv-swarm__daa_workflow_execute({ workflowId: "wf-1", agentIds: ["daa-1", "daa-2"], parallelExecution: true })

// Step 4: Share knowledge between DAA agents
mcp__ruv-swarm__daa_knowledge_share({ sourceAgentId: "daa-1", targetAgentIds: ["daa-2"] })

// Step 5: Check learning progress
mcp__ruv-swarm__daa_learning_status({ detailed: true })
```

### Pattern B3: Hybrid (Swarm + DAA Learning)

**Use when you need BOTH task orchestration AND learning capabilities**

```javascript
// Phase 1: Set up swarm for task orchestration
mcp__ruv-swarm__swarm_init({ topology: "mesh", strategy: "specialized" })
mcp__ruv-swarm__agent_spawn({ type: "researcher", name: "researcher-1" })
mcp__ruv-swarm__agent_spawn({ type: "coder", name: "coder-1" })

// Phase 2: Set up DAA for learning (separate agent pool)
mcp__ruv-swarm__daa_init({ enableLearning: true, enableCoordination: true })
mcp__ruv-swarm__daa_agent_create({ id: "learner-1", cognitivePattern: "adaptive", enableMemory: true })

// Phase 3: Orchestrate tasks with swarm agents
mcp__ruv-swarm__task_orchestrate({ task: "...", strategy: "parallel" })

// Phase 4: Use DAA to learn from results
mcp__ruv-swarm__daa_agent_adapt({ agentId: "learner-1", feedback: "Task completed", performanceScore: 0.9 })
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

**MCP coordinates, Claude Code Task tool executes.**

### ⛔ CRITICAL: Register Tasks in Coordination Layer

**After spawning MCP agents, you MUST use `task_create` with `assignToAgent` to register each task in the coordination layer BEFORE launching Task tool agents.** This links the MCP coordination metadata to the actual work, enabling monitoring via `task_status` / `task_results` instead of tailing output files.

**FAILURE MODE TO AVOID:**
```
❌ Spawn MCP agents → Launch Task tool agents → Tail output files manually
```

**CORRECT PATTERN:**
```javascript
// Step 1: Spawn MCP coordination agents
mcp__claude-flow__agent_spawn({ agentType: "coder", agentId: "agent-data-layer" })
mcp__claude-flow__agent_spawn({ agentType: "coder", agentId: "agent-chat-ui" })

// Step 2: Register tasks and assign to agents (THIS IS THE CRITICAL STEP)
mcp__claude-flow__task_create({
  type: "implement",
  description: "Implement data layer: CPT, roles, AJAX handlers",
  assignToAgent: "agent-data-layer",
  priority: 8
})
mcp__claude-flow__task_create({
  type: "implement",
  description: "Implement chat UI: panel, CSS, JS",
  assignToAgent: "agent-chat-ui",
  priority: 8
})

// Step 3: Launch ACTUAL work via Task tool (in background)
Task({ subagent_type: "coder", run_in_background: true, prompt: "..." })
Task({ subagent_type: "coder", run_in_background: true, prompt: "..." })

// Step 4: Monitor via coordination layer (NOT tailing files)
mcp__claude-flow__task_status({ taskId: "task-xxx" })
mcp__claude-flow__swarm_status({ includeAgents: true, includeMetrics: true })

// Step 5: Collect results
mcp__claude-flow__task_results({ taskId: "task-xxx", format: "detailed" })
TaskOutput({ task_id: "...", block: true })
```

**Why this matters:** Without `task_create` + `assignToAgent`, the MCP coordination layer has no visibility into what Task tool agents are doing. You end up with two disconnected layers — MCP agents that know nothing, and Task agents whose status you can only check by tailing output files. The entire point of the coordination layer is lost.

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

## ⚠️ MANDATORY: WM UPDATE

**Before transitioning to another state, you MUST:**
1. Update `## Progress` with completed steps
2. Update `**Files:**` with new files edited
3. Verify `## Workflow Context` is current

**SKIPPING WM UPDATE = WORKFLOW VIOLATION**

The hooks will BLOCK your next action if WM is stale.

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
