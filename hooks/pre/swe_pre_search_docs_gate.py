#!/usr/bin/env python3
"""PreToolUse hook for Grep/Glob/search_for_pattern — DOCS-FIRST blocking gate.

The informational docs-first hint (swe_post_search_docs_hint.py) fires only
AFTER repeated undocumented searches — the violation has already happened.
This gate inverts that: a wide-reaching search is DENIED unless the agent has
consulted documentation (any read_memory / list_memories → 'docread' event)
since the last user prompt ('prompt' event, appended by
swe_user_prompt_workflow.py).

Clearing the gate is deliberately cheap: ONE list_memories or read_memory call
per turn satisfies it — and that call is exactly the mandated docs-first
behavior. There is no other escape.

Exemptions (fail-open by design):
  - No session id / no stream → not a managed session, allow.
  - No init sentinel → spawned agent or unmanaged session (subagents bypass
    the workflow and must not be doc-gated), allow.
  - Stream with no 'prompt' marker in the tail window → fall back to "any
    docread in the window" (pre-upgrade streams stay usable).
"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import output_empty, output_block
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.session import extract_session_id
    from swe_hooks.core.stream import (
        get_stream_path, get_sentinel_path, count_events_since_last,
    )
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PreToolUse")


def docs_consulted_this_turn(stream_path: str) -> bool:
    """True when a 'docread' event exists after the last 'prompt' marker.

    count_events_since_last scans backwards and stops at the first marker, so
    with marker_types=('prompt',) it counts docreads in the current turn. In a
    stream that predates 'prompt' markers it counts docreads across the tail
    window — the graceful fallback.
    """
    return count_events_since_last(
        stream_path,
        marker_types=('prompt',),
        count_type='docread',
    ) > 0


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)

        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)
        if not session_id:
            output_empty()
            return

        # Spawned agents / unmanaged sessions have no init sentinel — never gate them.
        if not os.path.exists(get_sentinel_path(session_id)):
            output_empty()
            return

        stream_path = get_stream_path(session_id)
        if not os.path.exists(stream_path):
            output_empty()
            return

        if docs_consulted_this_turn(stream_path):
            output_empty()
            return

        tool_name = get_input_field(input_data, 'tool_name', default='search')
        output_block(
            f"📓 DOCS FIRST — {tool_name} blocked: no memory was consulted this turn.\n\n"
            "Before searching the filesystem, check whether the answer is already "
            "documented (it usually is):\n"
            "  1. mcp__plugin_swe_serena__list_memories(topic=\"<prefix>\")  — or "
            "search_memories_by_name / search_memories_by_front_matter\n"
            "  2. mcp__plugin_swe_serena__read_memory(memory_name=\"<hit>\")\n\n"
            "ONE memory list/read this turn clears this gate — then re-run the search "
            "if the docs did not answer. This is the CLAUDE.md '⛔ DOCS FIRST' rule, "
            "enforced. See feedback/FEEDBACK_DOCS_FIRST_ALWAYS."
        )

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                         "additionalContext": f"Docs-first gate error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
