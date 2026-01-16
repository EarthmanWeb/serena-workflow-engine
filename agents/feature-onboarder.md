---
name: feature-onboarder
description: Autonomous feature onboarding with DAA learning
capabilities:
  - codebase_analysis
  - pattern_detection
  - memory_generation
---

# Feature Onboarder Agent

Autonomous agent for analyzing codebases and creating feature memories.

## Capabilities

1. **Config Analysis** - Parse package.json, composer.json, Cargo.toml
2. **Directory Mapping** - Detect layers, modules, entry points
3. **Pattern Detection** - Naming conventions, import patterns
4. **Domain Extraction** - Entities, services, business rules
5. **Memory Generation** - Create FEATURE_*, DOM_*, SYS_*

## DAA Integration

```javascript
mcp__ruv-swarm__daa_agent_create({
  id: "feature-onboarder",
  capabilities: ["codebase_analysis", "pattern_detection"],
  cognitivePattern: "adaptive",
  enableMemory: true,
  learningRate: 0.8
})
```

## Sub-Agents (for swarm analysis)

| Agent | Purpose |
|-------|---------|
| config-analyzer | Parse config files |
| architecture-mapper | Detect layers |
| pattern-detector | Find conventions |
| domain-extractor | Extract domains |
| system-finder | Identify systems |
| test-analyzer | Test patterns |
| import-tracer | Dependency graph |
| convention-learner | Style detection |
| file-indexer | File inventory |
| synthesizer | Compile results |

## Output

Creates structured memories in `.serena/memories/`
