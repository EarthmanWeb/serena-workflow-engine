#!/usr/bin/env python3
"""PostToolUse hook for Edit - Checkpoint enforcement.

Tracks edit count via stream-based event tracking and reminds
the user to update WM progress after a threshold of edits.
"""

import os
import sys
import json
PLUGIN_ROOT = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
if PLUGIN_ROOT:
    hooks_dir = os.path.join(PLUGIN_ROOT, 'hooks')
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import HookOutput, output_empty, output_status
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.state_manager import StateManager
    from swe_hooks.core.session import extract_session_id, find_working_memory_for_session
    from swe_hooks.core.stream import get_stream_path, append_event, count_edits_since_checkpoint
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e)

# Edit threshold before checkpoint reminder
CHECKPOINT_THRESHOLD = 3


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())

        # Extract session ID for session isolation
        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)

        # Get edited file path if available
        tool_input = input_data.get('tool_input', {})
        edited_file = tool_input.get('file_path', '') or tool_input.get('path', '')

        # Append edit event to stream
        stream_path = get_stream_path(session_id)
        append_event(stream_path, 'edit', file=edited_file, s=session_id)

        # Count edits since last checkpoint or state event
        edit_count = count_edits_since_checkpoint(stream_path)

        # Check if checkpoint reminder is needed
        if edit_count >= CHECKPOINT_THRESHOLD:
            output = HookOutput(event_name="PostToolUse")
            output.add_message(f"\U0001f4be CHECKPOINT ({edit_count} edits) - Update your WM progress section")
            output.output_and_exit()
            return

        # Under threshold - track with concise status
        output_status(f"WM: edit #{edit_count}")

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"Checkpoint error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
