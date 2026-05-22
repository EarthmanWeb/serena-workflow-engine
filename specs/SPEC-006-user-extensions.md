# SPEC-006: User-Defined Extensions (JSON/YAML Configuration)

**Version:** 2.0.0
**Status:** Draft
**Date:** 2026-05-20
**Depends on:** SPEC-001, SPEC-002, SPEC-004

---

## 1. Purpose

Define how users can extend the workflow engine with custom states, gates, context templates, and workflow paths using declarative JSON/YAML configuration -- without modifying core plugin code.

## 2. Design Goals

1. **Zero Python required** -- all user customization via config files
2. **Overlay architecture** -- custom configs merge on top of defaults, not replace
3. **Validation on load** -- invalid config is caught early with clear error messages
4. **Project-scoped** -- custom configs live in the project, not the plugin
5. **Schema-documented** -- JSON Schema files enable IDE autocompletion

## 3. Configuration Directory Structure

### 3.1 Plugin Defaults (shipped with plugin)

```
serena-workflow-engine/
  config/
    states.json              # Default 15-state machine
    gates.yml                # Default gates (init, feature_swarm, feature_tests)
    workflows.yml            # Default workflow paths
    context-templates.yml    # Default context output templates
    schema/
      states.schema.json
      gates.schema.json
      workflows.schema.json
      context-templates.schema.json
```

### 3.2 User Overrides (per-project)

```
.serena/
  config/                    # User custom config (project-level)
    states.yml               # Additional/override states
    gates.yml                # Additional/override gates
    workflows.yml            # Additional/override workflow paths
    context-templates.yml    # Override context templates
```

### 3.3 Merge Order

1. Load plugin defaults from `config/`
2. Load user overrides from `.serena/config/`
3. Merge using overlay rules (see section 4)
4. Validate merged result against schema
5. Cache in memory for hook lifetime

## 4. Overlay Merge Rules

### 4.1 States: Deep Merge by ID

User state definitions are merged with defaults by state ID:

**Plugin default:**
```json
{
  "states": {
    "WF_EXECUTE": {
      "id": "WF_EXECUTE",
      "icon": "⚡",
      "description": "Execute implementation changes",
      "allowEdit": true,
      "transitions": {
        "checkpoint_needed": "WF_CHECKPOINT",
        "complete": "WF_VERIFY"
      }
    }
  }
}
```

**User override (`.serena/config/states.yml`):**
```yaml
states:
  # Modify existing state -- only specified fields are overridden
  WF_EXECUTE:
    transitions:
      checkpoint_needed: WF_CHECKPOINT
      complete: WF_VERIFY
      security_scan: WFX_SECURITY_SCAN   # Added transition

  # Add new custom state
  WFX_SECURITY_SCAN:
    id: WFX_SECURITY_SCAN
    category: execution
    icon: "🛡️"
    description: "Run security analysis before verification"
    allowEdit: false
    transitions:
      passed: WF_VERIFY
      issues_found: WF_EXECUTE

transitionMatrix:
  WF_EXECUTE:
    - WF_CHECKPOINT
    - WF_VERIFY
    - WFX_SECURITY_SCAN   # Updated matrix
  WFX_SECURITY_SCAN:
    - WF_VERIFY
    - WF_EXECUTE
```

**Merge result:** WF_EXECUTE keeps all default fields, gains the new `security_scan` transition. WFX_SECURITY_SCAN is added as a new state. The transition matrix is merged.

### 4.2 Gates: Additive Merge by ID

User gate definitions are added to defaults. If a gate ID matches an existing default, the user definition completely replaces it (no deep merge -- gates are atomic units):

