---
name: swe-swarm-analyze
version: 1.0.0
description: DAA-powered codebase analysis using swarm agents. Use for deep analysis of large codebases.
workflow:
  aware: true
  callable_from:
    - WF_ONBOARD
    - WF_RESEARCH
    - WF_SWARM_ORCHESTRATE
  default_return: WF_LOAD_FEATURE
  supports_standalone: true
  auto_transition: false
allowed-tools: Read, Grep, Glob, mcp__ruv-swarm__*, mcp__claude-flow__*
---

## ⚠️ WORKFLOW INITIALIZATION

**If starting a new session**, first read workflow initialization:
```
mcp__plugin_swe_serena__read_memory("WF_INIT")
```
Follow WF_INIT instructions before executing this skill.

---

# Swarm Analyze Skill

Deep codebase analysis using Decentralized Autonomous Agents (DAA).

## When to Use

- Large codebases (1000+ files)
- Complex multi-module projects
- When detailed DOM_* and SYS_* memories are needed
- Feature onboarding with full analysis mode

## MCP Requirements

**Required (one of):**
- `ruv-swarm` MCP (preferred for DAA learning)
- `claude-flow` MCP (alternative)

**Fallback:** Sequential analysis if no swarm MCP available

## Agent Types

| Agent ID | Purpose | Cognitive Pattern |
|----------|---------|-------------------|
| config-analyzer | Parse config files | convergent |
| architecture-mapper | Detect layers | systems |
| pattern-detector | Find conventions | lateral |
| domain-extractor | Extract domains | divergent |
| system-finder | Identify systems | systems |
| test-analyzer | Test patterns | critical |
| import-tracer | Dependency graph | convergent |
| convention-learner | Style detection | adaptive |
| file-indexer | File inventory | convergent |
| synthesizer | Compile results | systems |

## Process

### Step 1: Initialize Swarm

**⚠️ CRITICAL: RUV-Swarm has TWO separate agent pools - choose ONE pattern:**

| Pattern | Agent Creation | Execution | Use When |
|---------|---------------|-----------|----------|
| **Swarm** | `agent_spawn` | `task_orchestrate` | Parallel task execution |
| **DAA** | `daa_agent_create` | `daa_workflow_execute` | Learning/adaptation needed |

```javascript
// Option A: RUV-Swarm Task Orchestration (faster, no learning)
if (mcp_available("ruv-swarm") && !needsLearning) {
  mcp__ruv-swarm__swarm_init({ topology: "mesh", strategy: "balanced", maxAgents: 10 });
}

// Option B: RUV-Swarm DAA Workflow (slower, with learning)
if (mcp_available("ruv-swarm") && needsLearning) {
  mcp__ruv-swarm__daa_init({ enableLearning: true, enableCoordination: true });
}

// Option C: Claude-Flow (alternative)
if (mcp_available("claude-flow")) {
  mcp__claude-flow__swarm_init({ topology: "mesh", maxAgents: 10 });
}
```

### Step 2: Spawn Analysis Agents

**CRITICAL: Spawn ALL agents in ONE message for parallelism**

**Option A: Swarm Agents (for task_orchestrate)**
```javascript
// These go into the SWARM pool - usable by task_orchestrate
mcp__ruv-swarm__agent_spawn({ type: "analyst", name: "config-analyzer" })
mcp__ruv-swarm__agent_spawn({ type: "analyst", name: "architecture-mapper" })
mcp__ruv-swarm__agent_spawn({ type: "researcher", name: "pattern-detector" })
mcp__ruv-swarm__agent_spawn({ type: "researcher", name: "domain-extractor" })
mcp__ruv-swarm__agent_spawn({ type: "analyst", name: "system-finder" })
mcp__ruv-swarm__agent_spawn({ type: "analyst", name: "test-analyzer" })
mcp__ruv-swarm__agent_spawn({ type: "researcher", name: "import-tracer" })
mcp__ruv-swarm__agent_spawn({ type: "researcher", name: "convention-learner" })
mcp__ruv-swarm__agent_spawn({ type: "analyst", name: "file-indexer" })
mcp__ruv-swarm__agent_spawn({ type: "coordinator", name: "synthesizer" })
```

