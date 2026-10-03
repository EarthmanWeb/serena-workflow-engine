#!/usr/bin/env python3
"""PreToolUse hook for Bash and Agent|Task — browser-repro-first gate.

Incident 2026-10-02: an E2E (Playwright) spec failed; the orchestrator then
spent 4+ rerun cycles delegating "rerun the spec with fix X" agents on
unverified theories, never reproducing the failing step in the
browser-devtools MCP (the documented first move — browser = source of
truth, mem:feedback/FEEDBACK_TDD_FOR_BUG_FIXES "browser-repro section").

Rule enforced here: once an E2E Bash run FAILS (core.browser_repro.
needs_browser_repro reads the last 'e2e_fail' vs last 'browser_repro' stream
event), no further E2E run and no E2E rerun/debug DELEGATION is allowed
until the failing flow has been reproduced in mcp__browser-devtools__*.

Applies to BOTH the main agent and spawned agents — the gate reads the
SHARED session stream (needs_browser_repro treats a repro from any agent as
satisfying the requirement for everyone), so a subagent cannot route around
an orchestrator's unobserved failure, and vice versa.

Two independent deny checks, each with its own message:

1. Bash + is_e2e_command(command) + needs_browser_repro(events) -> deny.
   Escape: BROWSER_REPRO_NA=1 literally present in the command string —
   asserts the failure is NOT browser-reproducible (a pure REST/CLI spec
   with no UI flow). Honored only when present; never auto-applied.
2. Agent|Task + is_e2e_delegation(prompt) + needs_browser_repro(events) ->
   deny. No escape prefix for this tool — a genuinely non-browser rerun
   should go through Bash with BROWSER_REPRO_NA=1, not through a delegated
   agent that silently swaps a browser-repro requirement for a doc-reading
   requirement.

Fail-open on any error (never block real work over a hook bug) and on any
input the hook cannot parse into a clear judgment — same posture as the
other pre gates in this project.
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
    from swe_hooks.core.stream import get_stream_path
    from swe_hooks.core.browser_repro import (
        is_e2e_command, is_e2e_delegation, needs_browser_repro,
        has_browser_repro_na,
    )
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PreToolUse")


DENY_MESSAGE = (
    "⛔ BROWSER REPRO FIRST — an E2E run failed and the failing flow has not "
    "been reproduced in the browser since. Reproduce the EXACT failing "
    "steps in mcp__browser-devtools__* (scenario-list → scenario-run login "
    "→ navigate → perform the failing interaction → read console/network/"
    "a11y) and capture what actually happens BEFORE any rerun, fix, or "
    "rerun-delegation. Theorizing between reruns is the failure mode this "
    "gate blocks. Canon: feedback/FEEDBACK_TDD_FOR_BUG_FIXES (browser-repro "
    "section)."
)


def _needs_repro_full_stream(input_data: dict) -> bool:
    """needs_browser_repro() over the ENTIRE session stream (not just since
    the current task boundary) — an unreproduced failure from an earlier
    task must still block a new E2E run/delegation in a later task."""
    transcript_path = get_input_field(input_data, 'transcript_path', default='')
    session_id = extract_session_id(transcript_path)
    if not session_id:
        return False
    stream_path = get_stream_path(session_id)
    if not os.path.exists(stream_path):
        return False
    try:
        with open(stream_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except IOError:
        return False
    events = []
    for line in lines:
        try:
            events.append(json.loads(line.strip()))
        except (json.JSONDecodeError, ValueError):
            continue
    return needs_browser_repro(events)


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        tool_name = get_input_field(input_data, 'tool_name', default='')

        if tool_name == 'Bash':
            command = get_input_field(input_data, 'tool_input', 'command', default='')
            if not command or not is_e2e_command(command):
                output_empty()
                return
            if has_browser_repro_na(command):
                output_empty()
                return
            if _needs_repro_full_stream(input_data):
                output_block(DENY_MESSAGE)
                return
            output_empty()
            return

        if tool_name in ('Agent', 'Task'):
            tool_input = input_data.get('tool_input', {}) or {}
            prompt = str(tool_input.get('prompt') or '')
            if not is_e2e_delegation(prompt):
                output_empty()
                return
            if _needs_repro_full_stream(input_data):
                output_block(DENY_MESSAGE)
                return
            output_empty()
            return

        output_empty()

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                         "additionalContext": f"Browser repro gate error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
