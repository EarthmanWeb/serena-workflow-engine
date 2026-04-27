# WF_SWARM_RUV - RUV-Swarm Methodology (Task + DAA + Hybrid)

**System:** RUV-Swarm
**MCP Prefix:** `mcp__ruv-swarm__`
**Version:** 1.0.20
**Tools:** 25 total (15 core + 10 DAA)
**Memory:** better-sqlite3 (native SQLite), 256MB mmap, WAL mode

---

## ⚠️ Verified MCP Tool Prefix

| System | Actual Prefix |
|--------|---------------|
| **RUV-Swarm** | `mcp__ruv-swarm__` |

**⛔ WRONG prefixes (never use):** ~~`mcp__plugin_claude-flow_ruv-swarm__`~~, ~~`mcp__plugin_swe_ruv-swarm__`~~

---

## ⚠️ TWO SEPARATE Agent Systems — DO NOT MIX

| System | Agent Creation | Execution | Pool |
|--------|----------------|-----------|------|
| **Swarm (B1)** | `agent_spawn` | `task_orchestrate` | Swarm pool |
| **DAA (B2)** | `daa_agent_create` | `daa_workflow_execute` | DAA pool |

**Never use `task_orchestrate` with DAA agents. Never use `daa_workflow_execute` with swarm agents.**

---

## Pattern B1: Task Orchestration

### When To Use

| Scenario | Topology |
|----------|----------|
| Simple parallel tasks | mesh |
| Quick file analysis | star |
| Balanced workload | mesh + balanced strategy |

### Phase 1: Load Tools + Initialize Swarm + Spawn Agents

```javascript
// 1. Load ruv-swarm tools
ToolSearch({ query: "+ruv-swarm agent task swarm" })
ToolSearch({ query: "select:mcp__ruv-swarm__swarm_init,mcp__ruv-swarm__task_results,mcp__ruv-swarm__task_status" })

// 2. Init swarm
mcp__ruv-swarm__swarm_init({ topology: "mesh", strategy: "balanced", maxAgents: 5 })
// Strategies: "balanced" (default), "specialized", "adaptive"

// 3. Spawn ALL agents in ONE message
mcp__ruv-swarm__agent_spawn({ type: "researcher", name: "r1", capabilities: ["analysis"] })
mcp__ruv-swarm__agent_spawn({ type: "coder", name: "c1", capabilities: ["implementation"] })
// Agent types: researcher, coder, analyst, optimizer, coordinator
```

### Phase 2: Orchestrate Tasks

```javascript
// 4. Orchestrate task across swarm agents
mcp__ruv-swarm__task_orchestrate({
  task: "Description of the overall task",
  strategy: "parallel",   // or "sequential", "adaptive"
  priority: "high",        // "low", "medium", "high", "critical"
  maxAgents: 5
})
```

### Phase 3: Launch Task Agents + Collect Results

```javascript
// 5. Launch background Agent tools for actual file work
Agent({ description: "...", run_in_background: true, prompt: "..." })

// 6. Check task status
mcp__ruv-swarm__task_status({ taskId: "task-id" })

// 7. Retrieve results
mcp__ruv-swarm__task_results({ taskId: "task-id", format: "summary" })
// Formats: "summary" (default), "detailed", "raw"
```

### B1-Specific Rules

- **`agent_spawn` agents ONLY** — never use `daa_agent_create` with `task_orchestrate`
- **Swarm agents ≠ DAA agents** — two separate pools, never mix
- **Use `task_results` with `format: "summary"`** to keep responses small

---

## Pattern B2: DAA (Autonomous Learning)

### When To Use

| Scenario | Cognitive Pattern |
|----------|-------------------|
| Audits, code reviews | `critical` |
| Architecture analysis | `systems` |
| General learning tasks | `adaptive` |
| Decision-making | `convergent` |
| Brainstorming | `divergent` |
| Creative solutions | `lateral` |

### Phase 1: Load Tools + Initialize DAA + Create Agents