**User override:**
```yaml
gates:
  # Override built-in gate (full replacement)
  feature_tests:
    name: "Test Feature Loading"
    description: "Custom test gate for our project"
    matcher: "Bash"
    input_filter:
      field: "command"
      pattern: "(npm\\s+run\\s+test:e2e|cypress)"  # Project-specific
    satisfied_when:
      state_field: "gates_satisfied.feature_tests"
      equals: true
    satisfied_by:
      event: "memory_read"
      condition:
        memory_name: "feature/FEATURE_TESTS"
    deny:
      reason: "Test context not loaded. Read FEATURE_TESTS first."

  # Add entirely new gate
  jira_context:
    name: "Jira Context Gate"
    description: "Require Jira ticket fetch before code research"
    priority: 5
    matcher: "Grep|Glob|Read|Agent"
    active_when:
      state_field: "detected_patterns.jira_tickets"
      not_empty: true
    satisfied_when:
      state_field: "gates_satisfied.jira_context"
      equals: true
    satisfied_by:
      event: "tool_success"
      condition:
        tool_name_pattern: ".*jira.*"
    deny:
      reason: "Jira context required. Fetch {detected_jira} before code research."
```

### 4.3 Context Templates: Override by Key

User templates override specific template keys:

```yaml
# .serena/config/context-templates.yml
templates:
  # Override only session_start template; all others keep defaults
  session_start: |
    {prefix}
    Project: MyApp. Workflow state: {current_state}. WM: {wm_status}.
    Team convention: always fetch Jira context before code research.
```

### 4.4 Workflows: Additive Merge by Name

See section 6 for workflow path definitions.

## 5. Configuration Loader

### 5.1 Module: `swe_hooks/core/config_loader.py`

```python
class ConfigLoader:
    """Loads, merges, and validates configuration from plugin + user."""

    def __init__(self, plugin_root: str, project_root: str):
        """
        Args:
            plugin_root: Path to plugin installation directory
            project_root: Path to project root (.serena/ location)
        """
        self.plugin_config_dir = os.path.join(plugin_root, "config")
        self.user_config_dir = os.path.join(project_root, ".serena", "config")
        self._cache = {}

    def load_states(self) -> dict:
        """Load and merge state machine configuration."""
        if "states" not in self._cache:
            default = self._load_json(self.plugin_config_dir, "states.json")
            override = self._load_yaml(self.user_config_dir, "states.yml")
            merged = self._merge_states(default, override)
            self._validate(merged, "states")
            self._cache["states"] = merged
        return self._cache["states"]

    def load_gates(self) -> dict:
        """Load and merge gate configuration."""
        if "gates" not in self._cache:
            default = self._load_yaml(self.plugin_config_dir, "gates.yml")
            override = self._load_yaml(self.user_config_dir, "gates.yml")
            merged = self._merge_gates(default, override)
            self._validate(merged, "gates")
            self._cache["gates"] = merged
        return self._cache["gates"]

    def load_context_templates(self) -> dict:
        """Load and merge context templates."""
        if "templates" not in self._cache:
            default = self._load_yaml(self.plugin_config_dir, "context-templates.yml")
            override = self._load_yaml(self.user_config_dir, "context-templates.yml")
            merged = self._merge_templates(default, override)
            self._cache["templates"] = merged
        return self._cache["templates"]

    def load_workflows(self) -> dict:
        """Load and merge workflow definitions."""
        if "workflows" not in self._cache:
            default = self._load_yaml(self.plugin_config_dir, "workflows.yml")
            override = self._load_yaml(self.user_config_dir, "workflows.yml")
            merged = self._merge_workflows(default, override)
            self._cache["workflows"] = merged
        return self._cache["workflows"]

    # ── Merge Strategies ────────────────────────────────

    def _merge_states(self, default: dict, override: dict) -> dict:
        """Deep merge states; override fields win for existing states."""
        if not override:
            return default
        result = copy.deepcopy(default)
        for state_id, state_data in override.get("states", {}).items():
            if state_id in result["states"]:
                result["states"][state_id] = deep_merge(
                    result["states"][state_id], state_data
                )
            else:
                result["states"][state_id] = state_data
        # Merge transition matrix
        for from_state, targets in override.get("transitionMatrix", {}).items():
            result["transitionMatrix"][from_state] = targets
        return result

    def _merge_gates(self, default: dict, override: dict) -> dict:
        """Additive merge gates; override replaces by ID."""
        if not override:
            return default
        result = copy.deepcopy(default)
        for gate_id, gate_data in override.get("gates", {}).items():
            result["gates"][gate_id] = gate_data  # Full replacement
        return result

    def _merge_templates(self, default: dict, override: dict) -> dict:
        """Override individual template keys."""
        if not override:
            return default
        result = copy.deepcopy(default)
        for key, template in override.get("templates", {}).items():
            result["templates"][key] = template
        if "prefix" in override:
            result["prefix"] = override["prefix"]
        return result

    # ── Validation ──────────────────────────────────────

    def _validate(self, config: dict, config_type: str):
        """Validate config against JSON Schema."""
        schema_path = os.path.join(
            self.plugin_config_dir, "schema", f"{config_type}.schema.json"
        )
        if os.path.exists(schema_path):
            schema = json.load(open(schema_path))
            validate_config(config, schema)  # Raises on invalid
```

