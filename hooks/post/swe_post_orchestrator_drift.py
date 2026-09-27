#!/usr/bin/env python3
"""PostToolUse hook for main-agent task-work tools — orchestrator-drift nudge.

Counts consecutive direct task-work calls (Edit, Write, NotebookEdit, Serena
edit tools, Bash) made by the MAIN agent since the last Agent/Workflow launch
in this session. At a threshold, nudges the orchestrator to stop doing the
work itself and split what remains into parallel subagents — the
"orchestrator + swarm delegation" model this session is meant to follow
(FEATURE_SUBAGENTS).

An Agent or Workflow call resets the streak (the orchestrator just
delegated). Informational only — PostToolUse cannot block, and this hook
never does. Mirrors swe_post_edit_checkpoint.py / swe_post_search_docs_hint.py.

Exempt when the calling tool itself IS an Agent/Workflow launch — that event
is the reset marker, not task work, and is recorded as 'delegation' instead
of 'task_work' by this same hook (registered on both matchers so one script
covers count + reset).
"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import HookOutput, output_status, output_empty
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.session import extract_session_id, is_spawned_agent, is_subagent_transcript
    from swe_hooks.core.stream import get_stream_path, append_event, count_task_work_since_delegation
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e)

# Consecutive direct task-work calls before the drift nudge.
DRIFT_THRESHOLD = 6

DELEGATION_TOOL_NAMES = {'Agent', 'Task', 'Workflow'}


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)

        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)
        if not session_id:
            output_empty()
            return

        # Subagents are not orchestrators — never track drift for their own
        # tool calls (they are expected to do direct work).
        if is_spawned_agent(input_data) or is_subagent_transcript(transcript_path):
            output_empty()
            return

        tool_name = get_input_field(input_data, 'tool_name', default='')
        stream_path = get_stream_path(session_id)

        if tool_name in DELEGATION_TOOL_NAMES:
            append_event(stream_path, 'delegation', tool=tool_name, s=session_id)
            output_status("\U0001f501 delegation logged — drift counter reset")
            return

        append_event(stream_path, 'task_work', tool=tool_name, s=session_id)
        drift_count = count_task_work_since_delegation(stream_path)

        if drift_count >= DRIFT_THRESHOLD:
            output = HookOutput(event_name="PostToolUse")
            output.add_message(
                f"Orchestrator drift: {drift_count} direct task-work calls without "
                "delegating — split remaining work into parallel subagents "
                "(see FEATURE_SUBAGENTS)."
            )
            output.output_and_exit()
            return

        output_status(f"\U0001f6e0️ task-work #{drift_count} since last delegation")

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                         "additionalContext": f"Orchestrator-drift hook error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
