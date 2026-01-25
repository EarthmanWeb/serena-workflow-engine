# REF_SWARM_PATTERNS - Swarm Coordination Reference

Multi-agent swarm patterns for parallel processing and complex task coordination.

---

## ⚠️ CRITICAL: EXPLICIT TOOL SELECTION RULE

**When user explicitly requests a specific swarm system, USE THOSE EXACT MCP TOOLS.**

| User Says | YOU MUST USE | NOT |
|-----------|--------------|-----|
| "launch ruv-swarm" / "ruv swarm" | `mcp__plugin_swe_ruv-swarm__*` tools | Task/Explore agents |
| "launch claude-flow swarm" | `mcp__claude-flow__*` tools | Task/Explore agents |
| "use hive-mind" | `mcp__claude-flow__hive-mind_*` tools | Task/Explore agents |

**FAILURE MODE:** Substituting Task/Explore agents for MCP swarm tools breaks coordination model.

---

## ⛔ CRITICAL: NEVER RUN CLI INIT COMMANDS

**DO NOT run `npx claude-flow init`, `npx ruv-swarm init`, or any similar initialization commands.**

These commands modify repository files. Use MCP tools directly instead:
```javascript
// ✅ CORRECT: MCP tool (in-memory coordination only)
mcp__claude-flow__swarm_init({ topology: "mesh" })

// ❌ WRONG: CLI init (modifies repo files)
npx claude-flow init
```

---

## Available Swarm Systems

### 1. Claude-Flow (Primary - Recommended)
**MCP Prefix:** `mcp__claude-flow__*`

Core workflow:
```
1. mcp__claude-flow__swarm_init({ topology: "mesh"|"hierarchical"|"star", maxAgents: N })
2. mcp__claude-flow__agent_spawn({ agentType: "researcher"|"coder"|"analyst"|"tester", agentId: "..." })
3. mcp__claude-flow__task_orchestrate({ task: "description", strategy: "parallel"|"sequential", priority: "high" })
4. mcp__claude-flow__memory_store({ key: "swarm:state", value: { ... } })
```

Key tools:
- `swarm_init` - Initialize swarm with topology
- `agent_spawn` - Create agents (params: agentType, agentId)
- `task_orchestrate` - Coordinate task across agents
- `swarm_status` - Monitor swarm health
- `memory_store` - Store to persistent memory
- `memory_retrieve` - Get from memory
- `memory_search` - Pattern-based search

### 2. RUV-Swarm
**MCP Prefix:** `mcp__ruv-swarm__*`

**⚠️ CRITICAL: RUV-Swarm has TWO SEPARATE agent systems that DO NOT mix:**

| System | Agent Creation | Execution | Agent Pool |
|--------|---------------|-----------|------------|
| **Swarm** | `agent_spawn` | `task_orchestrate` | Swarm pool (visible to `agent_list`) |
| **DAA** | `daa_agent_create` | `daa_workflow_execute` | DAA pool (visible to `daa_learning_status`) |

**❌ WRONG (will fail with "No agents available"):**
```
daa_agent_create → task_orchestrate  // DAA agents NOT in swarm pool!
```

**✅ Pattern A: Task Orchestration (parallel tasks)**
```
1. mcp__ruv-swarm__swarm_init({ topology: "mesh", strategy: "balanced" })
2. mcp__ruv-swarm__agent_spawn({ type: "researcher", name: "r1" })  // Creates SWARM agent
3. mcp__ruv-swarm__agent_spawn({ type: "coder", name: "c1" })       // Creates SWARM agent
4. mcp__ruv-swarm__task_orchestrate({ task: "...", strategy: "parallel" })  // Uses SWARM agents
5. mcp__ruv-swarm__task_results({ taskId: "...", format: "detailed" })
```