### 5.2 YAML Support

The config loader uses PyYAML (already available via Python stdlib considerations) or falls back to JSON parsing:

```python
def _load_yaml(self, directory: str, filename: str) -> dict:
    """Load YAML or JSON file, returning empty dict if not found."""
    yaml_path = os.path.join(directory, filename)
    json_path = yaml_path.replace('.yml', '.json').replace('.yaml', '.json')

    for path in [yaml_path, json_path]:
        if os.path.exists(path):
            with open(path) as f:
                if path.endswith(('.yml', '.yaml')):
                    import yaml
                    return yaml.safe_load(f) or {}
                else:
                    return json.load(f)
    return {}
```

**Note:** PyYAML is not in Python's stdlib. The plugin should bundle it or declare it as a dependency. Alternatively, users can write config in JSON instead of YAML -- both formats are supported.

## 6. Workflow Path Definitions

### 6.1 Purpose

Workflow paths define named sequences of states that represent common task flows. They serve as documentation and can be used by the compliance checker (SPEC-007) to verify session completeness.

### 6.2 Schema: `config/workflows.yml`

```yaml
version: "2.0.0"

workflows:

  research:
    name: "Research Only"
    description: "Code exploration without changes"
    path:
      - WF_START
      - WF_RESEARCH
      - WF_DONE
    required_gates: [init]

  standard:
    name: "Standard Development"
    description: "Full planning + implementation cycle"
    path:
      - WF_START
      - WF_CLASSIFY
      - WF_ARCH_REVIEW
      - WF_EXECUTE
      - WF_VERIFY
      - WF_DONE
    required_gates: [init]
    optional_states: [WF_CHECKPOINT, WF_DEBUG_TDD, WF_CLARIFY]

  quick_fix:
    name: "Quick Fix"
    description: "Operational task without architecture review"
    path:
      - WF_START
      - WF_CLASSIFY
      - WF_EXECUTE
      - WF_VERIFY
      - WF_DONE
    required_gates: [init]
    conditions:
      classification: "operational"

  swarm:
    name: "Swarm Orchestration"
    description: "Multi-agent coordination for large tasks"
    path:
      - WF_START
      - WF_CLASSIFY
      - WF_ARCH_REVIEW
      - WF_SWARM_ORCHESTRATE
      - WF_EXECUTE
      - WF_VERIFY
      - WF_DONE
    required_gates: [init, feature_swarm]

  debug:
    name: "Test-Driven Debug"
    description: "Debug workflow using TDD approach"
    path:
      - WF_START
      - WF_CLASSIFY
      - WF_DEBUG_TDD
      - WF_EXECUTE
      - WF_VERIFY
      - WF_DONE
    required_gates: [init]
```

### 6.3 User-Defined Workflows

