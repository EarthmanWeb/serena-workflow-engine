#!/usr/bin/env python3
"""Stop hook - Check workflow state and log interruption to stream."""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import HookOutput, output_empty
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.state_manager import StateManager
    from swe_hooks.core.stream import get_stream_path, append_event
    from swe_hooks.core.session import extract_session_id
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "Stop")

INCOMPLETE = {'WF_EXECUTE', 'WF_DEBUG_TDD', 'WF_VERIFY', 'WF_ARCH_REVIEW'}

def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())

        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)

        state_mgr = StateManager(cwd, session_id=session_id)
        current = state_mgr.get_current_state()

        if current in ('WF_DONE', 'UNINITIALIZED'):
            output_empty()
            return

        if current in INCOMPLETE:
            if session_id:
                stream_path = get_stream_path(session_id)
                append_event(stream_path, 'interrupted', state=current, s=session_id)
            # Stop hooks use top-level fields, not hookSpecificOutput
            result = {"stopReason": f"⚠️ Stopping with incomplete work: {current}"}
            print(json.dumps(result), file=sys.stdout)
            sys.exit(0)
            return

        output_empty()
    except Exception as e:
        # Stop hooks use top-level fields, not hookSpecificOutput
        result = {"stopReason": f"Stop error: {e}"}
        print(json.dumps(result), file=sys.stdout)
        sys.exit(0)

if __name__ == '__main__':
    main()
