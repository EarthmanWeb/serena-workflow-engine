#!/usr/bin/env python3
"""PostToolUse hook for read_memory - State transitions.

When a WF_* memory is read, this hook transitions the workflow state.
Uses session isolation to ensure state changes only affect the current session.
"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import HookOutput, output_empty, output_status
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.state_manager import StateManager, STATE_ICONS
    from swe_hooks.core.session import extract_session_id, get_project_root, find_working_memory_for_session
    from swe_hooks.core.config import append_transition_to_wm, write_state_file, resolve_installed_plugin, resolve_plugin_root
    from swe_hooks.core.stream import get_stream_path, append_event, get_sentinel_path
    from datetime import datetime
    import re
    import time
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e)


def create_feature_sentinel(session_id: str, gate_name: str) -> bool:
    """Create a sentinel file for a feature gate.

    Pattern: .serena/streams/.{gate_name}_feature_{session_id}
    Used by: FEATURE_TESTS (test gate), FEATURE_SWARM (swarm gate).
    """
    if not session_id:
        return False
    try:
        stream_dir = get_stream_path(session_id).rsplit('/', 1)[0]
        sentinel = os.path.join(stream_dir, f'.{gate_name}_feature_{session_id}')
        os.makedirs(os.path.dirname(sentinel), exist_ok=True)
        open(sentinel, 'w').close()
        return True
    except IOError:
        return False


def _get_plugin_version() -> str:
    """Report the AUTHORITATIVE installed plugin version.

    Resolution order:
    1. installed_plugins.json `version` (source of truth — follows updates even
       if this process was launched under an older ${CLAUDE_PLUGIN_ROOT}).
    2. plugin.json at the installed root (resolve_plugin_root()).
    3. plugin.json under launch-time CLAUDE_PLUGIN_ROOT / derived path (dev).

    Reading directly from the launch-time CLAUDE_PLUGIN_ROOT (the old behaviour)
    reports a stale version after an in-place update, because a long-lived hook
    process keeps its launch root. The installed manifest does not.
    """
    # 1. Authoritative version straight from the install manifest.
    _, version = resolve_installed_plugin()
    if version:
        return version

    # 2/3. Fall back to plugin.json at the installed root, else launch root.
    plugin_root = resolve_plugin_root()
    if plugin_root:
        plugin_json = os.path.join(plugin_root, '.claude-plugin', 'plugin.json')
    else:
        # Derive: post/ -> hooks/ -> plugin root
        plugin_json = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            '.claude-plugin', 'plugin.json'
        )
    try:
        with open(plugin_json) as f:
            return json.load(f).get('version', '')
    except (IOError, json.JSONDecodeError, ValueError):
        return ''


def _get_continuation(current_state: str) -> str:
    """Get a one-line continuation directive for the current workflow state.

    Prevents mid-step stalls by reminding the agent what to do next.
    Only fires for states where stalls have been observed.
    """
    directives = {
        "WF_CLASSIFY": "Load ALL FEATURE_[KEY] + supporting DOM_*/SYS_*/SPEC_* memories → update WM → route to next step",
        "WF_ARCH_REVIEW": "Complete architecture review → present plan → route to WF_EXECUTE",
        "WF_EXECUTE": "Continue implementation → checkpoint at 3+ edits → WF_VERIFY when done",
        "WF_RESEARCH": "Continue investigation → record findings → route when complete",
        "WF_VERIFY": "Complete verification checks → update WM → read wf/WF_DONE when all clean",
        "WF_DONE": "Update WM with final status → summarize to user → end session",
    }
    d = directives.get(current_state)
    return f"⏩ CONTINUE ({current_state}): {d}" if d else ""


def _bootstrap_session_at_classify(cwd, session_id):
    """Create WM + state file + init sentinel when the init chain reaches
    WF_CLASSIFY. Restores the bootstrap that WF_START used to perform (v3),
    now bound to the v4 post-init entry state. Idempotent: callers guard on
    sentinel absence. Mirrors create_wm_and_sentinel() in the prompt hook.
    """
    project_root = get_project_root()
    wm_filename = f"WM_{session_id}.md"
    wm_filepath = os.path.join(project_root, ".serena", "memories", wm_filename)

    wm_content = f"""# Working Memory: Session {session_id}

