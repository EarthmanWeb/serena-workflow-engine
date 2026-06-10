#!/usr/bin/env python3
"""PreToolUse hook for Edit/Write - Validate state and check staleness.

Ensures edits only happen in appropriate workflow states.
BLOCKS edits if stream shows >3 edits since last checkpoint.
Uses session isolation for state checking.

ENFORCEMENT: This hook adds staleness blocking per SPEC_WM_ENFORCEMENT.
"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import HookOutput, output_empty, output_block, output_status
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.state_manager import StateManager
    from swe_hooks.core.session import extract_session_id
    from swe_hooks.core.stream import get_stream_path, count_edits_since_checkpoint
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PreToolUse")

# States where edits are allowed
EDIT_ALLOWED = {'WF_EXECUTE', 'WF_DEBUG_TDD', 'WF_CHECKPOINT', 'WF_INITIAL_SETUP', 'WF_ONBOARD'}

# States where edits should show a warning
WARN_STATES = {'WF_ARCH_REVIEW', 'WF_RESEARCH'}

# Edit threshold for staleness check (must match CHECKPOINT_THRESHOLD in swe_post_edit_checkpoint.py)
STALENESS_THRESHOLD = 10


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())

        # Extract session ID for session isolation
        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)

        # Check staleness via stream (replaces WM-based check)
        if session_id:
            stream_path = get_stream_path(session_id)
            edit_count = count_edits_since_checkpoint(stream_path)

            if edit_count >= STALENESS_THRESHOLD:
                output = HookOutput(event_name="PreToolUse")
                output.block(f"""🛑 WM STALE

{edit_count} edits since last checkpoint.

**UPDATE WM before continuing edits:**
1. Update `## Progress` section with completed work
2. Mark completed items with `[x]`
3. Update `**Files:**` with files you've edited

After updating WM, you may continue editing.""")
                output.output_and_exit()
                return

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