Users can add custom workflows:

```yaml
# .serena/config/workflows.yml
workflows:
  security_review:
    name: "Security Review Pipeline"
    description: "Full review with security scan before verification"
    path:
      - WF_START
      - WF_CLASSIFY
      - WF_ARCH_REVIEW
      - WF_EXECUTE
      - WFX_SECURITY_SCAN
      - WF_VERIFY
      - WF_DONE
    required_gates: [init, security_tools_available]
```

## 7. Pattern Detection Configuration

### 7.1 Purpose

Users can define patterns that are detected in user prompts (UserPromptSubmit) and stored in the state store's `detected_patterns` field. Gates can then condition on these patterns.

### 7.2 Configuration

Added to `config/gates.yml` or as a separate `config/patterns.yml`:

```yaml
patterns:

  jira_tickets:
    description: "Detect Jira ticket references in user prompts"
    regex: "\\b([A-Z]{2,10}-\\d{1,6})\\b"
    extract: "all_matches"    # Store all matches as list
    store_as: "detected_patterns.jira_tickets"
    example: "Fix bug SPS-755"

  swarm_keywords:
    description: "Detect swarm/multi-agent keywords"
    regex: "\\b(swarm|multi-agent|hive|orchestrat|parallel\\s+agents?)\\b"
    extract: "boolean"        # Store as true/false
    store_as: "detected_patterns.swarm_keywords"
    case_insensitive: true

  deployment_target:
    description: "Detect deployment target mentions"
    regex: "\\b(staging|production|dev|qa)\\b"
    extract: "first_match"    # Store first match
    store_as: "detected_patterns.deployment_target"
    case_insensitive: true
```

### 7.3 Pattern Detection Flow

1. UserPromptSubmit hook fires with user's prompt text
2. Pattern engine iterates `patterns` config
3. For each matching pattern, stores result in state store
4. Gates with `active_when` conditions on `detected_patterns` activate

## 8. Scaffolding Command

### 8.1 `swe-scaffold-config` Command

A skill/command that generates user config files with documentation:

```bash
# Creates .serena/config/ with annotated template files
swe-scaffold-config
```

Generates:
```
.serena/config/
  states.yml         # Annotated with all overridable fields
  gates.yml          # Template with example custom gate
  workflows.yml      # Template with example custom workflow
  context-templates.yml  # Template with all template keys
  patterns.yml       # Template with example patterns
  README.md          # Usage documentation
```

Each generated file includes extensive comments explaining:
- Available fields and their types
- Default values
- Examples of common customizations
- Links to spec documentation

## 9. Validation Error Reporting

When config validation fails, errors are reported clearly:

```
SWE Config Error: .serena/config/gates.yml
  Gate 'jira_context':
    - 'satisfied_when.state_field' references unknown field 'detected_patterns.jira'
      Valid fields: detected_patterns.jira_tickets, detected_patterns.swarm_keywords
    - 'depends_on' references unknown gate 'jira_setup'
      Available gates: init, feature_swarm, feature_tests

  Falling back to plugin defaults.
```

Validation errors are:
1. Logged to stderr (shown in debug mode)
2. Emitted as `additionalContext` in SessionStart (so Claude is aware)
3. Non-fatal -- system falls back to defaults

## 10. Security Considerations

### 10.1 Config Injection Prevention

- YAML `safe_load` only (no arbitrary Python execution)
- Regex patterns are compiled with timeout protection
- Template variables use `.format()` with explicit variable mapping (no `eval`)
- Config file paths are resolved relative to known directories only

### 10.2 User Config Scope

User configs in `.serena/config/` can:
- Add new states, gates, workflows, patterns, templates
- Override existing gate definitions
- Override individual state fields
- Override context templates

User configs CANNOT:
- Disable the init gate (hardcoded minimum enforcement)
- Remove built-in states (only override their properties)
- Execute arbitrary code
- Access files outside the project directory
