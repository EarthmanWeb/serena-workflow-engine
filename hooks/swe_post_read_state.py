#!/usr/bin/env python3
"""PostToolUse hook for read_memory - State transitions.

When a WF_* memory is read, this hook transitions the workflow state.
Uses session isolation to ensure state changes only affect the current session.
"""

import os
import sys
import json

PLUGIN_ROOT = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
if PLUGIN_ROOT:
    hooks_dir = os.path.join(PLUGIN_ROOT, 'hooks')
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)

try:
    from swe_hooks.core.output import HookOutput, output_empty
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.state_manager import StateManager, STATE_ICONS
    from swe_hooks.core.session import extract_session_id
    from swe_hooks.core.config import append_transition_to_wm
except ImportError as e:
    output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"SWE import error: {e}"}}
    print(json.dumps(output), file=sys.stdout)
    sys.exit(0)


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())
        memory_name = get_input_field(input_data, 'tool_input', 'memory_file_name', default='')

        # Only process WF_* memories for state transitions
        if not memory_name or not memory_name.startswith('WF_'):
            output_empty()
            return  # Explicit return for clarity (output_empty exits)

        # Extract session ID for session isolation
        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)

        # Create state manager with session isolation
        state_mgr = StateManager(cwd, session_id=session_id)

        output = HookOutput(event_name="PostToolUse")
        icon = STATE_ICONS.get(memory_name, '📍')
        current = state_mgr.get_current_state()

        output.add_message(f"{icon} ON STEP: {memory_name}")

        # Only transition if state is different
        if current != memory_name:
            success, msg = state_mgr.transition_to(memory_name)
            if success:
                output.add_message(msg)
                # Auto-log transition to WORKING_MEMORY Progress section
                if state_mgr.wm_filepath:
                    append_transition_to_wm(state_mgr.wm_filepath, current, memory_name)
            else:
                output.add_message(f"⚠️ State transition issue: {msg}")

        output.output_and_exit()

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"Post-read error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
