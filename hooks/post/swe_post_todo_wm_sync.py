#!/usr/bin/env python3
"""PostToolUse hook for TodoWrite - Remind agent to keep WM in sync.

When todos are modified, this hook checks if the current workflow state
has an active WM file and reminds the agent to invoke /swe-wm-update
to keep Working Memory synchronized with task progress.
"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import HookOutput, output_empty, output_status
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.state_manager import StateManager
    from swe_hooks.core.session import extract_session_id, find_working_memory_for_session
    from swe_hooks.core.stream import get_stream_path, append_event
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PostTodoWM")

# States where WM sync reminder is relevant
WM_SYNC_STATES = {
    'WF_START', 'WF_CLASSIFY', 'WF_LOAD_FEATURE', 'WF_ARCH_REVIEW',
    'WF_SWARM_ORCHESTRATE', 'WF_EXECUTE', 'WF_CHECKPOINT',
    'WF_DEBUG_TDD', 'WF_VERIFY', 'WF_RESEARCH', 'WF_CONTINUE',
}


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())

        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)

        if not session_id:
            output_empty()
            return

        # Track todo event in stream
        stream_path = get_stream_path(session_id)
        append_event(stream_path, 'todo', s=session_id)

        state_mgr = StateManager(cwd, session_id=session_id)
        current = state_mgr.get_current_state()

        if current not in WM_SYNC_STATES:
            output_status("📋 Todo updated")
            return

        # Check if WM exists for this session
        wm_file = find_working_memory_for_session(cwd, session_id)

        if not wm_file:
            output_status("📋 Todo updated (no WM)")
            return

        # Output reminder to sync WM
        out = HookOutput(event_name="PostToolUse")
        out.add_message(
            f"📋 Todo updated during {current}. "
            f"Invoke `/swe-wm-update --from {current}` to sync Working Memory with current progress."
        )
        out.output_and_exit()

    except Exception:
        output_empty()


if __name__ == '__main__':
    main()
