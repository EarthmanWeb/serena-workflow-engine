# WF_SWARM_HIVE_MIND - Hive-Mind Collective Intelligence Methodology

**System:** Hive-Mind (part of Claude-Flow)
**MCP Prefix:** `mcp__claude-flow__hive-mind_`
**Purpose:** Consensus-based decisions, collective intelligence, shared memory

---

## ⚠️ Verified MCP Tool Prefix

| System | Actual Prefix |
|--------|---------------|
| **Hive-Mind** | `mcp__claude-flow__hive-mind_` |

**Note:** Hive-Mind tools are part of Claude-Flow but use the `hive-mind_` sub-prefix.

---

## When To Use

| Scenario | Topology |
|----------|----------|
| Consensus decisions across agents | mesh |
| Collective code review | mesh |
| Architecture decision-making | mesh |
| Shared knowledge accumulation | mesh |

**Hive-Mind is best for tasks requiring agreement or collective intelligence, not raw parallel execution.** For parallel tasks, use Claude-Flow (Pattern A) or RUV-Swarm (Pattern B1).

---

## Phase 1: Load Tools + Initialize Hive

```javascript
// 1. Load hive-mind tools
ToolSearch({ query: "+claude-flow hive-mind" })

// 2. Init hive with topology and queen
mcp__claude-flow__hive-mind_init({
  topology: "mesh",
  queenId: "queen-1"
})
```

---

## Phase 2: Spawn Workers

```javascript
// 3. Spawn worker agents
mcp__claude-flow__hive-mind_spawn({
  count: 3,
  role: "worker",        // "worker" or "queen"
  agentType: "analyst"   // researcher, analyst, coder, etc.
})
```

---

## Phase 3: Set Shared Memory + Broadcast

```javascript
// 4. Store shared configuration/context in hive memory
mcp__claude-flow__hive-mind_memory({
  action: "set",
  key: "task-config",
  value: { description: "...", scope: "..." }
})

// 5. Broadcast instructions to all workers
mcp__claude-flow__hive-mind_broadcast({
  message: "Analyze the form submission pipeline for gaps",
  priority: "high"
})

// 6. Retrieve shared memory
mcp__claude-flow__hive-mind_memory({
  action: "get",
  key: "task-config"
})
```

---

## Phase 4: Launch Task Agents for File Work

**⛔ CRITICAL: Agent prompts MUST include hive-mind tool instructions.**

The hive-mind is file-backed (`.claude-flow/hive-mind/state.json`). Any process calling hive-mind MCP tools reads/writes the SAME shared state. Agent subagents have access to all MCP tools but **will not use them unless explicitly instructed in their prompt**.

**Every agent prompt MUST include these steps:**

1. `ToolSearch({ query: "select:mcp__claude-flow__hive-mind_memory", max_results: 1 })` — load the tool
2. `mcp__claude-flow__hive-mind_memory({ action: "get", key: "..." })` — read shared context
3. Do analysis work (file reads, codebase research)
4. `mcp__claude-flow__hive-mind_memory({ action: "set", key: "findings-{agent-id}", value: {...} })` — write findings to shared memory
5. (Optional) `mcp__claude-flow__hive-mind_memory({ action: "get", key: "findings-{other-agent}" })` — cross-reference other agents' findings

**Agent prompt template:**

```
You are {role} in a hive-mind swarm.

## STEP 1: Load hive-mind tools
Call: ToolSearch({ query: "select:mcp__claude-flow__hive-mind_memory", max_results: 1 })

## STEP 2: Read shared context from hive-mind
Call: mcp__claude-flow__hive-mind_memory({ action: "get", key: "{context-key}" })
Also check for scope updates:
Call: mcp__claude-flow__hive-mind_memory({ action: "get", key: "scope-update-{domain}" })

## STEP 3: Do your analysis
{domain-specific instructions}

## STEP 3b: MID-TASK SCOPE CHECK (poll for updates)
Before writing findings, check for scope refinements from the coordinator:
Call: mcp__claude-flow__hive-mind_memory({ action: "list" })
Look for any keys starting with "scope-update-" that appeared AFTER your initial read.
Read and apply any new scope constraints to your remaining work.

## STEP 4: Store findings in hive-mind shared memory
Call: mcp__claude-flow__hive-mind_memory({ action: "set", key: "findings-{agent-id}", value: { ... } })

## STEP 5: Cross-reference (if other agents have finished)
Call: mcp__claude-flow__hive-mind_memory({ action: "list" })
Then get any findings-* keys from other agents to cross-reference.
```

**Scope update polling pattern:**

Since `SendMessage` does not exist, the coordinator cannot push updates to running agents. Instead, use a pull-based pattern:

1. **Coordinator** writes scope refinements to a known key pattern: `scope-update-{topic}`
2. **Agents** poll for scope updates at defined checkpoints:
   - After initial context read (Step 2)
   - Before each major analysis section (Step 3b)
   - Before writing final findings (Step 4)
3. **Key convention:** `scope-update-*` keys are always refinements — agents merge them with initial instructions, they don't replace them
4. **For long-running agents**, add a poll step between each audit item analysis:
   ```
   ## Between each item analysis:
   Call: mcp__claude-flow__hive-mind_memory({ action: "get", key: "scope-update-{domain}" })
   If value exists and differs from last read, apply the refinement to remaining work.
   ```

**Launch agents in parallel:**

