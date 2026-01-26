# CLAUDE_FLOW - MCP Swarm Coordination Reference

## ⚠️ VERIFIED MCP TOOL PREFIXES (2026-01-26)

| System | Actual MCP Prefix |
|--------|-------------------|
| **Claude-Flow** | `mcp__plugin_claude-flow_claude-flow__` |
| **RUV-Swarm** | `mcp__plugin_claude-flow_ruv-swarm__` |
| **Hive-Mind** | `mcp__plugin_claude-flow_claude-flow__hive-mind_` |

**IMPORTANT:** Use `ToolSearch` to load MCP tools before calling them.

---

## 🎯 MCP vs Task Tool Division

| MCP Tools (Coordination) | Task Tool (Execution) |
|--------------------------|----------------------|
| `swarm_init` - topology setup | Spawn agents for actual file work |
| `agent_spawn` - define agent types | Read/Write/Edit files |
| `task_orchestrate` - high-level planning | Run tests, build commands |
| `memory_store/retrieve` - state persistence | Code generation |
| `hive-mind_*` - consensus/broadcast | Implementation tasks |

**Rule:** MCP coordinates strategy → Task tool executes work

---

## 🐝 HIVE-MIND (Collective Intelligence)

**Prefix:** `mcp__plugin_claude-flow_claude-flow__hive-mind_`

| Tool | Parameters | Purpose |
|------|------------|---------|
| `hive-mind_init` | `topology`, `queenId` | Initialize collective |
| `hive-mind_spawn` | `count`, `role`, `agentType` | Spawn + auto-join workers |
| `hive-mind_consensus` | `action`, `type`, `value` | Propose/vote decisions |
| `hive-mind_memory` | `action`, `key`, `value` | Shared memory (get/set/list) |
| `hive-mind_broadcast` | `message`, `priority`, `fromId` | Message all workers |
| `hive-mind_status` | `verbose` | Monitor hive health |

**Pattern:**
```javascript
// 1. Init → 2. Spawn → 3. Memory → 4. Consensus → 5. Broadcast → 6. Status
hive-mind_init({ topology: "mesh", queenId: "queen-1" })
hive-mind_spawn({ count: 3, role: "worker", agentType: "analyst" })
hive-mind_memory({ action: "set", key: "config", value: {...} })
hive-mind_consensus({ action: "propose", type: "decision", value: {...} })
hive-mind_broadcast({ message: "...", priority: "high" })
hive-mind_status({ verbose: true })
```

---

## 🚀 RUV-SWARM Task Orchestration

**Prefix:** `mcp__plugin_claude-flow_ruv-swarm__`

| Tool | Parameters | Purpose |
|------|------------|---------|
| `swarm_init` | `topology`, `strategy`, `maxAgents` | Initialize swarm |
| `agent_spawn` | `type`, `name`, `capabilities` | Create swarm agent |
| `agent_list` | `filter` | List agents (all/active/idle/busy) |
| `task_orchestrate` | `task`, `strategy`, `priority`, `maxAgents` | Execute across agents |
| `task_status` | `taskId`, `detailed` | Check progress |
| `task_results` | `taskId`, `format` | Get results |

**Agent types:** `researcher`, `analyst`, `coder`, `optimizer`, `coordinator`

**Pattern:**
```javascript
// 1. Init → 2. Spawn agents → 3. Orchestrate → 4. Status → 5. Results
swarm_init({ topology: "mesh", strategy: "specialized", maxAgents: 5 })
agent_spawn({ type: "researcher", name: "r1" })
agent_spawn({ type: "analyst", name: "a1" })
agent_spawn({ type: "coder", name: "c1" })
task_orchestrate({ task: "...", strategy: "parallel", priority: "high" })
task_status({ detailed: true })
task_results({ taskId: "task-xxx", format: "detailed" })
```

---

## 🧠 RUV-SWARM DAA (Autonomous Learning)

**Prefix:** `mcp__plugin_claude-flow_ruv-swarm__`

| Tool | Parameters | Purpose |
|------|------------|---------|
| `daa_init` | `enableLearning`, `enableCoordination`, `persistenceMode` | Enable DAA |
| `daa_agent_create` | `id`, `cognitivePattern`, `enableMemory`, `learningRate` | Create DAA agent |
| `daa_agent_adapt` | `agentId`, `feedback`, `performanceScore` | Adapt from feedback |
| `daa_workflow_create` | `id`, `name`, `strategy`, `steps` | Create workflow |
| `daa_learning_status` | `detailed` | Check learning progress |

**Cognitive patterns:** `adaptive`, `critical`, `convergent`, `divergent`, `lateral`, `systems`

**⚠️ DAA agents ≠ Swarm agents** - Use `daa_workflow_execute`, NOT `task_orchestrate`

**Pattern:**
```javascript
// 1. Init → 2. Create agents → 3. Workflow → 4. Adapt → 5. Status
daa_init({ enableLearning: true, enableCoordination: true })
daa_agent_create({ id: "daa-1", cognitivePattern: "adaptive", enableMemory: true })
daa_agent_create({ id: "daa-2", cognitivePattern: "critical", enableMemory: true })
daa_workflow_create({ id: "wf-1", name: "Analysis", strategy: "adaptive" })
daa_agent_adapt({ agentId: "daa-1", feedback: "...", performanceScore: 0.9 })
daa_learning_status({ detailed: true })
```

---

## ⚡ GOLDEN RULES

1. **Batch operations** - All related calls in ONE message
2. **Init before spawn** - Always initialize swarm/hive first
3. **ToolSearch first** - Load MCP tools before calling
4. **MCP = coordination, Task = execution**
5. **Never run CLI init** - Use MCP tools, not `npx claude-flow init`

---

## 📊 When to Use Each System

| Scenario | System | Topology |
|----------|--------|----------|
| Parallel file analysis | RUV-Swarm | mesh |
| Coordinated refactoring | RUV-Swarm | hierarchical |
| Learning from patterns | RUV-Swarm DAA | adaptive |
| Consensus decisions | Hive-Mind | mesh |
| Distributed memory | Hive-Mind | mesh |
| Quick parallel tasks | Claude-Flow | star |

---

## 🔧 Loading Tools

```javascript
// Search and load tools
ToolSearch({ query: "+claude-flow hive-mind" })
ToolSearch({ query: "+ruv-swarm agent task" })

// Or select specific tool
ToolSearch({ query: "select:mcp__plugin_claude-flow_claude-flow__hive-mind_init" })
```

---

Remember: **MCP coordinates, Task tool executes!**
