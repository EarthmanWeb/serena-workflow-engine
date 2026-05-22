# SPEC-008: Migration & Compatibility Plan

**Version:** 2.0.0
**Status:** Draft
**Date:** 2026-05-20
**Depends on:** SPEC-001 through SPEC-007

---

## 1. Purpose

Define the incremental migration path from v1 (current imperative hook architecture) to v2 (factual context + declarative gate engine). The migration must:
- Not break existing installations mid-session
- Allow rollback if issues are discovered
- Be executable in phases (not all-at-once)
- Preserve session state across the upgrade

## 2. Migration Phases

### Phase 0: Pre-Migration (No Code Changes)
### Phase 1: Foundation (State Store + Config Loader)
### Phase 2: Gate Engine (Replace Gate Scripts)
### Phase 3: Context Rewrite (Factual Output)
### Phase 4: Stop Hook Enhancement
### Phase 5: Cleanup (Remove Legacy)

---

## 3. Phase 0: Pre-Migration

**Goal:** Validate assumptions and prepare the codebase.

### 3.1 Tasks

| # | Task | Risk | Notes |
|---|---|---|---|
| 0.1 | Verify plugin hooks fire in VSCode extension | Critical | If they don't, document CLI requirement or explore alternatives |
| 0.2 | Add PyYAML dependency (or confirm available) | Low | Needed for YAML config support |
| 0.3 | Create `config/` directory structure | None | No functional changes |
| 0.4 | Create JSON Schema files for validation | None | Documentation + validation prep |
| 0.5 | Write integration tests for current hook behavior | Medium | Baseline for regression testing |
| 0.6 | Copy `state-machine/states.json` to `config/states.json` | None | Dual location temporarily |

### 3.2 Verification: VSCode Extension Hooks

**This is the most critical pre-migration task.** If plugin hooks don't fire in VSCode extension mode, the entire architecture needs reconsideration.