```javascript
// 7. Launch background Agent tools for actual work
Agent({ description: "Worker 1 analysis", run_in_background: true, prompt: "..." })
Agent({ description: "Worker 2 analysis", run_in_background: true, prompt: "..." })
Agent({ description: "Worker 3 analysis", run_in_background: true, prompt: "..." })
```

**Verified behavior (tested 2026-04-27):**
- Coordinator stores context → Agent reads it via `hive-mind_memory get` ✓
- Agent stores findings → Coordinator reads them via `hive-mind_memory get` ✓
- Agent loads MCP tools via `ToolSearch` inside Agent subagent ✓
- All backed by same file: `.claude-flow/hive-mind/state.json` ✓

---

## Phase 5: Consensus + Collect Results

After all agents complete and store findings in shared memory:

```javascript
// 8. Coordinator reads all agent findings from shared memory
mcp__claude-flow__hive-mind_memory({ action: "list" })
// Then get each findings-* key

// 9. Propose a decision for consensus
mcp__claude-flow__hive-mind_consensus({
  action: "propose",
  type: "decision",
  strategy: "quorum",           // "bft", "raft", or "quorum"
  quorumPreset: "majority",     // "unanimous", "majority", "supermajority"
  value: {
    question: "Should we refactor the submission pipeline?",
    options: ["yes-full-refactor", "partial-refactor", "no-change"]
  }
})

// 10. Vote on proposal (coordinator votes on behalf of agents based on findings)
mcp__claude-flow__hive-mind_consensus({
  action: "vote",
  proposalId: "proposal-id",   // from step 9 response
  voterId: "worker-1",
  vote: true                   // true=for, false=against
})

// 11. Check consensus status
mcp__claude-flow__hive-mind_consensus({
  action: "status",
  proposalId: "proposal-id"
})

// 12. Store final results in shared memory
mcp__claude-flow__hive-mind_memory({
  action: "set",
  key: "consensus-result",
  value: { decision: "...", rationale: "..." }
})
```

**Consensus strategies (from source `hive-mind-tools.js`):**
- **bft** — Byzantine Fault Tolerant: requires 2/3 + 1 votes, detects conflicting voters
- **raft** — Simple majority, one vote per node per term, timeout support
- **quorum** — Configurable: `unanimous` (all), `majority` (50%+1), `supermajority` (2/3+1)

---

## Phase 6: Cleanup

```javascript
// 12. Workers leave hive when done
mcp__claude-flow__hive-mind_leave({ agentId: "worker-1" })

// 13. Shutdown hive when all work complete
mcp__claude-flow__hive-mind_shutdown({})
```

---

## Essential Tools Reference

| Tool | Full Name | Purpose |
|------|-----------|---------|
| `hive-mind_init` | `mcp__claude-flow__hive-mind_init` | Initialize hive |
| `hive-mind_spawn` | `mcp__claude-flow__hive-mind_spawn` | Spawn workers |
| `hive-mind_join` | `mcp__claude-flow__hive-mind_join` | Agent joins hive |
| `hive-mind_leave` | `mcp__claude-flow__hive-mind_leave` | Agent leaves hive |
| `hive-mind_broadcast` | `mcp__claude-flow__hive-mind_broadcast` | Send to all agents |
| `hive-mind_memory` | `mcp__claude-flow__hive-mind_memory` | Shared key-value store |
| `hive-mind_consensus` | `mcp__claude-flow__hive-mind_consensus` | Propose/vote/decide |
| `hive-mind_status` | `mcp__claude-flow__hive-mind_status` | Check hive state |
| `hive-mind_shutdown` | `mcp__claude-flow__hive-mind_shutdown` | Terminate hive |

---

## Hive-Mind Specific Rules

- **Always init before spawn** — hive must exist before workers join
- **Use shared memory** (`hive-mind_memory`) for cross-agent state, not individual agent memory
- **Use broadcast** for instructions that all workers need
- **Use consensus** for decisions that require agreement
- **Cleanup:** `leave` workers → `shutdown` hive when done
- **Mesh topology** is the only practical choice for consensus
- **MCP = coordination, Agent tool = execution** — same rule as all systems
- **⛔ Agent prompts MUST include ToolSearch + hive-mind tool usage** — agents will NOT use hive-mind tools unless explicitly told to in their prompt. This is the #1 mistake. Without it, you just have parallel agents, not a hive-mind.
- **⛔ SendMessage does NOT exist** — the Agent tool output suggests "Use SendMessage to continue this agent" but the tool is not available. Agents are fire-and-forget. All instructions must be in the initial prompt. For mid-flight data sharing, agents should read hive-mind memory at BOTH start AND end of their analysis.
- **Scope refinements after launch** — update hive-mind memory keys before the agent reads them. Race condition applies — if the agent already read the key, it won't see updates. Design agents to read shared memory at multiple points (start + before writing findings).

## How It Works (from source code)

All hive-mind state is stored in `.claude-flow/hive-mind/state.json`:

```
{
  initialized: bool,
  topology: "mesh",
  workers: ["agent-id-1", "agent-id-2", ...],
  consensus: { pending: [...], history: [...] },
  sharedMemory: { "key": value, "broadcasts": [...] },
  queen: { agentId, electedAt, term }
}
```

- `hive-mind_memory` reads/writes `state.sharedMemory[key]`
- `hive-mind_broadcast` appends to `state.sharedMemory.broadcasts` array (keeps last 100)
- `hive-mind_spawn` creates agents in both `.claude-flow/agents.json` AND adds to `state.workers`
- `hive-mind_consensus` manages proposals in `state.consensus.pending`, moves to `history` on resolution
- All operations are file I/O — any process calling MCP tools shares the same state file
