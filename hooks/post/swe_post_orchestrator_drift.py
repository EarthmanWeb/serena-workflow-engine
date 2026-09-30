#!/usr/bin/env python3
"""PostToolUse hook for main-agent task-work tools — orchestrator-drift nudge.

Counts consecutive direct task-work calls (Edit, Write, NotebookEdit, Serena
edit tools, Bash) made by the MAIN agent since the last Agent/Workflow launch
in this session. At DRIFT_THRESHOLD (6), nudges the orchestrator to stop
doing the work itself and split what remains into parallel subagents — the
"orchestrator + swarm delegation" model this session is meant to follow
(FEATURE_SUBAGENTS). At DRIFT_HARD_THRESHOLD (12), the advisory escalates
into a MANDATE: split remaining work into parallel subagents NOW, or record a
'single-agent: <reason>' override in the WM Context section — the sibling
PreToolUse edit gate (swe_pre_edit_validate.py) hard-enforces this same
threshold by DENYING further edits without that override.

An Agent or Workflow call resets the streak (the orchestrator just
delegated). Informational only — PostToolUse cannot block, and this hook
never does.

Exempt when the calling tool itself IS an Agent/Workflow launch — that event
is the reset marker, not task work, and is recorded as 'delegation' instead
of 'task_work' by this same hook (registered on both matchers so one script
covers count + reset).

Also exempt: a Bash call whose PRIMARY command is verification/inspection
rather than task work — git status/diff/log/show/commit/add, test runners
(python3 -m unittest / pytest / npm test), py_compile, jq ., and the
project's own validate-*.py scripts. Checking your own work, or reading
codebase state to decide what to do next, is not "doing the work itself" in
the sense this nudge targets; counting it as task work produced false
positives that nudged delegation mid-verification.
"""

import os
import re
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import HookOutput, output_status, output_empty
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.session import extract_session_id, is_spawned_agent, is_subagent_transcript
    from swe_hooks.core.stream import (
        get_stream_path, append_event, count_task_work_since_delegation,
        DRIFT_HARD_THRESHOLD,
    )
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e)

# Consecutive direct task-work calls before the advisory drift nudge.
DRIFT_THRESHOLD = 6

# At this streak, the advisory becomes a MANDATE (see core.stream for the
# shared constant the sibling edit gate also enforces against).
MANDATE_TEXT = (
    "STOP doing the work yourself. Split the remaining work and launch "
    "parallel subagents NOW (haiku=routine/recon/tests, sonnet=implementation "
    "— FEATURE_SUBAGENTS). For a genuinely tight single-file coupled fix, "
    "record 'single-agent: <reason>' in the WM Context section to continue "
    "solo; the edit gate blocks further edits otherwise."
)

DELEGATION_TOOL_NAMES = {'Agent', 'Task', 'Workflow'}

# Bash commands whose PRIMARY (first pipeline-group) stage is verification —
# checking state or running tests/compiles — rather than doing task work.
BASH_GROUP_SPLIT_RE = re.compile(r'(?:;|&&|\|\||&|\n)+')
BASH_PIPE_SPLIT_RE = re.compile(r'\|(?!\|)')
BASH_ENV_ASSIGN_RE = re.compile(
    r'^(?:[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|\'[^\']*\'|\S*)\s+)*')
BASH_VERIFICATION_FIRST_RE = re.compile(
    r'^(?:'
    r'git\s+(?:status|diff|log|show|commit|add)\b'
    r'|python3?\s+-m\s+(?:unittest|py_compile|pytest)\b'
    r'|pytest\b'
    r'|npm\s+(?:test|run\s+test)\b'
    r'|jq\s+\.'
    r'|(?:python3?\s+)?(?:scripts/)?validate-[\w.-]*\.py\b'
    r')',
    re.IGNORECASE,
)


def bash_is_verification(command: str) -> bool:
    """True when EVERY command group in `command` is a verification/inspection
    call (see BASH_VERIFICATION_FIRST_RE) — the whole Bash call is checking
    state, not doing task work. A mixed group (e.g. `edit-ish-thing && git
    status`) still counts as task work: any non-verification group disqualifies
    the whole call from exemption."""
    if not command:
        return False
    groups = [g for g in BASH_GROUP_SPLIT_RE.split(command) if g.strip()]
    if not groups:
        return False
    for group in groups:
        first_stage = BASH_PIPE_SPLIT_RE.split(group, 1)[0].strip()
        first_stage = BASH_ENV_ASSIGN_RE.sub('', first_stage)
        if not BASH_VERIFICATION_FIRST_RE.match(first_stage):
            return False
    return True


def is_task_work(tool_name: str, tool_input: dict) -> bool:
    """True when this tool call counts toward the orchestrator-drift streak.

    Everything the matcher routes here counts as task work EXCEPT a Bash call
    that is entirely verification/inspection (see bash_is_verification).
    """
    if tool_name == 'Bash':
        command = str((tool_input or {}).get('command', ''))
        return not bash_is_verification(command)
    return True


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
        tool_input = get_input_field(input_data, 'tool_input', default={})
        stream_path = get_stream_path(session_id)

        if tool_name in DELEGATION_TOOL_NAMES:
            append_event(stream_path, 'delegation', tool=tool_name, s=session_id)
            output_status("\U0001f501 delegation logged — drift counter reset")
            return

        if not is_task_work(tool_name, tool_input):
            output_status(f"✓ verification call exempt from drift count: {tool_name}")
            return

        append_event(stream_path, 'task_work', tool=tool_name, s=session_id)
        drift_count = count_task_work_since_delegation(stream_path)

        if drift_count >= DRIFT_HARD_THRESHOLD:
            output = HookOutput(event_name="PostToolUse")
            output.add_message(
                f"Orchestrator drift: {drift_count} direct task-work calls without "
                f"delegating (>= hard threshold {DRIFT_HARD_THRESHOLD}). "
                + MANDATE_TEXT
            )
            output.output_and_exit()
            return

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