Test procedure:
1. Install plugin in VSCode extension mode
2. Start a session
3. Check if SessionStart hook fires (look for output in Claude's context)
4. Check if PreToolUse hooks fire (try to use a tool and see if gates apply)

**If hooks don't fire in extension mode:**
- Document that hook-gated workflows require CLI mode (`claude` in terminal)
- Add a CLAUDE.md-based fallback with workflow instructions (advisory, not enforced)
- Consider MCP-tool-based alternatives for critical gates

### 3.3 Deliverables

- Test report: hooks in VSCode extension ✓/✗
- `config/` directory with schema files
- Integration test suite for v1 behavior
- Dependency manifest updated (PyYAML if needed)

---

## 4. Phase 1: Foundation

**Goal:** Introduce StateStore and ConfigLoader alongside existing code. No behavior changes.

### 4.1 New Files

```
hooks/swe_hooks/core/
  state_store.py        # NEW: JSON state store
  config_loader.py      # NEW: YAML/JSON config loader
  context_engine.py     # NEW: factual context builder

config/
  states.json           # COPIED from state-machine/
  gates.yml             # NEW: gate definitions (matching current behavior)
  context-templates.yml # NEW: context templates
  workflows.yml         # NEW: workflow path definitions
  schema/               # NEW: JSON Schema files
```

### 4.2 Dual-Write Strategy

During Phase 1, the existing hooks write to BOTH the old mechanisms AND the new state store:

```python
# In swe_post_read_state.py (existing hook)
# ... existing logic unchanged ...

# NEW: Also write to state store
from swe_hooks.core.state_store import StateStore
try:
    store = StateStore(session_id)
    store.transition_to(new_state)
    if new_state in ("WF_START", "WF_CLASSIFY", "WF_RESEARCH", "WF_CONTINUE"):
        store.satisfy_gate("init")
except Exception:
    pass  # Non-fatal: state store is secondary during Phase 1
```

### 4.3 Validation

- State store JSON files are created alongside sentinel files
- State store contents can be compared against sentinel files for consistency
- No existing behavior changes -- old hooks still drive all decisions

### 4.4 Deliverables

- `state_store.py` with full API
- `config_loader.py` with merge logic
- `context_engine.py` with template rendering
- Config files with default definitions
- Dual-write in existing hooks (behind try/except)

---

## 5. Phase 2: Gate Engine

**Goal:** Replace three PreToolUse gate scripts with the generic gate engine.

### 5.1 Changes

1. Create `hooks/pre/swe_gate_engine.py` (new generic gate script)
2. Create `config/gates.yml` with definitions matching current gate behavior
3. Update `hooks/hooks.json` to use single gate engine entry
4. Keep old gate scripts as fallback (not wired in hooks.json)

### 5.2 hooks.json Change

**Before:**
```json
{
  "PreToolUse": [
    { "matcher": ".*", "hooks": [{ "command": "...swe_pre_tool_init_gate.py" }] },
    { "matcher": "mcp__ruv-swarm__swarm_init", "hooks": [{ "command": "...swe_pre_swarm_feature_gate.py" }] },
    { "matcher": "Bash", "hooks": [{ "command": "...swe_pre_bash_test_gate.py" }] }
  ]
}
```

**After:**
```json
{
  "PreToolUse": [
    {
      "matcher": ".*",
      "hooks": [{
        "type": "command",
        "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/pre/swe_gate_engine.py",
        "timeout": 5
      }]
    }
  ]
}
```

### 5.3 Gate Engine Reads State Store

The gate engine reads `gates_satisfied` from the state store instead of checking sentinel files. Since Phase 1 established dual-write, the state store already has accurate gate status.

### 5.4 Rollback Plan

If the gate engine has issues:
1. Revert `hooks.json` to the three-script configuration
2. Old scripts still exist and still work
3. State store dual-write continues

### 5.5 Testing

- Verify init gate blocks tools before WF_INIT
- Verify init gate allows exempt tools
- Verify swarm gate blocks swarm_init before FEATURE_SWARM read
- Verify test gate blocks test commands before FEATURE_TESTS read
- Verify all gates open correctly after satisfaction events
- Verify gate deny messages are factual (not imperative)

### 5.6 Deliverables

- `swe_gate_engine.py` (single generic gate script)
- `config/gates.yml` (matching current behavior exactly)
- Updated `hooks/hooks.json`
- Test results document

---

## 6. Phase 3: Context Rewrite

**Goal:** Replace all imperative `additionalContext` output with factual state descriptions.

### 6.1 Files Modified

| File | Change |
|---|---|
| `hooks/session/swe_session_start.py` | Rewrite output to use context_engine templates |
| `hooks/prompt/swe_user_prompt_workflow.py` | Merge with swarm script, rewrite output |
| `hooks/prompt/swe_user_prompt_swarm.py` | Merge into workflow script |
| `hooks/post/swe_post_read_state.py` | Rewrite continuation directives as facts |
| `hooks/post/swe_post_write_continue.py` | Merge into post_context, rewrite |
| `memories/wf/WF_INIT.md` | Rewrite imperative instructions as factual descriptions |
| `memories/wf/WF_START.md` | Rewrite imperative instructions |
| `memories/claude/CLAUDE_OBLIGATIONS.md` | Review and reduce imperative content |

### 6.2 Approach

Each script is modified to:
1. Import `ContextEngine` and `StateStore`
2. Read state from state store (not WM parsing)
3. Render context using templates (not inline strings)
4. Output factual state descriptions (not imperative commands)

### 6.3 Before/After Examples

See SPEC-003 for comprehensive before/after examples for each hook.

### 6.4 Memory File Updates

The WF_*.md memory files are rewritten simultaneously. This is a content change, not a structural change -- the files stay in the same location with the same names.

**Key principle:** These files are read by Claude as regular content. While they don't trigger injection defenses as strongly as `additionalContext`, rewriting them for consistency reinforces the factual pattern.

### 6.5 Rollback Plan

Context changes are purely output changes. If factual context doesn't work as well:
- Revert individual template strings in `context-templates.yml`
- No structural changes to undo

### 6.6 Deliverables

- All hook scripts updated to use ContextEngine
- All WF_*.md memory files rewritten
- CLAUDE_OBLIGATIONS.md reviewed and updated
- `config/context-templates.yml` finalized

---

## 7. Phase 4: Stop Hook Enhancement

**Goal:** Replace passive Stop hook with compliance-checking Stop hook.

### 7.1 Changes

1. Replace `hooks/stop/swe_stop_workflow_check.py` with `swe_stop_compliance.py`
2. Update `hooks/hooks.json` Stop entry
3. Optionally add prompt-type hook for deeper verification

### 7.2 Conservative Approach

Start with the command hook only (deterministic, fast). Add the prompt hook only if testing shows the command hook is insufficient.

### 7.3 Anti-Loop Protection

The stop compliance hook includes a block counter (max 3) to prevent infinite loops. This is critical for user experience.

### 7.4 Deliverables

- `swe_stop_compliance.py` with factual blocking
- Updated `hooks/hooks.json`
- Documentation on compliance behavior
- Anti-loop protection tested

---

## 8. Phase 5: Cleanup

**Goal:** Remove legacy code, sentinel files, and deprecated paths.

### 8.1 Removals

| Item | Notes |
|---|---|
| `hooks/pre/swe_pre_tool_init_gate.py` | Replaced by gate engine |
| `hooks/pre/swe_pre_swarm_feature_gate.py` | Replaced by gate engine |
| `hooks/pre/swe_pre_bash_test_gate.py` | Replaced by gate engine |
| `hooks/prompt/swe_user_prompt_swarm.py` | Merged into workflow script |
| `hooks/post/swe_post_write_continue.py` | Merged into post_context |
| `hooks/stop/swe_stop_workflow_check.py` | Replaced by compliance hook |
| `hooks/swe_hooks/core/state_manager.py` | Replaced by state_engine + state_store |
| `hooks/swe_hooks/core/wm_validator.py` | No longer needed (state store validates) |
| `state-machine/states.json` | Moved to `config/states.json` |
| Sentinel file creation code | State store replaces sentinels |
| Legacy `.state` file support in StateStore | After transition period |
| Dual-write code from Phase 1 | State store is now sole authority |

### 8.2 Deprecation Notice

The `state-machine/` directory gets a single file:

```
state-machine/DEPRECATED.md

This directory has been replaced by config/states.json in SWE v2.0.
See specs/SPEC-002 for the new state machine schema.
```

### 8.3 Version Bump

Plugin version bumps to 2.0.0 after Phase 5 is complete.

---

## 9. Session Continuity

### 9.1 Mid-Upgrade Sessions

If a user upgrades mid-session:
- Phase 1 dual-write ensures state store catches up
- Phase 2 gate engine reads from state store (populated by dual-write)
- Sentinel files are still readable as migration fallback

### 9.2 State Store Migration

`StateStore._load_or_create()` includes a migration path that reads legacy sentinel files and `.state` files (see SPEC-005 section 9). This ensures existing sessions continue to work after upgrade.

### 9.3 Clean Install

New installations (no existing `.serena/`) start directly with v2 state store. No migration needed.

---

## 10. Timeline Estimate

| Phase | Scope | Dependencies |
|---|---|---|
| Phase 0 | Pre-migration validation | None |
| Phase 1 | Foundation (new modules, dual-write) | Phase 0 |
| Phase 2 | Gate engine replacement | Phase 1 |
| Phase 3 | Context rewrite | Phase 1 (can parallel Phase 2) |
| Phase 4 | Stop hook enhancement | Phase 2 + 3 |
| Phase 5 | Cleanup | Phase 4 |

Phases 2 and 3 can be developed in parallel since they're independent (gates vs context output).

---

## 11. Risk Mitigation Summary

| Risk | Phase | Mitigation |
|---|---|---|
| VSCode hooks don't fire | 0 | Test early; document CLI requirement |
| Gate engine has regression | 2 | Old scripts kept as rollback |
| Factual context ignored | 3 | Gate engine provides hard enforcement; context is supplementary |
| Stop hook creates loops | 4 | Block counter limits to 3 attempts |
| PyYAML not available | 0 | Support JSON-only fallback |
| Migration corrupts state | 1 | Dual-write ensures both mechanisms stay consistent |
| User configs cause errors | 1 | Validation on load; fall back to defaults on error |

---

## 12. Success Criteria

The migration is complete when:

1. All `additionalContext` output is factual state descriptions (no imperative commands)
2. All gates are defined in `gates.yml` and evaluated by the generic gate engine
3. State is tracked in a single JSON file per session (no sentinel files)
4. Users can add custom gates by editing `.serena/config/gates.yml`
5. Users can add custom states by editing `.serena/config/states.yml`
6. The Stop hook blocks premature completion with factual context
7. Total hook scripts reduced from 10 to 5 + 1 prompt hook
8. Context output per event is under 500 characters (vs current 800-2000+)
9. No hardcoded state logic in Python (all declarative in config)
10. Existing sessions continue to work after upgrade
