# SPEC-005: Session & State Management Refactor

**Version:** 2.0.0
**Status:** Draft
**Date:** 2026-05-20
**Depends on:** SPEC-001, SPEC-002, SPEC-004

---

## 1. Purpose

Consolidate session state management into a single, well-defined **State Store** that replaces:
- Scattered sentinel files (`.init_{id}`, `.swarm_feature_{id}`, `.test_feature_{id}`)
- Dual-layer state persistence (WM markdown parsing + decoupled `.state` files)
- In-memory state in `StateManager` class

The State Store becomes the **single source of truth** for all hook decisions.

## 2. Current Problems

### 2.1 State is Scattered Across Multiple Mechanisms

| Mechanism | What It Tracks | Format |
|---|---|---|
| `.serena/swe-state/{id}.state` | Current/previous state | Plain text key-value |
| `.serena/memories/WM_{id}.md` | State embedded in `**Current State**:` field | Markdown (regex-parsed) |
| `.serena/streams/.init_{id}` | Whether WF_INIT is complete | Sentinel file existence |
| `.serena/streams/.swarm_feature_{id}` | Whether FEATURE_SWARM was read | Sentinel file existence |
| `.serena/streams/.test_feature_{id}` | Whether FEATURE_TESTS was read | Sentinel file existence |
| `StateManager.state` dict | In-memory edit counter, plan mode | Python dict (ephemeral) |

### 2.2 Race Conditions and Inconsistency

The WM file is both a user-facing document (Claude reads/writes it) and a state tracking mechanism (hooks parse `**Current State**:`). When Claude writes to the WM via MCP, the hook may read stale data if the MCP hasn't flushed yet.

### 2.3 Complex Initialization Flow

The init gate checks sentinel files, falls back to WM parsing, falls back to state files -- a fragile chain that breaks when any link is missing.

## 3. State Store Design

### 3.1 Single JSON File Per Session

Location: `.serena/swe-state/{session_id}.json`

```json
{
  "schema_version": "2.0.0",
  "session_id": "00893aaf",

  "state": {
    "current": "WF_CLASSIFY",
    "previous": "WF_START",
    "history": ["WF_INIT", "WF_START", "WF_CLASSIFY"]
  },

  "timestamps": {
    "created": "2026-05-20T10:30:00Z",
    "updated": "2026-05-20T10:35:00Z",
    "last_transition": "2026-05-20T10:35:00Z"
  },

  "working_memory": {
    "file": "WM_00893aaf.md",
    "exists": true
  },

  "gates_satisfied": {
    "init": true,
    "feature_swarm": false,
    "feature_tests": false
  },

  "detected_patterns": {
    "jira_tickets": [],
    "swarm_keywords": false
  },

  "counters": {
    "edits_since_checkpoint": 0,
    "total_edits": 0,
    "total_transitions": 3
  },

  "flags": {
    "plan_mode": false,
    "setup_complete": true,
    "archived": false
  },

  "custom": {}
}
```

### 3.2 Schema Fields

| Path | Type | Description |
|---|---|---|
| `schema_version` | string | State store schema version |
| `session_id` | string | Session identifier (8 char UUID prefix) |
| `state.current` | string | Current workflow state |
| `state.previous` | string | Previous workflow state |
| `state.history` | string[] | Ordered list of all states visited |
| `timestamps.created` | ISO 8601 | When session state was created |
| `timestamps.updated` | ISO 8601 | Last modification time |
| `timestamps.last_transition` | ISO 8601 | Last state transition time |
| `working_memory.file` | string | WM filename |
| `working_memory.exists` | boolean | Whether WM file exists on disk |
| `gates_satisfied` | object | Map of gate_id -> boolean |
| `detected_patterns` | object | Patterns detected in user prompts |
| `counters.*` | integer | Various counters |
| `flags.*` | boolean | Boolean flags |
| `custom` | object | User-defined custom data |

### 3.3 The `custom` Field

Users can store arbitrary data in the `custom` field via gate `satisfied_by` events or custom hooks. This provides extensibility without schema changes:

```json
{
  "custom": {
    "jira_ticket_data": { "key": "SPS-755", "status": "In Progress" },
    "last_test_result": "pass",
    "deployment_target": "staging"
  }
}
```

## 4. StateStore Module

### 4.1 Module: `swe_hooks/core/state_store.py`

