#!/usr/bin/env python3
"""PostToolUse - RLVR trajectory tracking.

Tracks workflow step progression for reinforcement learning.
Uses session isolation for trajectory tracking.
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
    from swe_hooks.core.output import output_empty
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.state_manager import StateManager
    from swe_hooks.core.session import extract_session_id
except ImportError as e:
    output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"SWE import error: {e}"}}
    print(json.dumps(output), file=sys.stdout)
    sys.exit(0)


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())
        memory_name = get_input_field(input_data, 'tool_input', 'memory_file_name', default='')

        # Only track trajectory for WF_* memory reads
        if memory_name and memory_name.startswith('WF_'):
            # Extract session ID for session isolation
            transcript_path = get_input_field(input_data, 'transcript_path', default='')
            session_id = extract_session_id(transcript_path)

            # Create state manager with session isolation
            state_mgr = StateManager(cwd, session_id=session_id)
            state_mgr.increment_trajectory_step()

        output_empty()

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"Learn error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
