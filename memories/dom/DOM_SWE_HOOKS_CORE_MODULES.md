---
name: DOM_SWE_HOOKS_CORE_MODULES
description: Shared hook core modules (HookOutput, StateManager, Session, WM Validator, Orphan Reaper), output-format JSON examples, instruction-file strategy, hook loading verification, new scripts, and the diagnostic checklist.
obligations:
  - Store all workflow state in per-session WM files via StateManager, NEVER a global state file.
  - SWE hooks load automatically from the plugin folder via hooks/hooks.json + `${CLAUDE_PLUGIN_ROOT}` — do NOT copy hook config to settings.json.
metadata:
  type: domain
---

# DOM_SWE_HOOKS_CORE_MODULES — Core Modules, Output Formats, Diagnostics

Hub: `mem:dom/DOM_SWE_HOOKS`.

## Output Format Examples

Allow (silent):

```json
{}
```

Show message:

```json
{ "hookSpecificOutput": { "hookEventName": "PostToolUse", "additionalContext": "Your message here" } }
```

Block (PreToolUse only):

```json
{ "hookSpecificOutput": { "hookEventName": "PreToolUse", "permissionDecision": "deny", "additionalContext": "Reason for blocking" } }
```

Stop event:

```json
{ "hookSpecificOutput": { "hookEventName": "Stop", "additionalContext": "Warning message" } }
```

## HookOutput (`swe_hooks.core.output`)

```python
from swe_hooks.core.output import HookOutput, output_empty, output_block, output_message

output = HookOutput(event_name="PostToolUse")
output.add_message("Info message")
output.output_and_exit()          # always exits 0

output = HookOutput(event_name="PreToolUse")
output.block("Reason for blocking")   # block PreToolUse only
output.output_and_exit()

output_empty()                        # {} and exit 0
output_message("Info", "PostToolUse") # message and exit 0
output_block("Reason")                # block PreToolUse and exit 0
```

## StateManager (`swe_hooks.core.state_manager`)

Session-isolated state. Store state in WM files, NEVER a global state file — enables concurrent sessions without conflict. Each session's state lives in the `## Workflow Context` section of its WM.

```python
from swe_hooks.core.state_manager import StateManager

state_mgr = StateManager(cwd)                              # finds most recent WM
state_mgr = StateManager(cwd, wm_filename="WM_20260120_my_task")
state_mgr.get_current_state()      # "WF_CLASSIFY" — read from WM
state_mgr.transition_to("WF_EXECUTE")  # updates WM file
state_mgr.get_working_memory()     # WM filename
state_mgr.increment_edits()        # in-memory only (session-local)
state_mgr.should_checkpoint()      # True if >= 10 edits (CHECKPOINT_THRESHOLD)
```

State storage in WM:

```markdown
## Workflow Context

- **Calling Step**: WF_EXECUTE ← current state stored here
- **Feature Key(s)**: BUILDER
- **Session ID**: 20260120_143052
- **Return Step**: WF_VERIFY
- **Invocation Mode**: workflow
```

## Session (`swe_hooks.core.session`)

```python
from swe_hooks.core.session import get_session_id, find_wm_file, create_wm_file

session_id = get_session_id()   # e.g., "250125a3"
wm_path = find_wm_file(cwd)     # most recent WM
create_wm_file(cwd, session_id, initial_state="WF_INIT")
```

## WM Validator (`swe_hooks.core.wm_validator`)

```python
from swe_hooks.core.wm_validator import validate_wm_structure, get_wm_section

is_valid, errors = validate_wm_structure(wm_content)
section_content = get_wm_section(wm_content, "Workflow Context")
```

## Orphan Reaper (`swe_hooks.core.orphan_reaper`)

- Problem: a VS Code (or Cursor / VS Code Insiders) restart/crash can leave its Claude Code native-binary child alive, reparented to launchd (`ppid == 1`). Nothing in the UI can reach it — its whole MCP/LSP stack (Serena, tsserver, pyright, etc., several GB) keeps running; multiple orphans can re-OOM the machine.
- Match criteria (ALL required): executable path matches `/\.(vscode(-insiders)?|cursor)/extensions/anthropic\.claude-code-.*/resources/native-binary/claude`, `ppid == 1`, owned by the current user, not this session's own pid. A terminal `claude` CLI session is NEVER matched (parent is a shell; the path check alone excludes it even if its ppid happened to be 1).
- `find_orphaned_vscode_claude_sessions(ps_output, my_uid, exclude_pids=None)` — pure parser over `ps -axo pid=,ppid=,uid=,command=` text.
- `kill_matches(matches, kill_fn=os.kill, grace_seconds=3, is_alive_fn=None)` — SIGTERM every match; escalate to SIGKILL only if still alive after the grace period. Injectable `kill_fn`/`is_alive_fn`/`sleep_fn` for tests.
- `reap_orphans(dry_run, ...)` — wires ps-fetch + match + kill; NEVER raises — a fetch/parse/kill failure is returned as `{"error": ...}` instead. Wired into `swe_session_start.py` (best-effort, one `ps` call, never blocks boot; a reap error prints a one-line warning to stderr, never swallowed silently); reaped pids are surfaced in the SessionStart banner.
- Standalone CLI: `python3 hooks/swe_hooks/core/orphan_reaper.py --dry-run` (list matches, kill nothing) or `--apply` (SIGTERM/SIGKILL them); `--grace-seconds N` to tune the escalation wait.

## Instruction File Strategy

- Hooks NEVER read and echo instruction-file contents.
- Hooks point the agent to `mcp__serena__read_memory("wf/WF_*")`.
- Instruction files are copied to `.serena/swe/` during `/swe-init`.

## Hook Loading

- SWE hooks load automatically from the plugin folder. Do NOT copy to settings.json.
- `hooks/hooks.json` uses `${CLAUDE_PLUGIN_ROOT}`, resolved by the plugin system.

Verify loading:

```bash
jq '.hooks | keys' .claude/plugins/serena-workflow-engine/hooks/hooks.json
# Expected: ["PostToolUse","PostToolUseFailure","PreToolUse","SessionEnd","SessionStart","Stop","UserPromptSubmit"]
```

## Other Behavior Notes

- Background task notifications receive NO workflow injection (no step-report, no CONTINUE directive, no gate prompts) — they are informational only.
- ToolSearch instructions in hook output are CONDITIONAL — surfaced only when a deferred-tool call is actually pending, not on every turn.

## New Modules & Scripts

- `hooks/swe_hooks/core/loop_guard.py` — implements `loopCaps` enforcement (refuse-with-escape-message on cap exceeded, warn on A→B→A→B oscillation) for `readAdvance` transitions. See `mem:dom/DOM_SWE_STATE_MACHINE`.
- `scripts/validate-graph.py` — validates `state-machine/states.json` (transitions, `transitionMatrix` edges, `rank` ordering, `loopCaps`, `subflows`).
- `skills/swe-memory-size-audit/scripts/validate-memory-graph.py` — validates the memory link graph (dangling/orphan refs, per-file word counts, CAPS hard-stop counts). Run as `python3 skills/swe-memory-size-audit/scripts/validate-memory-graph.py --extra-root memories` (conf roots + plugin source tree in ONE run — never validate trees separately). See `mem:feature/FEATURE_SWE` for usage.

## Diagnostic Checklist

1. `which python3` — Python 3 available.
2. `chmod +x hooks/**/*.py` — hooks executable.
3. hooks.json uses `python3` commands.
4. Each hook has an appropriate timeout.
5. All hooks exit 0.
6. `jq '.enabledPlugins' .claude/settings.local.json` — SWE plugin enabled.