```python
class StateStore:
    """Single source of truth for session state.

    Reads and writes .serena/swe-state/{session_id}.json.
    All hook scripts use this instead of sentinel files or WM parsing.
    """

    def __init__(self, session_id: str, cwd: str = None):
        """Load or create state store for session.

        Args:
            session_id: Session identifier
            cwd: Working directory (for locating .serena/)
        """
        self.session_id = session_id
        self.cwd = cwd or os.getcwd()
        self.path = self._state_path()
        self.data = self._load_or_create()

    @property
    def current_state(self) -> str:
        return self.data["state"]["current"]

    @property
    def previous_state(self) -> str:
        return self.data["state"]["previous"]

    @property
    def completed_steps(self) -> list:
        return self.data["state"]["history"]

    def is_gate_satisfied(self, gate_id: str) -> bool:
        return self.data["gates_satisfied"].get(gate_id, False)

    def satisfy_gate(self, gate_id: str):
        self.data["gates_satisfied"][gate_id] = True
        self._save()

    def reset_gate(self, gate_id: str):
        self.data["gates_satisfied"][gate_id] = False
        self._save()

    def transition_to(self, new_state: str) -> bool:
        """Record a state transition.

        Updates current/previous state, appends to history,
        updates timestamps. Does NOT validate -- validation
        is done by the state engine before calling this.
        """
        self.data["state"]["previous"] = self.data["state"]["current"]
        self.data["state"]["current"] = new_state
        self.data["state"]["history"].append(new_state)
        self.data["timestamps"]["updated"] = now_iso()
        self.data["timestamps"]["last_transition"] = now_iso()
        self.data["counters"]["total_transitions"] += 1
        self._save()
        return True

    def set_detected_pattern(self, key: str, value):
        self.data["detected_patterns"][key] = value
        self._save()

    def increment_edits(self) -> int:
        self.data["counters"]["edits_since_checkpoint"] += 1
        self.data["counters"]["total_edits"] += 1
        self._save()
        return self.data["counters"]["edits_since_checkpoint"]

    def reset_edit_counter(self):
        self.data["counters"]["edits_since_checkpoint"] = 0
        self._save()

    def set_flag(self, flag: str, value: bool):
        self.data["flags"][flag] = value
        self._save()

    def get_flag(self, flag: str) -> bool:
        return self.data["flags"].get(flag, False)

    def set_custom(self, key: str, value):
        self.data["custom"][key] = value
        self._save()

    def get_custom(self, key: str, default=None):
        return self.data["custom"].get(key, default)

    # ── Template variables ──────────────────────────────

    def to_template_vars(self) -> dict:
        """Return dict of all template variables for context rendering."""
        return {
            "session_id": self.session_id,
            "current_state": self.current_state,
            "previous_state": self.previous_state,
            "completed_steps": ", ".join(self.completed_steps),
            "wm_status": self.wm_status(),
            "wm_file": self.data["working_memory"]["file"] or "none",
            "satisfied_gates": ", ".join(self.satisfied_gates()),
            "detected_patterns": self._format_detected_patterns(),
            "required_steps": self._compute_required_steps(),
            "detected_jira": ", ".join(self.data["detected_patterns"].get("jira_tickets", [])),
            "edit_count": str(self.data["counters"]["edits_since_checkpoint"]),
        }

    def wm_status(self) -> str:
        wm = self.data["working_memory"]
        if wm["exists"] and wm["file"]:
            return f"exists ({wm['file']})"
        return "not created"

    def satisfied_gates(self) -> list:
        return [k for k, v in self.data["gates_satisfied"].items() if v]

    # ── Private ─────────────────────────────────────────

    def _state_path(self) -> str:
        return os.path.join(self.cwd, ".serena", "swe-state",
                           f"{self.session_id}.json")

    def _load_or_create(self) -> dict:
        if os.path.exists(self.path):
            with open(self.path) as f:
                return json.load(f)
        return self._create_default()

    def _create_default(self) -> dict:
        data = {
            "schema_version": "2.0.0",
            "session_id": self.session_id,
            "state": {
                "current": "WF_INIT",
                "previous": None,
                "history": []
            },
            "timestamps": {
                "created": now_iso(),
                "updated": now_iso(),
                "last_transition": None
            },
            "working_memory": {
                "file": None,
                "exists": False
            },
            "gates_satisfied": {},
            "detected_patterns": {
                "jira_tickets": [],
                "swarm_keywords": False
            },
            "counters": {
                "edits_since_checkpoint": 0,
                "total_edits": 0,
                "total_transitions": 0
            },
            "flags": {
                "plan_mode": False,
                "setup_complete": False,
                "archived": False
            },
            "custom": {}
        }
        self._ensure_dir()
        self._write(data)
        return data

    def _save(self):
        self.data["timestamps"]["updated"] = now_iso()
        self._write(self.data)

    def _write(self, data):
        with open(self.path, 'w') as f:
            json.dump(data, f, indent=2)

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
```