```javascript
// 1. Load ALL needed DAA tools (3 ToolSearch calls covers everything)
ToolSearch({ query: "+ruv-swarm daa agent task swarm" })
ToolSearch({ query: "select:mcp__ruv-swarm__swarm_init,mcp__ruv-swarm__daa_init,mcp__ruv-swarm__daa_workflow_create,mcp__ruv-swarm__daa_workflow_execute,mcp__ruv-swarm__task_results" })
ToolSearch({ query: "select:mcp__ruv-swarm__daa_knowledge_share,mcp__ruv-swarm__daa_learning_status,mcp__ruv-swarm__daa_performance_metrics,mcp__ruv-swarm__daa_cognitive_pattern,mcp__ruv-swarm__daa_meta_learning" })

// 2. Init DAA (ONE call)
mcp__ruv-swarm__daa_init({ enableLearning: true, enableCoordination: true, persistenceMode: "memory" })

// 3. Create DAA agents — batch ALL in ONE message
mcp__ruv-swarm__daa_agent_create({
  id: "agent-1",
  cognitivePattern: "critical",
  enableMemory: true,
  capabilities: ["spec-audit", "code-review"]
})
mcp__ruv-swarm__daa_agent_create({
  id: "agent-2",
  cognitivePattern: "systems",
  enableMemory: true,
  capabilities: ["architecture-analysis"]
})
// ... more agents as needed
```

### Phase 2: Create Workflow + Execute + Enable Meta-Learning

```javascript
// 4. Create workflow with steps mapped to agents
mcp__ruv-swarm__daa_workflow_create({
  id: "wf-id",
  name: "Workflow Name",
  strategy: "parallel",  // or "sequential", "adaptive"
  steps: [
    { id: "step-1", name: "Step Name", description: "...", agentId: "agent-1", type: "analysis" },
    { id: "step-2", name: "Step Name", description: "...", agentId: "agent-2", type: "analysis" },
  ],
  dependencies: {}  // add { "step-2": ["step-1"] } if step-2 depends on step-1
})

// 5. Execute workflow with all agent IDs
mcp__ruv-swarm__daa_workflow_execute({
  workflowId: "wf-id",
  agentIds: ["agent-1", "agent-2"],
  parallelExecution: true
})

// 6. Enable meta-learning across agents for cross-domain knowledge transfer
mcp__ruv-swarm__daa_meta_learning({
  sourceDomain: "primary-domain",
  targetDomain: "secondary-domain",
  transferMode: "adaptive",  // or "direct", "gradual"
  agentIds: ["agent-1", "agent-2"]
})
```

### Phase 3: Launch Task Agents for Actual File Work

```javascript
// 7. Launch background Agent tools — one per DAA agent/step
//    MCP layer coordinates; Task agents execute in SEPARATE context windows
Agent({ description: "Task for agent-1", run_in_background: true, prompt: "..." })
Agent({ description: "Task for agent-2", run_in_background: true, prompt: "..." })
```

### Phase 4: Collect Results + Share Knowledge + Adapt

```javascript
// 8. After Task agents complete, share knowledge between DAA agents
mcp__ruv-swarm__daa_knowledge_share({
  sourceAgentId: "agent-1",
  targetAgentIds: ["agent-2"],
  knowledgeDomain: "domain-name",
  knowledgeContent: { findings: "summary of results" }
})

// 9. Adapt agents based on performance feedback
mcp__ruv-swarm__daa_agent_adapt({
  agentId: "agent-1",
  feedback: "description of performance",
  performanceScore: 0.9,
  suggestions: ["improvement suggestion"]
})

// 10. Check learning status across all agents
mcp__ruv-swarm__daa_learning_status({})

// 11. Get performance metrics
mcp__ruv-swarm__daa_performance_metrics({ category: "all" })
// Categories: "all", "system", "performance", "efficiency", "neural"
```

### Phase 5 (Optional): Analyze Cognitive Patterns

```javascript
// 12. Analyze agent cognitive patterns
mcp__ruv-swarm__daa_cognitive_pattern({
  action: "analyze",
  agentId: "agent-1"
})

// 13. Change pattern if agent needs different approach
mcp__ruv-swarm__daa_cognitive_pattern({
  action: "change",
  agentId: "agent-1",
  pattern: "adaptive"  // switch from current to adaptive
})
```

