# WF_SWARM_RUV - Ruflo Coordination & DAA Methodology (Task + DAA + Hybrid)

**System:** Ruflo (Coordination + DAA subsystems)
**MCP Prefix:** `mcp__ruflo__`

---

## ⚠️ Verified MCP Tool Prefix

| System | Actual Prefix |
|--------|---------------|
| **Ruflo** | `mcp__ruflo__` |

**⛔ WRONG prefixes (never use):** ~~`mcp__ruv-swarm__`~~, ~~`mcp__plugin_claude-flow_ruv-swarm__`~~, ~~`mcp__plugin_swe_ruv-swarm__`~~

---

## ⚠️ TWO SEPARATE Agent Systems — DO NOT MIX

| System | Agent Creation | Execution | Pool |
|--------|----------------|-----------|------|
| **Swarm (B1)** | `agent_spawn` | `coordination_orchestrate` | Swarm pool |
| **DAA (B2)** | `daa_agent_create` | `daa_workflow_execute` | DAA pool |

**Never use `coordination_orchestrate` with DAA agents. Never use `daa_workflow_execute` with swarm agents.**

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
// 1. Load ruflo tools
ToolSearch({ query: "+ruflo agent coordination swarm" })
ToolSearch({ query: "select:mcp__ruflo__swarm_init,mcp__ruflo__task_summary,mcp__ruflo__task_status" })

// 2. Init swarm
mcp__ruflo__swarm_init({ topology: "mesh", strategy: "balanced", maxAgents: 5 })
// Strategies: "balanced" (default), "specialized", "adaptive"