## 5. State Engine (Refactored StateManager)

### 5.1 Module: `swe_hooks/core/state_engine.py`

The current `StateManager` is refactored into `StateEngine` with clear responsibilities:

```python
class StateEngine:
    """Validates state transitions and updates state store.

    Responsibilities:
    - Validate transitions against states.json matrix
    - Update state store on valid transitions
    - Satisfy gates based on transition events
    - Emit factual context for transitions

    Does NOT:
    - Parse WM markdown files (state store is source of truth)
    - Manage sentinel files (replaced by state store gates)
    - Emit imperative instructions
    """

    def __init__(self, config_dir: str, state_store: StateStore):
        self.states_config = load_states(config_dir)
        self.gates_config = load_gates(config_dir)
        self.store = state_store

    def transition(self, new_state: str, force: bool = False) -> TransitionResult:
        """Validate and execute a state transition.

        Returns TransitionResult with success/failure and context.
        """
        old_state = self.store.current_state

        # Validate
        if not force:
            valid, error = is_valid_transition(
                old_state, new_state, self.states_config
            )
            if not valid:
                return TransitionResult(success=False, error=error)

        # Execute
        self.store.transition_to(new_state)

        # Handle state-level hooks
        self._execute_on_enter(new_state)
        self._execute_on_exit(old_state)

        # Check if this transition satisfies any gates
        self._check_gate_satisfaction("state_transition", {
            "new_state": new_state,
            "old_state": old_state
        })

        return TransitionResult(
            success=True,
            old_state=old_state,
            new_state=new_state,
            context=self._build_transition_context(old_state, new_state)
        )

    def on_memory_read(self, memory_name: str):
        """Handle memory read events for gate satisfaction."""
        self._check_gate_satisfaction("memory_read", {
            "memory_name": memory_name
        })

    def on_tool_success(self, tool_name: str, tool_input: dict,
                        tool_result: str = ""):
        """Handle tool success events for gate satisfaction."""
        self._check_gate_satisfaction("tool_success", {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_result": tool_result
        })

    def _check_gate_satisfaction(self, event_type: str, event_data: dict):
        """Check all gates' satisfied_by conditions against event."""
        for gate_id, gate in self.gates_config.items():
            if self.store.is_gate_satisfied(gate_id):
                continue
            satisfied_by = gate.get("satisfied_by", {})
            if satisfied_by.get("event") != event_type:
                continue
            condition = satisfied_by.get("condition", {})
            if self._evaluate_satisfaction(condition, event_data):
                self.store.satisfy_gate(gate_id)

    def _execute_on_enter(self, state: str):
        """Execute declarative onEnter hooks for a state."""
        hooks = self.states_config.get("hooks", {}).get("onEnter", {})
        actions = hooks.get(state, {})
        if actions.get("enablePlanMode"):
            self.store.set_flag("plan_mode", True)
        if actions.get("disablePlanMode"):
            self.store.set_flag("plan_mode", False)
        if actions.get("resetEditCounter"):
            self.store.reset_edit_counter()
        if actions.get("archiveSession"):
            self.store.set_flag("archived", True)
        sentinel = actions.get("createSentinel")
        if sentinel:
            self.store.satisfy_gate(sentinel)
```

## 6. Working Memory Interaction

### 6.1 WM is a User-Facing Document, Not a State Store

In v2, the WM file (`WM_{session_id}.md`) is purely a user-facing artifact:
- Claude writes context, progress, and notes into it
- Hooks do NOT parse it for state (state store is authoritative)
- The `**Current State**:` field in the WM is updated as a **courtesy** by the state engine after transitions, but is never read by hooks

### 6.2 WM Creation

WM creation is triggered by the state engine when transitioning to WF_START:

```python
# In state_engine.py
def _execute_on_enter(self, state):
    if state == "WF_START" and not self.store.data["working_memory"]["exists"]:
        wm_file = f"WM_{self.store.session_id}.md"
        self._create_wm_file(wm_file)
        self.store.data["working_memory"]["file"] = wm_file
        self.store.data["working_memory"]["exists"] = True
        self.store._save()
```

