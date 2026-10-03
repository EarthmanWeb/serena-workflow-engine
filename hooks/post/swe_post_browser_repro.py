#!/usr/bin/env python3
"""PostToolUse hook for mcp__browser-devtools__* — browser-repro recording.

Half of the browser-repro-first gate (see hooks/pre/swe_pre_browser_repro_gate.py
and swe_hooks.core.browser_repro). Records a 'browser_repro' stream event on a
SUCCESSFUL call of any actual repro-step tool under the browser-devtools MCP
server (navigation_*, interaction_*, a11y_*, content_*, o11y_*, scenario-run,
execute, …) — core.browser_repro.is_browser_repro_tool excludes the
scenario-CATALOG tools (scenario-list/-search/-add/-delete/-update), since
listing or editing saved scenarios is not itself a repro observation.

Fires for BOTH the main agent and any spawned agent — needs_browser_repro
treats a repro event from ANY agent as satisfying the requirement for the
whole session (the orchestrator delegating the repro step to a subagent is a
legitimate pattern, not a loophole).

Always exit 0 — this hook only records, never blocks (PostToolUse cannot deny).
"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.output import output_empty
    from swe_hooks.core.session import extract_session_id, get_agent_id
    from swe_hooks.core.stream import get_stream_path, append_event
    from swe_hooks.core.browser_repro import is_browser_repro_tool
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PostToolUse")


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        tool_name = get_input_field(input_data, 'tool_name', default='')

        if not is_browser_repro_tool(tool_name):
            output_empty()
            return

        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)
        if not session_id:
            output_empty()
            return

        stream_path = get_stream_path(session_id)
        agent_id = get_agent_id(input_data)
        kwargs = {'tool': tool_name, 's': session_id}
        if agent_id:
            kwargs['agent'] = agent_id
        append_event(stream_path, 'browser_repro', **kwargs)

        output_empty()

    except Exception:
        output_empty()


if __name__ == '__main__':
    main()