**✅ Pattern B: DAA Workflow (autonomous learning)**
```
1. mcp__ruv-swarm__daa_init({ enableLearning: true, enableCoordination: true })
2. mcp__ruv-swarm__daa_agent_create({ id: "daa-1", cognitivePattern: "adaptive" })  // Creates DAA agent
3. mcp__ruv-swarm__daa_agent_create({ id: "daa-2", cognitivePattern: "critical" })  // Creates DAA agent
4. mcp__ruv-swarm__daa_workflow_create({ id: "wf-1", name: "...", strategy: "adaptive" })
5. mcp__ruv-swarm__daa_workflow_execute({ workflowId: "wf-1", agentIds: ["daa-1", "daa-2"] })  // Uses DAA agents
6. mcp__ruv-swarm__daa_knowledge_share({ sourceAgentId: "daa-1", targetAgentIds: ["daa-2"] })
```

**Swarm tools (for task_orchestrate):**
- `swarm_init` - Initialize swarm infrastructure
- `agent_spawn` - Create swarm agent (type: researcher|coder|analyst|optimizer|coordinator)
- `agent_list` - List swarm agents
- `task_orchestrate` - Execute task across swarm agents
- `task_status` - Check task progress
- `task_results` - Get task results

**DAA tools (for autonomous learning):**
- `daa_init` - Enable autonomous learning
- `daa_agent_create` - Create DAA agent with cognitive pattern
- `daa_workflow_create` - Create DAA workflow
- `daa_workflow_execute` - Execute DAA workflow with DAA agents
- `daa_knowledge_share` - Share patterns between DAA agents
- `daa_agent_adapt` - Trigger adaptation from feedback
- `daa_learning_status` - Check DAA agents learning progress
- `neural_train` - Train coordination patterns

### 3. Hive-Mind (Collective Intelligence & Consensus)
**MCP Prefix:** `mcp__claude-flow__hive-mind_*`

For tasks requiring collective decision-making or distributed memory:
```
1. mcp__claude-flow__hive-mind_init({ topology: "mesh" })
2. mcp__claude-flow__hive-mind_spawn({ count: 3, role: "worker", agentType: "worker" })
3. mcp__claude-flow__hive-mind_consensus({ action: "propose", type: "decision", value: "..." })
4. mcp__claude-flow__hive-mind_memory({ action: "set", key: "...", value: "..." })
5. mcp__claude-flow__hive-mind_status({ verbose: true })
6. mcp__claude-flow__hive-mind_broadcast({ message: "...", priority: "normal" })
```

Hive-Mind MCP tools:
- `hive-mind_init` - Initialize the collective (topology: mesh|hierarchical|ring|star)
- `hive-mind_spawn` - Spawn and auto-join workers (count, role, agentType)
- `hive-mind_join` - Join existing agent to hive
- `hive-mind_consensus` - Propose/vote on collective decisions
- `hive-mind_memory` - Distributed shared memory (get/set/delete/list)
- `hive-mind_status` - Monitor hive health
- `hive-mind_broadcast` - Send message to all workers

**Best for:**
- Decisions requiring consensus across multiple perspectives
- Distributed codebase analysis with shared findings
- Collaborative problem-solving
- Tasks where collective intelligence outperforms individual agents

---

## When to Use Swarms

| Scenario | Use | Reason |
|----------|-----|--------|
| Multi-file analysis | Claude-Flow mesh | Parallel processing |
| Code refactoring | Claude-Flow hierarchical | Coordinated changes |
| Research tasks | RUV-Swarm DAA | Learning from findings |
| Pattern discovery | RUV-Swarm + neural_train | Adaptive learning |
| Simple parallel tasks | Claude-Flow star | Quick coordination |
| Consensus decisions | Hive-Mind | Collective agreement |
| Distributed memory | Hive-Mind | Shared state across agents |
| Collaborative analysis | Hive-Mind mesh | Multiple perspectives |

---

## CRITICAL: Proper Swarm Usage

### DO:
1. Initialize swarm FIRST before spawning agents
2. Launch ALL agents in parallel (single message block)
3. Use Task tool for actual work (agents are coordination metadata)
4. Store coordination state to memory
5. Use non-blocking status checks during work
6. Collect results at end with blocking calls

### DON'T:
1. Spawn swarm then do work in single-agent mode
2. Block on first agent before spawning others
3. Read files directly when agents should do it
4. Forget to track agent IDs for result collection
5. Skip memory persistence for coordination state

---

## Workflow Patterns

