#!/usr/bin/env python3
"""PreToolUse hook for Grep/Glob/search_for_pattern/Bash-inspection/Read —
DOCS-FIRST blocking gate.

The informational docs-first hint (swe_post_search_docs_hint.py) fires only
AFTER repeated undocumented searches — the violation has already happened.
This gate inverts that: surfing the codebase is DENIED unless the agent has
consulted documentation (any read_memory / list_memories → 'docread' event)
since the last user prompt ('prompt' event, appended by
swe_user_prompt_workflow.py).

Covered vectors — all the ways an agent reverse-engineers instead of reading
docs (a deploy task answered with `cat package.json` + `head .github/workflows/`
is the canonical violation):
  - Grep / Glob / search_for_pattern — wide searches
  - Bash INSPECTION commands (cat/head/tail/less/grep/rg/find/ls/awk/sed and
    git status/diff/log/show/blame) — mutation/build commands are NOT gated
  - Read of project files — reads under .serena/, scratchpad, or tmp are exempt

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
import re
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


# Bash command words that are pure inspection/recon — reading state instead of
# consulting docs. Matched at command start or after a separator. Mutation,
# build, and pipeline commands are deliberately absent: they are doing work,
# not surfing.
BASH_INSPECT_RE = re.compile(
    r'(^|[;&|]\s*)('
    r'(cat|head|tail|less|more|grep|rg|find|ls|tree|awk|sed)\b'
    r'|git\s+(status|diff|log|show|blame)\b'
    r')',
    re.IGNORECASE,
)

# Read-tool paths that are NOT code-surfing: the memory store / WM, workflow
# machinery, scratchpads, and temp files.
READ_EXEMPT_RE = re.compile(
    r'(/\.serena/|/\.claude/|/scratchpad/|^/(private/)?tmp/|/T/[^/]+/)',
    re.IGNORECASE,
)


def is_gated_call(tool_name: str, tool_input: dict) -> bool:
    """True when this tool call is a docs-first-gated code-surf.

    Grep/Glob/search_for_pattern: always gated.
    Bash: gated only when the command contains an inspection segment.
    Read: gated unless the target path is exempt (memories, scratchpad, tmp).
    Anything else: not gated.
    """
    tool_input = tool_input or {}
    if tool_name in ('Grep', 'Glob') or tool_name.endswith('search_for_pattern'):
        return True
    if tool_name == 'Bash':
        return bool(BASH_INSPECT_RE.search(str(tool_input.get('command', ''))))
    if tool_name == 'Read':
        path = str(tool_input.get('file_path', ''))
        return bool(path) and not READ_EXEMPT_RE.search(path)
    return False


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

        tool_name = get_input_field(input_data, 'tool_name', default='')
        tool_input = input_data.get('tool_input', {})
        if not is_gated_call(tool_name, tool_input):
            output_empty()
            return

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

        output_block(
            f"📓 DOCS FIRST — {tool_name or 'search'} blocked: no memory was consulted "
            "this turn, and this call reads/searches source instead of docs.\n\n"
            "Reverse-engineering the codebase (cat/head/grep/git log/Read) for "
            "something that is documented is the canonical violation — ops, deploy, "
            "and lookup answers live in memories, not in package.json or workflows/.\n\n"
            "  1. mcp__plugin_swe_serena__search_memories_by_name(\"<key terms>\") — or "
            "list_memories(topic=\"<prefix>\") / search_memories_by_front_matter\n"
            "  2. mcp__plugin_swe_serena__read_memory(memory_name=\"<hit>\")\n\n"
            "ONE memory list/read this turn clears this gate — then re-run this call "
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
