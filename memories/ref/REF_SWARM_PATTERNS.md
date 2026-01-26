# REF_SWARM_PATTERNS - Swarm Coordination Reference

Multi-agent swarm patterns for parallel processing and complex task coordination.

---

## ⚠️ CRITICAL: ACTUAL MCP TOOL NAMES (Verified 2026-01-26)

**The MCP tool names follow this pattern:**
```
mcp__plugin_claude-flow_<system>__<tool_name>
```

| System | MCP Prefix | Example |
|--------|------------|---------|
| **Claude-Flow** | `mcp__plugin_claude-flow_claude-flow__` | `mcp__plugin_claude-flow_claude-flow__swarm_init` |
| **RUV-Swarm** | `mcp__plugin_claude-flow_ruv-swarm__` | `mcp__plugin_claude-flow_ruv-swarm__agent_spawn` |
| **Hive-Mind** | `mcp__plugin_claude-flow_claude-flow__hive-mind_` | `mcp__plugin_claude-flow_claude-flow__hive-mind_init` |

---

## ⚠️ CRITICAL: EXPLICIT TOOL SELECTION RULE

**When user explicitly requests a specific swarm system, USE THOSE EXACT MCP TOOLS.**

| User Says | YOU MUST USE | NOT |
|-----------|--------------|-----|
| "launch ruv-swarm" / "ruv swarm" | `mcp__plugin_claude-flow_ruv-swarm__*` tools | Task/Explore agents |
| "launch claude-flow swarm" | `mcp__plugin_claude-flow_claude-flow__*` tools | Task/Explore agents |
| "use hive-mind" | `mcp__plugin_claude-flow_claude-flow__hive-mind_*` tools | Task/Explore agents |

**FAILURE MODE:** Substituting Task/Explore agents for MCP swarm tools breaks coordination model.

---

## ⛔ CRITICAL: NEVER RUN CLI INIT COMMANDS

**DO NOT run `npx claude-flow init`, `npx ruv-swarm init`, or any similar initialization commands.**

These commands modify repository files. Use MCP tools directly instead:
```javascript
// ✅ CORRECT: MCP tool (in-memory coordination only)
mcp__plugin_claude-flow_claude-flow__swarm_init({ topology: "mesh" })

// ❌ WRONG: CLI init (modifies repo files)
npx claude-flow init
```

---

## Available Swarm Systems

### 1. Claude-Flow (Primary - Recommended)
**MCP Prefix:** `mcp__plugin_claude-flow_claude-flow__`

**Verified Tools:**
| Tool | Full Name |
|------|-----------|
| `swarm_init` | `mcp__plugin_claude-flow_claude-flow__swarm_init` |
| `swarm_status` | `mcp__plugin_claude-flow_claude-flow__swarm_status` |
| `swarm_shutdown` | `mcp__plugin_claude-flow_claude-flow__swarm_shutdown` |
| `swarm_health` | `mcp__plugin_claude-flow_claude-flow__swarm_health` |
| `agent_spawn` | `mcp__plugin_claude-flow_claude-flow__agent_spawn` |
| `agent_list` | `mcp__plugin_claude-flow_claude-flow__agent_list` |
| `memory_store` | `mcp__plugin_claude-flow_claude-flow__memory_store` |
| `memory_retrieve` | `mcp__plugin_claude-flow_claude-flow__memory_retrieve` |

Core workflow:
```javascript
// 1. Initialize swarm
mcp__plugin_claude-flow_claude-flow__swarm_init({ topology: "mesh", maxAgents: 15 })

// 2. Spawn agents
mcp__plugin_claude-flow_claude-flow__agent_spawn({ agentType: "researcher", agentId: "agent-1" })

// 3. Check status
mcp__plugin_claude-flow_claude-flow__swarm_status({ includeAgents: true })

// 4. Store coordination state
mcp__plugin_claude-flow_claude-flow__memory_store({ key: "swarm:state", value: { ... } })
```