### 6.3 WM State Field Update (Courtesy Only)

After a state transition, the state engine updates the `**Current State**:` field in the WM file as a non-authoritative mirror. This is for human readability and Claude's reference, not for hook logic:

```python
def _update_wm_state_field(self, new_state: str):
    """Update the Current State field in WM for readability.

    This is a courtesy update. The authoritative state is in
    the state store JSON file. Hooks never read this field.
    """
    wm_path = self._get_wm_path()
    if not wm_path or not os.path.exists(wm_path):
        return
    # Simple regex replace of **Current State**: value
    content = open(wm_path).read()
    content = re.sub(
        r'\*\*Current State\*\*:\s*\S+',
        f'**Current State**: {new_state}',
        content
    )
    with open(wm_path, 'w') as f:
        f.write(content)
```

## 7. Session Lifecycle

### 7.1 Session Creation

```
SessionStart hook fires
  → Extract session_id from transcript_path
  → StateStore(session_id) creates default state file
  → Emit factual context: "Workflow state: WF_INIT. WM: not created."
```

### 7.2 Initialization (WF_INIT → WF_START)

```
Claude reads WF_INIT memory
  → PostToolUse fires
  → State engine detects WF_INIT read
  → (No state transition yet -- WF_INIT is not a state in the transition matrix,
     it's the default starting position)

Claude reads WF_START memory
  → PostToolUse fires
  → State engine transitions WF_INIT → WF_START
  → State store updated: state.current = "WF_START", history = ["WF_INIT", "WF_START"]
  → Init gate satisfied: gates_satisfied.init = true
  → WM file created: WM_{session_id}.md
  → Context emitted: "Transition: WF_INIT -> WF_START. ..."
```

### 7.3 Gate Unlocking

```
Claude reads FEATURE_SWARM memory
  → PostToolUse fires
  → State engine on_memory_read("feature/FEATURE_SWARM")
  → feature_swarm gate condition matches
  → State store: gates_satisfied.feature_swarm = true
```

### 7.4 New Task in Same Session

```
WF_DONE reached, user submits new task
  → UserPromptSubmit fires
  → State store: state.current = "WF_DONE"
  → Prompt context hook detects new task pattern
  → State engine transitions WF_DONE → WF_CLASSIFY
  → Gates with reset_on conditions are reset
  → Context: "Session 00893aaf state: WF_CLASSIFY. New task in existing session."
```

### 7.5 Session Archival

```
Stop hook fires with state = WF_DONE
  → Compliance passes
  → State store: flags.archived = true
```

## 8. Sentinel File Elimination

All sentinel files are replaced by `gates_satisfied` in the state store:

| Old Sentinel | New State Store Field |
|---|---|
| `.serena/streams/.init_{id}` | `gates_satisfied.init` |
| `.serena/streams/.swarm_feature_{id}` | `gates_satisfied.feature_swarm` |
| `.serena/streams/.test_feature_{id}` | `gates_satisfied.feature_tests` |

The `.serena/streams/` directory continues to hold JSONL audit logs (unchanged).

## 9. Backward Compatibility

### 9.1 Migration

On first load, `StateStore._load_or_create()` checks for legacy state files:

```python
def _migrate_legacy(self):
    """Migrate from v1 sentinel + state file format."""
    # Check for legacy .state file
    legacy_path = self.path.replace('.json', '.state')
    if os.path.exists(legacy_path):
        legacy = read_legacy_state(legacy_path)
        self.data["state"]["current"] = legacy.get("current_state", "WF_INIT")
        self.data["state"]["previous"] = legacy.get("prev", None)

    # Check for sentinel files
    streams_dir = os.path.join(self.cwd, ".serena", "streams")
    if os.path.exists(os.path.join(streams_dir, f".init_{self.session_id}")):
        self.data["gates_satisfied"]["init"] = True
    if os.path.exists(os.path.join(streams_dir, f".swarm_feature_{self.session_id}")):
        self.data["gates_satisfied"]["feature_swarm"] = True
    if os.path.exists(os.path.join(streams_dir, f".test_feature_{self.session_id}")):
        self.data["gates_satisfied"]["feature_tests"] = True

    self._save()
```

### 9.2 Deprecation Timeline

- **Phase 1 (v2.0):** State store is authoritative; legacy files read during migration
- **Phase 2 (v2.1):** Legacy sentinel file creation removed; migration still reads them
- **Phase 3 (v3.0):** Legacy support removed entirely
