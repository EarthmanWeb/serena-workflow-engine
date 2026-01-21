#!/usr/bin/env python3
"""PostToolUse hook for Edit - Checkpoint tracking.

Tracks edit count and reminds to update WORKING_MEMORY after threshold.
Uses session isolation for edit counting.
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

        # Extract session ID for session isolation
        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)

        # Create state manager with session isolation
        state_mgr = StateManager(cwd, session_id=session_id)

        # Increment edit counter (in-memory, session-scoped)
        count = state_mgr.increment_edits()

        # Check if checkpoint reminder is needed
        if state_mgr.should_checkpoint(3):
            output = HookOutput(event_name="PostToolUse")
            output.add_message(f"💾 CHECKPOINT: {count} edits - Update WORKING_MEMORY")
            state_mgr.reset_edit_counter()
            output.output_and_exit()
            return

        output_empty()

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"Checkpoint error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