### 2. RUV-Swarm
**MCP Prefix:** `mcp__plugin_claude-flow_ruv-swarm__`

**⚠️ CRITICAL: RUV-Swarm has TWO SEPARATE agent systems that DO NOT mix:**

| System | Agent Creation | Execution | Agent Pool |
|--------|---------------|-----------|------------|
| **Swarm** | `agent_spawn` | `task_orchestrate` | Swarm pool (visible to `agent_list`) |
| **DAA** | `daa_agent_create` | `daa_workflow_execute` | DAA pool (visible to `daa_learning_status`) |

**❌ WRONG (will fail with "No agents available"):**
```
daa_agent_create → task_orchestrate  // DAA agents NOT in swarm pool!
```

**Verified Swarm Tools:**
| Tool | Full Name |
|------|-----------|
| `swarm_init` | `mcp__plugin_claude-flow_ruv-swarm__swarm_init` |
| `agent_spawn` | `mcp__plugin_claude-flow_ruv-swarm__agent_spawn` |
| `agent_list` | `mcp__plugin_claude-flow_ruv-swarm__agent_list` |
| `task_orchestrate` | `mcp__plugin_claude-flow_ruv-swarm__task_orchestrate` |
| `task_status` | `mcp__plugin_claude-flow_ruv-swarm__task_status` |
| `task_results` | `mcp__plugin_claude-flow_ruv-swarm__task_results` |

**Verified DAA Tools:**
| Tool | Full Name |
|------|-----------|
| `daa_init` | `mcp__plugin_claude-flow_ruv-swarm__daa_init` |
| `daa_agent_create` | `mcp__plugin_claude-flow_ruv-swarm__daa_agent_create` |
| `daa_agent_adapt` | `mcp__plugin_claude-flow_ruv-swarm__daa_agent_adapt` |
| `daa_workflow_create` | `mcp__plugin_claude-flow_ruv-swarm__daa_workflow_create` |
| `daa_learning_status` | `mcp__plugin_claude-flow_ruv-swarm__daa_learning_status` |

**✅ Pattern A: Task Orchestration (parallel tasks)**
```javascript
// 1. Initialize swarm
mcp__plugin_claude-flow_ruv-swarm__swarm_init({ topology: "mesh", strategy: "balanced", maxAgents: 5 })

// 2. Spawn swarm agents (REQUIRED before task_orchestrate)
mcp__plugin_claude-flow_ruv-swarm__agent_spawn({ type: "researcher", name: "r1" })
mcp__plugin_claude-flow_ruv-swarm__agent_spawn({ type: "coder", name: "c1" })
mcp__plugin_claude-flow_ruv-swarm__agent_spawn({ type: "analyst", name: "a1" })

// 3. Orchestrate task across agents
mcp__plugin_claude-flow_ruv-swarm__task_orchestrate({ task: "...", strategy: "parallel", priority: "high" })

// 4. Check status and get results
mcp__plugin_claude-flow_ruv-swarm__task_status({ detailed: true })
mcp__plugin_claude-flow_ruv-swarm__task_results({ taskId: "task-xxx", format: "detailed" })
```

**✅ Pattern B: DAA Workflow (autonomous learning)**
```javascript
// 1. Initialize DAA
mcp__plugin_claude-flow_ruv-swarm__daa_init({ enableLearning: true, enableCoordination: true })

// 2. Create DAA agents (NOT swarm agents!)
mcp__plugin_claude-flow_ruv-swarm__daa_agent_create({ id: "daa-1", cognitivePattern: "adaptive", enableMemory: true })
mcp__plugin_claude-flow_ruv-swarm__daa_agent_create({ id: "daa-2", cognitivePattern: "critical", enableMemory: true })

// 3. Create and execute DAA workflow
mcp__plugin_claude-flow_ruv-swarm__daa_workflow_create({ id: "wf-1", name: "Analysis", strategy: "adaptive" })

// 4. Adapt agents based on feedback
mcp__plugin_claude-flow_ruv-swarm__daa_agent_adapt({ agentId: "daa-1", feedback: "...", performanceScore: 0.9 })

// 5. Check learning status
mcp__plugin_claude-flow_ruv-swarm__daa_learning_status({ detailed: true })
```

