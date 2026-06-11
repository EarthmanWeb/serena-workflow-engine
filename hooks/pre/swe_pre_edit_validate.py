#!/usr/bin/env python3
"""PreToolUse hook for Edit/Write - Validate workflow state for edits.

Ensures edits only happen in appropriate workflow states.
No staleness blocking — checkpoint is informational only.
"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import HookOutput, output_status
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.state_manager import StateManager
    from swe_hooks.core.session import extract_session_id
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PreToolUse")

# States where edits are allowed
EDIT_ALLOWED = {'WF_EXECUTE', 'WF_DEBUG_TDD', 'WF_CHECKPOINT', 'WF_INITIAL_SETUP', 'WF_ONBOARD'}

# States where edits should show a warning
WARN_STATES = {'WF_ARCH_REVIEW', 'WF_RESEARCH'}


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())

        # Extract session ID for session isolation
        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)

        # Create state manager with session isolation
        state_mgr = StateManager(cwd, session_id=session_id)
        current = state_mgr.get_current_state()

        # Allow edits in execution states
        if current in EDIT_ALLOWED:
            output_status(f"✓ Edit allowed ({current})", event="PreToolUse")
            return

        # Warn but allow in planning states
        if current in WARN_STATES:
            output = HookOutput(event_name="PreToolUse")
            output.add_message(f"⚠️ Edit in planning state: {current}")
            output.output_and_exit()
            return

        # BLOCK: editing not allowed in this state
        output = HookOutput(event_name="PreToolUse")
        output.block(f"🛑 Edit blocked in state {current}. Move to WF_EXECUTE first.")
        output.output_and_exit()

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": f"Pre-edit error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
