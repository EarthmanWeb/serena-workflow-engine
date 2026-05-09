# WF_SWARM_RUV - Ruflo Coordination & DAA Methodology

**MCP Prefix:** `mcp__ruflo__`
**Full tool reference:** `ref/REF_RUFLO_MCP_TOOLS`

---

## Agent System Overview

| System | Create With | Execute With | Tracking |
|--------|------------|--------------|----------|
| **Swarm (B1)** | `agent_spawn` | `agent_execute` (API) or Claude Code `Agent` (file access) | Ruflo task/memory |
| **DAA (B2)** | `daa_agent_create` (metadata) + `agent_spawn` (execution) | Same as B1 | DAA knowledge_share across iterations |
| **Hybrid (B3)** | Both pools | Both execution paths | Both tracking systems |

---

## Pattern B1: Task Orchestration

**Use for:** Simple parallel tasks, file analysis, balanced workloads.

```javascript
// Phase 1: Init + spawn ALL agents in ONE message
ToolSearch({ query: "+ruflo swarm agent" })
ToolSearch({ query: "select:mcp__ruflo__agent_execute,mcp__ruflo__task_create" })

mcp__ruflo__swarm_init({ topology: "star", strategy: "balanced", maxAgents: 5 })
mcp__ruflo__agent_spawn({ agentType: "researcher", agentId: "r1", model: "sonnet" })
mcp__ruflo__agent_spawn({ agentType: "researcher", agentId: "r2", model: "sonnet" })
mcp__ruflo__task_create({ type: "research", description: "...", assignTo: ["r1", "r2"] })

// Phase 2: Execute — pick ONE path per agent
// Path A: Ruflo-native (reasoning/planning — no file access)
mcp__ruflo__agent_execute({ agentId: "r1", prompt: "...", maxTokens: 4096 })
mcp__ruflo__agent_execute({ agentId: "r2", prompt: "...", maxTokens: 4096 })

// Path B: Hybrid (codebase analysis — needs file access)
Agent({ description: "R1 task", run_in_background: true, prompt: "..." })

// Phase 3: Collect results
// Path A: Results come back directly from agent_execute
// Path B: Wait for Agent tool completion, then store:
mcp__ruflo__memory_store({ key: "r1-findings", value: { findings: "..." } })
```

---

## Pattern B2: DAA Multi-Iteration

**Use for:** Multi-round workflows where Round 1 findings shape Round 2 prompts.

| Cognitive Pattern | Use For |
|-------------------|---------|
| `critical` | Audits, finding flaws |
| `systems` | Architecture exploration |
| `adaptive` | Findings shape next query |
| `convergent` | Decision trees |
| `divergent` | Brainstorming |
| `lateral` | Creative solutions |

```javascript
// Phase 1: Create metadata + executable agents
ToolSearch({ query: "+ruflo daa agent" })
ToolSearch({ query: "select:mcp__ruflo__agent_execute,mcp__ruflo__daa_knowledge_share" })

mcp__ruflo__daa_agent_create({ id: "daa-1", cognitivePattern: "critical", enableMemory: true })
mcp__ruflo__agent_spawn({ agentType: "researcher", agentId: "r1", model: "sonnet" })

mcp__ruflo__daa_workflow_create({ id: "wf-1", name: "Analysis", strategy: "parallel",
  steps: [{ id: "s1", name: "Round 1", agentId: "daa-1", type: "analysis" }]
})

// Phase 2: Execute Round 1
mcp__ruflo__agent_execute({ agentId: "r1",
  prompt: "You are r1 (cognitive: critical). Analyze critically. [task details]...",
  maxTokens: 4096
})

// Phase 3: Store findings for next round
mcp__ruflo__daa_knowledge_share({
  sourceAgentId: "daa-1", targetAgentIds: ["daa-2"],
  knowledgeDomain: "analysis",
  knowledgeContent: { findings: "actual results from agent_execute" }
})
mcp__ruflo__daa_agent_adapt({ agentId: "daa-1", feedback: "summary", performanceScore: 0.9 })

// Phase 4: Round 2 — inject Round 1 knowledge
mcp__ruflo__agent_execute({ agentId: "r1",
  prompt: "Round 2. Context from Round 1: [findings]. Deep-dive into...",
  maxTokens: 4096
})
```

---

## Pattern B3: Hybrid (Swarm + DAA)

**Use for:** Multi-phase projects where early phases inform later ones.

1. `swarm_init` — set up coordination
2. `agent_spawn` — create executable agents for immediate work
3. `daa_agent_create` — create metadata agents for iteration tracking
4. Execute via `agent_execute` or Claude Code `Agent`
5. Store results via `daa_knowledge_share`
6. Read stored knowledge → shape next round's prompts
7. Record feedback via `daa_agent_adapt`

---

## Essential Tools

**See `ref/REF_RUFLO_MCP_TOOLS` for complete schemas and anti-patterns.**

| Tool | Purpose |
|------|---------|
| `swarm_init` | Initialize swarm with topology |
| `agent_spawn` | Create Ruflo-tracked executable agent |
| `agent_execute` | Run prompt on spawned agent (Anthropic API) |
| `agent_list` | List active agents |
| `task_create` | Register task for tracking |
| `task_status` / `task_summary` | Check progress / get results |
| `coordination_orchestrate` | Fan-out task across swarm agents |
| `daa_agent_create` | Create DAA metadata agent (tracking only) |
| `daa_workflow_create` | Register workflow steps (bookkeeping) |
| `daa_knowledge_share` | Store findings for cross-iteration use |
| `daa_agent_adapt` | Record performance feedback |
| `memory_store` | Persist coordination state |
