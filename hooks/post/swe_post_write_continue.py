#!/usr/bin/env python3
"""PostToolUse hook for write_memory/edit_memory - Inject continuation directive.

Prevents Claude from stopping after write_memory returns a simple confirmation.
Uses updatedMCPToolOutput to inject workflow state into the result itself,
plus additionalContext as a belt-and-suspenders continuation reminder.
"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.session import extract_session_id, find_working_memory_for_session
    from swe_hooks.core.config import read_working_memory_state
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PostToolUse")


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())
        tool_name = get_input_field(input_data, 'tool_name', default='')
        memory_name = get_input_field(input_data, 'tool_input', 'memory_name', default='')

        # Get original tool result
        tool_result = get_input_field(input_data, 'tool_result', default='')

        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)

        # Get current workflow state
        current_state = None
        if session_id:
            wm_filepath = find_working_memory_for_session(cwd, session_id)
            if wm_filepath:
                wm_file = os.path.basename(wm_filepath).replace('.md', '')
                state_data, _ = read_working_memory_state(cwd, wm_file, session_id=session_id)
                if state_data:
                    current_state = state_data.get("current_state")

        # Context message only - never mask the actual tool result
        context = f"💾 Memory written: {memory_name}"
        if current_state:
            context += f" | State: {current_state} — continue working on current task."

        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": context
            }
        }
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"Post-write error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