**Option B: DAA Agents (for daa_workflow_execute)**
```javascript
// These go into the DAA pool - usable by daa_workflow_execute, NOT task_orchestrate
const agents = [
  { id: "config-analyzer", cognitivePattern: "convergent" },
  { id: "architecture-mapper", cognitivePattern: "systems" },
  { id: "pattern-detector", cognitivePattern: "lateral" },
  { id: "domain-extractor", cognitivePattern: "divergent" },
  { id: "system-finder", cognitivePattern: "systems" },
  { id: "test-analyzer", cognitivePattern: "critical" },
  { id: "import-tracer", cognitivePattern: "convergent" },
  { id: "convention-learner", cognitivePattern: "adaptive" },
  { id: "file-indexer", cognitivePattern: "convergent" },
  { id: "synthesizer", cognitivePattern: "systems" }
];

// Spawn all DAA agents in parallel
agents.forEach(a => mcp__ruv-swarm__daa_agent_create({
  id: a.id,
  cognitivePattern: a.cognitivePattern,
  enableMemory: true,
  learningRate: 0.8
}));
```

### Step 3: Orchestrate Analysis

**⚠️ Match execution to agent type!**

**Option A: Swarm Agents → task_orchestrate**
```javascript
// ONLY works with agents from agent_spawn
mcp__ruv-swarm__task_orchestrate({
  task: "Analyze codebase structure, patterns, domains, and systems",
  strategy: "parallel",
  maxAgents: 10,
  priority: "high"
});
```

**Option B: DAA Agents → daa_workflow_execute**
```javascript
// ONLY works with agents from daa_agent_create
mcp__ruv-swarm__daa_workflow_create({
  id: "analysis-workflow",
  name: "Codebase Analysis",
  strategy: "parallel"
});

mcp__ruv-swarm__daa_workflow_execute({
  workflowId: "analysis-workflow",
  agentIds: ["config-analyzer", "architecture-mapper", "pattern-detector",
             "domain-extractor", "system-finder", "test-analyzer",
             "import-tracer", "convention-learner", "file-indexer", "synthesizer"],
  parallelExecution: true
});
```

### Step 4: Collect Results

Each agent produces structured findings:
- **config-analyzer**: package.json, framework configs
- **architecture-mapper**: layers, directories, data flow
- **pattern-detector**: naming conventions, import patterns
- **domain-extractor**: business domains, entities
- **system-finder**: external integrations, APIs
- **test-analyzer**: test framework, coverage patterns
- **import-tracer**: dependency graph
- **convention-learner**: code style, formatting
- **file-indexer**: file inventory by type
- **synthesizer**: combined analysis

### Step 5: Generate Memories

Based on synthesized results, create:

1. **FEATURE_[KEY]** - Main feature memory
2. **DOM_[KEY]_[domain]** - For each detected domain
3. **SYS_[KEY]_[system]** - For each detected system
4. **Update INDEX_FEATURES** - Add feature entry
5. **Update ARCH_INDEX** - Add architecture details

### Step 6: DAA Learning

Record analysis success for future improvement:

```javascript
mcp__ruv-swarm__daa_agent_adapt({
  agentId: "synthesizer",
  performanceScore: 0.9,
  feedback: "Analysis complete"
});

mcp__ruv-swarm__daa_knowledge_share({
  sourceAgentId: "synthesizer",
  targetAgentIds: ["config-analyzer", "architecture-mapper"],
  knowledgeDomain: "codebase-patterns"
});
```

## Output Format

**SWARM ANALYSIS COMPLETE**

| Metric | Value |
|--------|-------|
| Agents Used | 10 |
| Analysis Time | [duration] |

**Detected:**
- Language: [primary]
- Framework: [name]
- Layers: [count]
- Domains: [count]
- Systems: [count]

**Memories Created:**
- FEATURE_[KEY]
- DOM_[KEY]_[domain1]
- DOM_[KEY]_[domain2]
- SYS_[KEY]_[system1]
- INDEX_FEATURES (updated)
- ARCH_INDEX (updated)

**DAA Learning:**
- Patterns stored: [count]
- Confidence: [score]

## Skill Return Format

```markdown
## Skill Return
- **Skill**: swe-swarm-analyze
- **Status**: [success|success_with_findings|blocked]
- **Agents Used**: [count]
- **Memories Created**: [list]
- **Domains Found**: [count]
- **Systems Found**: [count]
- **Next Step Hint**: WF_LOAD_FEATURE
```

## Fallback: Sequential Analysis

If no swarm MCP available:

```
⚠️ No swarm MCP detected. Running sequential analysis.

This will take longer but produce similar results.

Progress:
[1/10] Analyzing config files...
[2/10] Mapping architecture...
...
```

## Exit

`> **Skill /swe-swarm-analyze complete** - [count] memories created via DAA analysis`