## Session
- **ID**: {session_id}
- **Task**: (awaiting classification)
- **Started**: {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Workflow Context
**Current State**: WF_CLASSIFY
**Previous State**: WF_INIT
**Session ID**: {session_id}

## Task Context
- **Feature(s)**: (to be determined)
- **Complexity**: (to be determined)

## Progress Tracking
### Pending
- [ ] Classify task

## Requirements
(to be determined from user request)

## Implementation Notes
(none yet)
"""
    try:
        os.makedirs(os.path.dirname(wm_filepath), exist_ok=True)
        with open(wm_filepath, 'w', encoding='utf-8') as f:
            f.write(wm_content)
    except IOError:
        pass

    # Decoupled state file — advance WF_INIT → WF_CLASSIFY.
    write_state_file(session_id, 'WF_CLASSIFY', prev_state='WF_INIT')

    # Session start stream event.
    try:
        append_event(get_stream_path(session_id), 'session_start', s=session_id)
    except Exception:
        pass

    # Init sentinel — unlocks the pre-init gate for this session.
    sentinel = get_sentinel_path(session_id)
    try:
        os.makedirs(os.path.dirname(sentinel), exist_ok=True)
        sentinel_data = {
            "session_id": session_id,
            "wm_file": wm_filename.replace('.md', ''),
            "validated_at": int(time.time()),
        }
        with open(sentinel, 'w') as sf:
            json.dump(sentinel_data, sf, separators=(',', ':'))
    except IOError:
        pass


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())
        tool_name = get_input_field(input_data, 'tool_name', default='')
        memory_name = get_input_field(input_data, 'tool_input', 'memory_name', default='')
        tool_result = get_input_field(input_data, 'tool_result', default='')
        # Bare name without directory prefix (e.g. "wf/WF_CLASSIFY" -> "WF_CLASSIFY")
        bare_name = memory_name.rsplit('/', 1)[-1] if memory_name else ''

        # Build input echo prefix for all output paths
        _in_label = f"[IN: memory_name=\"{memory_name}\"]" if memory_name else ""

        # Extract session ID early (needed for continuation directives)
        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)

        # Handle list_memories calls (no memory_name) — inject continuation
        if 'list_memories' in tool_name:
            state_mgr = StateManager(cwd, session_id=session_id)
            current = state_mgr.get_current_state()
            directive = _get_continuation(current)
            if directive:
                output = HookOutput(event_name="PostToolUse")
                output.add_message("📋 Memories listed")
                output.add_message("")
                output.add_message(directive)
                output.output_and_exit()
            output_status(f"📋 Memories listed {_in_label}")
            return

        # Handle FEATURE_TESTS read - create sentinel for test gate
        if bare_name == 'FEATURE_TESTS':
            create_feature_sentinel(session_id, 'test')
            output_status(f"📖 Read: {memory_name} {_in_label}")
            return

        # Handle FEATURE_SWARM read - create sentinel for swarm gate + emit directive
        if bare_name == 'FEATURE_SWARM':
            create_feature_sentinel(session_id, 'swarm')

            output = HookOutput(event_name="PostToolUse")
            output.add_message(f"📖 Read: {memory_name} {_in_label}")
            output.add_message("")
            output.add_message("🐝 SWARM DETECTED - You MUST use ruv-swarm or hive-mind swarm orchestration. Go to WF_SWARM_ORCHESTRATE after completing WF_CLASSIFY feature loading.")
            output.output_and_exit()

        # Non-WF_* memories: log read + inject continuation directive
        if not bare_name or not bare_name.startswith('WF_'):
            state_mgr = StateManager(cwd, session_id=session_id)
            current = state_mgr.get_current_state()
            directive = _get_continuation(current)

            if directive:
                output = HookOutput(event_name="PostToolUse")
                output.add_message(f"📖 Read: {memory_name or 'unknown'} {_in_label}")
                output.add_message("")
                output.add_message(directive)
                output.output_and_exit()

            output_status(f"📖 Read: {memory_name or 'unknown'} {_in_label}")
            return

        # WF_* read = PURE READ. Reads NEVER advance the FSM (v4: read≠transition).
        # Display the step being inspected and emit a continuation directive for
        # the CURRENT state. Transitions happen only via explicit set_state / the
        # prompt-intent hook — never as a side effect of reading a memory.
        state_mgr = StateManager(cwd, session_id=session_id)

        output = HookOutput(event_name="PostToolUse")
        icon = STATE_ICONS.get(bare_name, '📍')
        current = state_mgr.get_current_state()

        # INIT-CHAIN COMPLETION (the ONE sanctioned read-driven transition).
        # v4 removed WF_START; the WM + init sentinel used to be created when the
        # session transitioned to WF_START during the init chain. The init chain
        # now ends by reading wf/WF_CLASSIFY. Because reads no longer transition,
        # nothing creates the sentinel within the first turn, so the pre-init gate
        # stays locked and blocks every task read — a deadlock.
        #
        # Fix: when wf/WF_CLASSIFY is read while still at WF_INIT (init chain in
        # progress) and the session is not yet initialized, bootstrap it here:
        # create WM + sentinel and advance WF_INIT → WF_CLASSIFY. This is NOT a
        # general read-transition — it is scoped to exactly WF_INIT→WF_CLASSIFY,
        # the one transition the init chain requires, with no work semantics.
        if bare_name == 'WF_CLASSIFY' and current in ('WF_INIT', 'UNINITIALIZED'):
            sentinel = get_sentinel_path(session_id) if session_id else None
            if session_id and sentinel and not os.path.exists(sentinel):
                _bootstrap_session_at_classify(cwd, session_id)
                # Reflect the new state for the directive/label below.
                current = 'WF_CLASSIFY'
        version = _get_plugin_version()
        ver_tag = f" (v{version})" if version else ""

        step_label = f"{icon} ON STEP: {bare_name}{ver_tag}" if bare_name == 'WF_INIT' else f"{icon} ON STEP: {bare_name}"
        output.add_message(step_label)

        directive = _get_continuation(current)
        if directive:
            output.add_message("")
            output.add_message(directive)

        output.output_and_exit()

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"Post-read error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
