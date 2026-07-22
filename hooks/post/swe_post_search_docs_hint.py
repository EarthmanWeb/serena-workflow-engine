#!/usr/bin/env python3
"""PostToolUse hook for wide-reaching searches — docs-first hint.

Counts consecutive wide-reaching search calls (Grep, Glob,
search_for_pattern) via stream-based event tracking. At a threshold of
searches in a row with no intervening documentation read, it reminds the
agent to consult Serena memories first — most problems are solved quickly
by checking the docs.

Streak semantics ("in a row"): the counter resets whenever a doc read
(read_memory / list_memories → 'docread' event) or a state change occurs.
So the reminder fires only when the agent greps repeatedly WITHOUT checking
documentation. Consulting a memory clears the streak.

Mirrors swe_post_edit_checkpoint.py. Informational only — PostToolUse
cannot block, and this hook never does.
"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import HookOutput, output_status
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.session import extract_session_id
    from swe_hooks.core.stream import get_stream_path, append_event, count_searches_since_docread
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e)

# Consecutive wide-reaching searches before the docs-first reminder
SEARCH_HINT_THRESHOLD = 3


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)

        # Extract session ID for session isolation
        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)

        # Record the search target if available (best-effort, for the log only)
        tool_input = input_data.get('tool_input', {})
        query = (tool_input.get('pattern')
                 or tool_input.get('substring_pattern')
                 or tool_input.get('query', ''))

        # Append search event to stream
        stream_path = get_stream_path(session_id)
        append_event(stream_path, 'search', q=str(query)[:80], s=session_id)

        # Count searches since the last doc read / state change
        search_count = count_searches_since_docread(stream_path)

        # Informational nudge at threshold — never blocks
        if search_count >= SEARCH_HINT_THRESHOLD:
            output = HookOutput(event_name="PostToolUse")
            output.add_message(
                f"\U0001f4d3 {search_count} wide searches in a row without checking docs. "
                "Most problems are solved fast by checking the documentation FIRST: "
                "list_memories / search_memories_by_name / search_memories_by_front_matter, "
                "then read_memory. Consult a memory before grepping again."
            )
            output.output_and_exit()
            return

        # Under threshold - concise status
        output_status(f"\U0001f50d search #{search_count} (docs-first at {SEARCH_HINT_THRESHOLD})")

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"Search-hint error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