### DAA-Specific Rules

- **MCP = coordination, Agent tool = execution** — never read/write files in coordinator context
- **Batch all `daa_agent_create` calls** in ONE message
- **Always create workflow** via `daa_workflow_create` BEFORE `daa_workflow_execute` — don't skip it
- **Always use `daa_knowledge_share`** after collecting results to cross-pollinate findings
- **Always use `daa_agent_adapt`** to feed back results and improve agent performance
- **Use `daa_meta_learning`** to transfer learning across domains when agents cover different areas
- **Never mix** `daa_agent_create` agents with `agent_spawn` agents — they are separate pools
- **Never use** `task_orchestrate` with DAA agents — use `daa_workflow_execute` instead

---

## Pattern B3: Hybrid (Swarm + DAA)

Combine B1 for task orchestration + B2 for learning. Two separate agent pools.

### When To Use

- Need both parallel task execution AND learning/adaptation
- Complex multi-phase projects where early phases inform later ones

### Methodology

1. **Phase 1:** Init both systems — `swarm_init` + `daa_init`
2. **Phase 2:** Spawn swarm agents (`agent_spawn`) for immediate task work
3. **Phase 3:** Create DAA agents (`daa_agent_create`) for learning/analysis
4. **Phase 4:** Run swarm tasks via `task_orchestrate`
5. **Phase 5:** Feed swarm results into DAA via `daa_knowledge_share`
6. **Phase 6:** Run DAA workflows via `daa_workflow_execute` informed by swarm findings
7. **Phase 7:** Use `daa_agent_adapt` to improve future iterations

**Key rule:** Keep the two pools completely separate. Swarm agents run immediate tasks; DAA agents learn from results.

---

## Essential Tools Reference

### Swarm (B1) Tools

| Tool | Full Name | Purpose |
|------|-----------|---------|
| `swarm_init` | `mcp__ruv-swarm__swarm_init` | Initialize swarm |
| `agent_spawn` | `mcp__ruv-swarm__agent_spawn` | Create swarm agent |
| `task_orchestrate` | `mcp__ruv-swarm__task_orchestrate` | Execute across agents |
| `task_status` | `mcp__ruv-swarm__task_status` | Check progress |
| `task_results` | `mcp__ruv-swarm__task_results` | Get results |
| `agent_list` | `mcp__ruv-swarm__agent_list` | List agents |
| `agent_metrics` | `mcp__ruv-swarm__agent_metrics` | Performance metrics |

### DAA (B2) Tools

| Tool | Full Name | Purpose |
|------|-----------|---------|
| `daa_init` | `mcp__ruv-swarm__daa_init` | Initialize DAA |
| `daa_agent_create` | `mcp__ruv-swarm__daa_agent_create` | Create DAA agent |
| `daa_agent_adapt` | `mcp__ruv-swarm__daa_agent_adapt` | Adapt agent from feedback |
| `daa_workflow_create` | `mcp__ruv-swarm__daa_workflow_create` | Create workflow |
| `daa_workflow_execute` | `mcp__ruv-swarm__daa_workflow_execute` | Execute workflow |
| `daa_knowledge_share` | `mcp__ruv-swarm__daa_knowledge_share` | Share between agents |
| `daa_learning_status` | `mcp__ruv-swarm__daa_learning_status` | Learning progress |
| `daa_performance_metrics` | `mcp__ruv-swarm__daa_performance_metrics` | Performance data |
| `daa_cognitive_pattern` | `mcp__ruv-swarm__daa_cognitive_pattern` | Analyze/change patterns |
| `daa_meta_learning` | `mcp__ruv-swarm__daa_meta_learning` | Cross-domain transfer |

---

## Known Issues

| Issue | Mitigation |
|-------|------------|
| ruv-swarm WAL file grows unbounded | Clear npx cache periodically |
| Swarm agents ≠ DAA agents | Never mix pools |
| `task_orchestrate` ignores DAA agents | Use `daa_workflow_execute` instead |