// 3. Spawn ALL agents in ONE message
mcp__ruflo__agent_spawn({ type: "researcher", name: "r1", capabilities: ["analysis"] })
mcp__ruflo__agent_spawn({ type: "coder", name: "c1", capabilities: ["implementation"] })
// Agent types: researcher, coder, analyst, optimizer, coordinator
```

### Phase 2: Orchestrate Tasks

```javascript
// 4. Orchestrate task across swarm agents
mcp__ruflo__coordination_orchestrate({
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
mcp__ruflo__task_status({ taskId: "task-id" })

// 7. Retrieve results
mcp__ruflo__task_summary({ taskId: "task-id" })
```

### B1-Specific Rules

- **`agent_spawn` agents ONLY** — never use `daa_agent_create` with `coordination_orchestrate`
- **Swarm agents ≠ DAA agents** — two separate pools, never mix
- **Use `task_summary`** to keep responses small

---

## Pattern B2: DAA (Iterative Coordination & Tracking)

### ⚠️ DAA REALITY — Read Before Using

**DAA is a metadata/tracking layer, NOT an execution engine.**

| DAA Tool | What It Actually Does |
|----------|----------------------|
| `daa_agent_create` | Creates a JSON record with id, cognitive pattern label, capabilities list. No process spawned. |
| `daa_workflow_create` | Creates a JSON workflow record with steps. No execution logic. |
| `daa_workflow_execute` | **Flips a status flag.** Returns empty arrays. Does NOT run agents or analysis. |
| `daa_knowledge_share` | Stores a JSON blob. Source note: "No cross-agent memory transfer occurs." |
| `daa_agent_adapt` | Changes cognitive pattern string based on score thresholds. |
| `daa_learning_status` | Returns hardcoded/random metrics. |
| `daa_performance_metrics` | Mix of real counts and random values. |
| `daa_cognitive_pattern` | Reads or changes a string enum label. Returns random effectiveness scores. |

**All actual work (file reading, analysis, code generation) is done by the Agent tool in separate context windows. DAA tools NEVER read files, analyze code, or produce findings.**

### When DAA Adds Value vs When It's Overhead

| Scenario | Use DAA? | Why |
|----------|----------|-----|
| **Single-pass parallel analysis** | ❌ NO — use Ruflo swarm | DAA adds ~10 MCP calls of pure overhead. Agent tools do all real work regardless. |
| **Multi-iteration workflow** where Round 1 findings shape Round 2 prompts | ✅ YES | DAA provides structured storage for cross-iteration state. |
| **Iterative refinement** with feedback loops | ✅ YES | DAA tracks which agents performed well, stores knowledge for reuse across rounds. |
| **Research with learning** across repeated similar tasks | ✅ YES | Knowledge registry builds up findings for future Agent prompts. |

### When To Use

| Scenario | Cognitive Pattern |
|----------|-------------------|
| Multi-round audits with refinement | `critical` |
| Iterative architecture exploration | `systems` |
| Adaptive research (findings shape next query) | `adaptive` |
| Decision trees requiring multiple passes | `convergent` |
| Brainstorming across iterations | `divergent` |
| Creative multi-pass solutions | `lateral` |

### Phase 1: Load Tools + Create DAA Agents

```javascript
// 1. Load DAA tools (2 ToolSearch calls max)
ToolSearch({ query: "+ruflo daa agent" })
ToolSearch({ query: "select:mcp__ruflo__daa_agent_create,mcp__ruflo__daa_workflow_create,mcp__ruflo__daa_knowledge_share" })

// 2. Create DAA agents — cognitive pattern WILL BE USED to shape Agent prompts
mcp__ruflo__daa_agent_create({
  id: "agent-1",
  cognitivePattern: "critical",    // → Agent prompt will emphasize: "Analyze critically, find flaws"
  enableMemory: true,
  capabilities: ["spec-audit", "code-review"]
})
mcp__ruflo__daa_agent_create({
  id: "agent-2",
  cognitivePattern: "systems",     // → Agent prompt will emphasize: "Think holistically, trace connections"
  enableMemory: true,
  capabilities: ["architecture-analysis"]
})
```

### Phase 2: Create Workflow (Tracking Only)

```javascript
// 3. Register workflow — this is BOOKKEEPING, not execution
mcp__ruflo__daa_workflow_create({
  id: "wf-id",
  name: "Workflow Name",
  strategy: "parallel",
  steps: [
    { id: "step-1", name: "Step Name", description: "...", agentId: "agent-1", type: "analysis" },
    { id: "step-2", name: "Step Name", description: "...", agentId: "agent-2", type: "analysis" },
  ],
  dependencies: {}
})

// ⚠️ DO NOT call daa_workflow_execute here — it returns empty arrays.
```

### Phase 3: Launch Agent Tools — THE ACTUAL WORK

**This is where real work happens. The DAA cognitive pattern MUST shape the Agent prompt.**

```javascript
// 4. Launch background Agent tools — ONE per DAA agent
// ⚠️ CRITICAL: Include the cognitive pattern instruction in the Agent prompt
Agent({
  description: "Task for agent-1",
  run_in_background: true,
  prompt: `You are agent-1 (cognitive pattern: critical).
Analyze critically. Identify flaws, gaps, and risks. Question assumptions.

Your task: [specific task description]
Research ONLY — do NOT modify files.

After completing analysis, structure your findings as:
- KEY_FINDINGS: [list]
- ISSUES_FOUND: [list]
- RECOMMENDATIONS: [list]`
})
```

### Phase 4: Collect Results + Store in DAA (for multi-iteration use)

```javascript
// 5. After Agent tools complete, store ACTUAL findings in DAA for the NEXT iteration
mcp__ruflo__daa_knowledge_share({
  sourceAgentId: "agent-1",
  targetAgentIds: ["agent-2"],
  knowledgeDomain: "domain-name",
  knowledgeContent: { findings: "ACTUAL findings from Agent tool results — not empty data" }
})

// 6. Record performance feedback (only useful if you'll iterate)
mcp__ruflo__daa_agent_adapt({
  agentId: "agent-1",
  feedback: "Found 3 critical issues in auth flow",
  performanceScore: 0.9,
  suggestions: ["Expand scope to include session management"]
})
```

### Phase 5 (Multi-Iteration ONLY): Use Stored Knowledge for Next Round

```javascript
// 7. READ stored knowledge before crafting next-round Agent prompts
mcp__ruflo__daa_learning_status({ agentId: "agent-1", detailed: true })

// 8. Launch Round 2 agents with knowledge from Round 1 injected into prompts
Agent({
  description: "Round 2 for agent-1",
  run_in_background: true,
  prompt: `You are agent-1 (cognitive pattern: critical), Round 2.
Analyze critically. Identify flaws, gaps, and risks. Question assumptions.

CONTEXT FROM ROUND 1:
[Insert actual findings from Phase 4 knowledge_share here]

Your task: Deep-dive into the issues found in Round 1...`
})
```

### DAA-Specific Rules

- **MCP = tracking/metadata, Agent tool = execution** — DAA tools NEVER read/write files
- **DO NOT call `daa_workflow_execute` expecting results** — it returns empty arrays
- **DO inject cognitive patterns into Agent prompts** — this is how DAA influences real work
- **DO store actual Agent findings via `daa_knowledge_share`** — not empty/fake data
- **ONLY use DAA for multi-iteration workflows** — single-pass parallel work should use Ruflo swarm
- **Skip `daa_performance_metrics` and `daa_learning_status`** unless tracking iteration state
- **Never mix** `daa_agent_create` agents with `agent_spawn` agents — they are separate pools

---

## Pattern B3: Hybrid (Swarm + DAA)

Combine B1 for task orchestration + B2 for iterative tracking. Two separate agent pools.

### When To Use

- Need both parallel task execution AND cross-iteration state tracking
- Complex multi-phase projects where early phases inform later ones

### Methodology

1. **Phase 1:** Init swarm — `swarm_init`
2. **Phase 2:** Spawn swarm agents (`agent_spawn`) for immediate task work
3. **Phase 3:** Create DAA agents (`daa_agent_create`) for iterative tracking
4. **Phase 4:** Run swarm tasks via `coordination_orchestrate` + Agent tools (actual work)
5. **Phase 5:** Feed swarm results into DAA via `daa_knowledge_share` (store ACTUAL findings)
6. **Phase 6:** For next iteration, read stored DAA knowledge → shape new Agent prompts
7. **Phase 7:** Use `daa_agent_adapt` to record performance feedback for tracking

**Key rule:** Keep the two pools completely separate. Swarm agents (via Agent tool) run immediate tasks; DAA agents track state and store findings for cross-iteration use. DAA does NOT execute work — it's bookkeeping.

---

## Essential Tools Reference

### Swarm (B1) Tools

| Tool | Full Name | Purpose |
|------|-----------|---------|
| `swarm_init` | `mcp__ruflo__swarm_init` | Initialize swarm |
| `swarm_status` | `mcp__ruflo__swarm_status` | Check swarm state |
| `agent_spawn` | `mcp__ruflo__agent_spawn` | Create swarm agent |
| `agent_list` | `mcp__ruflo__agent_list` | List agents |
| `coordination_orchestrate` | `mcp__ruflo__coordination_orchestrate` | Execute across agents |
| `task_status` | `mcp__ruflo__task_status` | Check progress |
| `task_summary` | `mcp__ruflo__task_summary` | Get results |

### DAA (B2) Tools

| Tool | Full Name | Purpose |
|------|-----------|---------|
| `daa_agent_create` | `mcp__ruflo__daa_agent_create` | Create DAA agent |
| `daa_agent_adapt` | `mcp__ruflo__daa_agent_adapt` | Adapt agent from feedback |
| `daa_workflow_create` | `mcp__ruflo__daa_workflow_create` | Create workflow |
| `daa_workflow_execute` | `mcp__ruflo__daa_workflow_execute` | Execute workflow |
| `daa_knowledge_share` | `mcp__ruflo__daa_knowledge_share` | Share between agents |
| `daa_learning_status` | `mcp__ruflo__daa_learning_status` | Learning progress |
| `daa_performance_metrics` | `mcp__ruflo__daa_performance_metrics` | Performance data |
| `daa_cognitive_pattern` | `mcp__ruflo__daa_cognitive_pattern` | Analyze/change patterns |

### Additional Ruflo Tools

| Tool | Full Name | Purpose |
|------|-----------|---------|
| `performance_benchmark` | `mcp__ruflo__performance_benchmark` | Run performance benchmarks |
| `neural_patterns` | `mcp__ruflo__neural_patterns` | Analyze neural patterns |
| `neural_status` | `mcp__ruflo__neural_status` | Check neural engine state |
| `neural_train` | `mcp__ruflo__neural_train` | Train neural models |

---

## Known Issues

| Issue | Mitigation |
|-------|------------|
| Swarm agents ≠ DAA agents | Never mix pools |
| `coordination_orchestrate` ignores DAA agents | Use `daa_workflow_execute` instead |
