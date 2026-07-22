#!/usr/bin/env python3
"""SessionEnd hook - Session cleanup and metrics.

Inspired by IronBee's session-end pattern.

Responsibilities:
  1. Record session_end event with duration and final state
  2. Clean up sentinel files (.init_, .test_feature_)
  3. Mark WM as ABANDONED if session didn't reach WF_DONE
"""

import os
import sys
import json
import glob
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.session import extract_session_id
    from swe_hooks.core.config import get_project_root
    from swe_hooks.core.state_manager import StateManager
    from swe_hooks.core.stream import (
        get_stream_path, get_stream_dir, get_sentinel_path, append_event
    )
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "SessionEnd")


def get_session_duration(stream_path: str) -> int:
    """Calculate session duration in seconds from first event timestamp."""
    if not os.path.exists(stream_path):
        return 0
    try:
        with open(stream_path, 'r') as f:
            first_line = f.readline().strip()
        if first_line:
            first_event = json.loads(first_line)
            start_time = first_event.get('t', 0)
            if start_time:
                return int(time.time()) - start_time
    except (IOError, json.JSONDecodeError, ValueError):
        pass
    return 0


def cleanup_sentinels(stream_dir: str, session_id: str):
    """Remove all sentinel files for this session."""
    patterns = [
        f'.init_{session_id}',
        f'.test_feature_{session_id}',
    ]
    for pattern in patterns:
        sentinel_path = os.path.join(stream_dir, pattern)
        try:
            if os.path.exists(sentinel_path):
                os.remove(sentinel_path)
        except IOError:
            pass


def mark_wm_abandoned(project_root: str, session_id: str, final_state: str):
    """If session didn't reach WF_DONE, update WM status to ABANDONED."""
    if final_state == 'WF_DONE':
        return

    wm_path = os.path.join(project_root, '.serena', 'memories', f'WM_{session_id}.md')
    if not os.path.exists(wm_path):
        return

    try:
        with open(wm_path, 'r') as f:
            content = f.read()

        # Only mark if not already marked
        if '[ABANDONED]' in content or '[COMPLETED]' in content:
            return

        # Replace [IN_PROGRESS] with [ABANDONED] in Current Task
        if '[IN_PROGRESS]' in content:
            content = content.replace('[IN_PROGRESS]', '[ABANDONED]', 1)
        elif '## Current Task' in content:
            content = content.replace(
                '## Current Task',
                '## Current Task\n> Session ended without reaching WF_DONE. Final state: ' + final_state,
                1
            )

        with open(wm_path, 'w') as f:
            f.write(content)
    except IOError:
        pass


def main():
    try:
        input_data = {}
        try:
            input_data = json.load(sys.stdin)
        except Exception:
            pass

        cwd = input_data.get('cwd', os.getcwd())
        transcript_path = input_data.get('transcript_path', '')

        session_id = extract_session_id(transcript_path)
        if not session_id:
            print(json.dumps({}))
            sys.exit(0)

        # Check if session was ever initialized
        try:
            project_root = get_project_root()
        except Exception:
            project_root = cwd

        stream_dir = get_stream_dir()
        sentinel_path = os.path.join(stream_dir, f'.init_{session_id}')
        if not os.path.exists(sentinel_path):
            # Session was never initialized — nothing to clean up
            print(json.dumps({}))
            sys.exit(0)

        # Get final workflow state
        try:
            state_mgr = StateManager(cwd, session_id=session_id)
            final_state = state_mgr.get_current_state()
        except Exception:
            final_state = 'unknown'

        # Calculate session duration
        stream_path = get_stream_path(session_id)
        duration = get_session_duration(stream_path)

        # Record session_end event
        append_event(stream_path, 'session_end',
                     s=session_id,
                     final_state=final_state,
                     duration_s=duration)

        # Clean up sentinel files
        cleanup_sentinels(stream_dir, session_id)

        # Mark WM as abandoned if not completed
        mark_wm_abandoned(project_root, session_id, final_state)

        # Output summary (informational, never blocks)
        duration_min = duration // 60
        status = "completed" if final_state == 'WF_DONE' else f"ended in {final_state}"
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SessionEnd",
                "additionalContext": (
                    f"Session {session_id} {status} "
                    f"({duration_min}m). Sentinels cleaned."
                )
            }
        }
        print(json.dumps(output))
        sys.exit(0)

    except Exception:
        print(json.dumps({}))
        sys.exit(0)


if __name__ == '__main__':
    main()