### 3. Hive-Mind (Collective Intelligence & Consensus)
**MCP Prefix:** `mcp__plugin_claude-flow_claude-flow__hive-mind_`

**Verified Hive-Mind Tools:**
| Tool | Full Name |
|------|-----------|
| `hive-mind_init` | `mcp__plugin_claude-flow_claude-flow__hive-mind_init` |
| `hive-mind_spawn` | `mcp__plugin_claude-flow_claude-flow__hive-mind_spawn` |
| `hive-mind_consensus` | `mcp__plugin_claude-flow_claude-flow__hive-mind_consensus` |
| `hive-mind_memory` | `mcp__plugin_claude-flow_claude-flow__hive-mind_memory` |
| `hive-mind_status` | `mcp__plugin_claude-flow_claude-flow__hive-mind_status` |
| `hive-mind_broadcast` | `mcp__plugin_claude-flow_claude-flow__hive-mind_broadcast` |

**Complete Hive-Mind Pattern:**
```javascript
// 1. Initialize hive with topology and queen
mcp__plugin_claude-flow_claude-flow__hive-mind_init({ topology: "mesh", queenId: "queen-coordinator" })

// 2. Spawn and auto-join workers
mcp__plugin_claude-flow_claude-flow__hive-mind_spawn({ count: 3, role: "worker", agentType: "analyst" })

// 3. Set shared memory
mcp__plugin_claude-flow_claude-flow__hive-mind_memory({ action: "set", key: "config", value: {...} })

// 4. Propose consensus decision
mcp__plugin_claude-flow_claude-flow__hive-mind_consensus({ action: "propose", type: "decision", value: {...} })

// 5. Broadcast to all workers
mcp__plugin_claude-flow_claude-flow__hive-mind_broadcast({ message: "...", priority: "high", fromId: "queen-coordinator" })

// 6. Get hive status
mcp__plugin_claude-flow_claude-flow__hive-mind_status({ verbose: true })

// 7. Retrieve shared memory
mcp__plugin_claude-flow_claude-flow__hive-mind_memory({ action: "get", key: "config" })
```

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

## Topology Guide

| Topology | Structure | Best For |
|----------|-----------|----------|
| mesh | All agents connected peer-to-peer | Collaborative analysis, distributed work |
| hierarchical | Tree structure with coordinator | Complex projects, orchestrated changes |
| star | Central hub with workers | Quick parallel tasks |
| ring | Circular chain | Sequential processing |

---

## Agent Types

### RUV-Swarm Agent Types (for `agent_spawn`)
| Type | Capabilities | Use For |
|------|--------------|---------|
| researcher | Information gathering, pattern detection | Codebase exploration |
| analyst | Code analysis, data processing | Understanding structure |
| coder | Code generation, implementation | Writing changes |
| optimizer | Performance analysis | Optimization tasks |
| coordinator | Orchestration, synthesis | Managing complex flows |

### DAA Cognitive Patterns (for `daa_agent_create`)
| Pattern | Thinking Style | Use For |
|---------|---------------|---------|
| adaptive | Flexible, learns from feedback | General learning tasks |
| critical | Analytical, evaluative | Code review, quality analysis |
| convergent | Focused, solution-oriented | Problem-solving |
| divergent | Creative, exploratory | Brainstorming, discovery |
| lateral | Unconventional connections | Innovation |
| systems | Holistic, interconnected | Architecture analysis |

---

## Tips

- **Start small**: Begin with 2-3 agents before scaling up
- **Use mesh for exploration**: When agents need to share discoveries
- **Use hierarchical for execution**: When changes must be coordinated
- **Monitor memory usage**: Swarm state consumes tokens
- **Persist across sessions**: Store agent IDs and task state to Serena memory
- **Use ToolSearch first**: Load MCP tools with `ToolSearch` before calling them