### Pattern: Swarm Task Orchestration (RUV-Swarm or Claude-Flow)

```
Phase 1: ESTABLISH
  - swarm_init (choose topology: mesh/hierarchical/star/ring)

Phase 2: SPAWN (parallel - all in ONE message)
  - Multiple agent_spawn calls (creates SWARM agents)
  - Store agent IDs to memory

Phase 3: ORCHESTRATE
  - task_orchestrate (requires agents from Phase 2!)
  - Launch Task tool agents for actual file work (run_in_background: true)

Phase 4: MONITOR
  - swarm_status / agent_list (non-blocking)
  - Update memory with progress

Phase 5: COLLECT
  - task_results / TaskOutput with block: true

Phase 6: SYNTHESIZE
  - Combine results
  - Update Serena memory with findings
```

### Pattern: DAA Autonomous Learning (RUV-Swarm only)

```
Phase 1: ESTABLISH
  - daa_init (enables learning/coordination)

Phase 2: CREATE (parallel - all in ONE message)
  - Multiple daa_agent_create calls (creates DAA agents - NOT swarm agents!)
  - Choose cognitive patterns: adaptive/critical/convergent/divergent/lateral/systems

Phase 3: WORKFLOW
  - daa_workflow_create (define workflow steps)
  - daa_workflow_execute (run with DAA agents)

Phase 4: LEARN
  - daa_knowledge_share (share patterns between agents)
  - daa_agent_adapt (apply feedback)
  - daa_learning_status (check progress)

Phase 5: SYNTHESIZE
  - daa_performance_metrics (review effectiveness)
  - Update Serena memory with learnings
```

---

## Example: Multi-File Codebase Analysis

```javascript
// Step 1: Init
mcp__claude-flow__swarm_init({ topology: "mesh", maxAgents: 5 })

// Step 2: Spawn all agents in ONE message
mcp__claude-flow__agent_spawn({ agentType: "analyst", agentId: "code-reader-1" })
mcp__claude-flow__agent_spawn({ agentType: "analyst", agentId: "code-reader-2" })
mcp__claude-flow__agent_spawn({ agentType: "researcher", agentId: "pattern-finder" })

// Step 3: Orchestrate tasks
mcp__claude-flow__task_orchestrate({ task: "Analyze codebase structure", strategy: "parallel", priority: "high" })

// Step 4: Launch ACTUAL work agents (Claude Task tool)
Task({ subagent_type: "Explore", run_in_background: true, prompt: "Read module A files..." })
Task({ subagent_type: "Explore", run_in_background: true, prompt: "Read module B files..." })
Task({ subagent_type: "Explore", run_in_background: true, prompt: "Find patterns..." })

// Step 5: Store coordination state
mcp__claude-flow__memory_store({ key: "analysis:status", value: { status: "agents_spawned", agentCount: 3 } })

// Step 6: Monitor (non-blocking)
mcp__claude-flow__swarm_status({})

// Step 7: Collect results
TaskOutput({ task_id: "...", block: true })

// Step 8: Synthesize and update memory
```

---

## Topology Guide

| Topology | Structure | Best For |
|----------|-----------|----------|
| mesh | All agents connected peer-to-peer | Collaborative analysis, distributed work |
| hierarchical | Tree structure with coordinator | Complex projects, orchestrated changes |
| star | Central hub with workers | Quick parallel tasks |
| ring | Circular chain | Sequential processing |

---

## Agent Types

| Type | Capabilities | Use For |
|------|--------------|---------|
| researcher | Information gathering, pattern detection | Codebase exploration |
| analyst | Code analysis, data processing | Understanding structure |
| coder | Code generation, implementation | Writing changes |
| tester | Validation, verification | Testing changes |
| coordinator | Orchestration, synthesis | Managing complex flows |
| optimizer | Performance analysis | Optimization tasks |

---

## Tips

- **Start small**: Begin with 2-3 agents before scaling up
- **Use mesh for exploration**: When agents need to share discoveries
- **Use hierarchical for execution**: When changes must be coordinated
- **Monitor memory usage**: Swarm state consumes tokens
- **Persist across sessions**: Store agent IDs and task state to Serena memory

