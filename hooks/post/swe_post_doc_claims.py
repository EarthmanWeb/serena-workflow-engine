#!/usr/bin/env python3
"""PostToolUse hook (Bash) — doc-claim substitution detector (C6).

A SUCCESSFUL Bash call whose command near-matches a WM '## Doc Claims Used'
ledger claim (same key, different value — e.g. documented 'sps-wpms.local',
used 'sps-wpms-master.local') is a SILENT doc substitution: the model worked
around a wrong/stale memory value without reconciling the doc. This hook
surfaces it: correct the memory now, or record in WM why the doc is right
and this value is the exception.

Matching lives in core.doc_claims.near_match — deliberately dumb, favors
false positives. Rows already 'corrected' are excluded (their substitution
is the sanctioned, recorded exception).

This hook runs on EVERY Bash call, so the no-ledger fast path is one stat:
find_wm_claims is a single open() attempt that returns [] when the WM file
is absent. Silent ({}) on no ledger / no match. One emission per
(claim, used) pair per session via a 'claim_subst' stream event.

Informational only — PostToolUse cannot block, and this hook never does.

Spawned agents (is_spawned_agent/is_subagent_transcript): early
output_empty(), no stream event, no substitution text — a subagent's Bash
call is checked against its own task, not the orchestrator's WM ledger.

ALSO carries half of the browser-repro-first gate (core.browser_repro,
swe_pre_browser_repro_gate.py): a Bash E2E (Playwright) run redirected to a
log file exits 0 at the shell level even when the spec itself failed — that
never reaches PostToolUseFailure (swe_post_tool_failure.py handles the
genuine-nonzero-exit half). This successful-PostToolUse hook reads the
captured tool_response/tool_result for a Playwright failure marker
(is_failed_e2e_output) and logs 'e2e_fail' when found — checked BEFORE the
spawned-agent early-return above, since an e2e_fail from a subagent must
still trip the gate for everyone.
"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.output import output_empty, output_message
    from swe_hooks.core.session import (
        extract_session_id, is_spawned_agent, is_subagent_transcript, get_agent_id)
    from swe_hooks.core.stream import get_stream_path, append_event
    from swe_hooks.core.doc_claims import (
        find_wm_claims, near_match, stream_has_event_key)
    from swe_hooks.core.browser_repro import is_e2e_command, is_failed_e2e_output
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PostToolUse")


def substitution_message(claim: dict, used: str) -> str:
    """The C6 reconciliation instruction for a detected substitution."""
    return (
        "You substituted '{used}' for documented '{claim}' (mem:{name}). "
        "Correct the memory now or record in WM why the doc is right and "
        "your value is the exception.".format(
            used=used, claim=claim['claim'], name=claim['name'])
    )


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)

        tool_name = get_input_field(input_data, 'tool_name', default='')
        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        tool_input = input_data.get('tool_input', {}) or {}
        command = str(tool_input.get('command', ''))
        session_id = extract_session_id(transcript_path)

        # Browser-repro-first gate (core.browser_repro), BEFORE the spawned-
        # agent early-return below: an E2E (Playwright) run that exits 0 at
        # the SHELL level (redirected to a log, `... ; echo exit $?`) but
        # shows a Playwright failure in its own captured output never reaches
        # PostToolUseFailure (that only fires on a genuine nonzero exit) — so
        # THIS successful-PostToolUse hook is where that failure class is
        # caught. Recorded for spawned agents too (an e2e_fail from any
        # agent must still trip the gate for everyone), unlike the doc-claims
        # check below, which is orchestrator-WM-only.
        if tool_name == 'Bash' and command and session_id:
            raw_output = str(get_input_field(
                input_data, 'tool_response', default='')) or str(
                get_input_field(input_data, 'tool_result', default=''))
            if is_e2e_command(command) and is_failed_e2e_output(raw_output):
                stream_path = get_stream_path(session_id)
                e2e_fail_kwargs = {'s': session_id}
                e2e_agent_id = get_agent_id(input_data)
                if e2e_agent_id:
                    e2e_fail_kwargs['agent'] = e2e_agent_id
                append_event(stream_path, 'e2e_fail', **e2e_fail_kwargs)

        # Spawned agents are not orchestrators — their Bash calls are not
        # checked against the orchestrator's WM Doc Claims ledger.
        if is_spawned_agent(input_data) or is_subagent_transcript(transcript_path):
            output_empty()
            return

        if tool_name != 'Bash':
            output_empty()
            return
        if not command:
            output_empty()
            return

        if not session_id:
            output_empty()
            return

        # No-ledger fast path: one open() attempt inside find_wm_claims.
        cwd = get_input_field(input_data, 'cwd', default='') or os.getcwd()
        claims = find_wm_claims(cwd, session_id)
        # 'corrected' rows already record the sanctioned exception — matching
        # them would flag exactly the value the ledger blessed.
        claims = [c for c in claims if c['status'] != 'corrected']
        if not claims:
            output_empty()
            return

        hit = near_match(claims, command)
        if not hit:
            output_empty()
            return
        claim, used = hit

        # One emission per (claim, used) pair per session.
        stream_path = get_stream_path(session_id)
        key = f"{claim['name']}::{claim['claim']}::{used}"
        if stream_has_event_key(stream_path, 'claim_subst', key):
            output_empty()
            return
        append_event(stream_path, 'claim_subst', k=key, s=session_id)
        output_message(substitution_message(claim, used), "PostToolUse")

    except Exception:
        output_empty()


if __name__ == '__main__':
    main()
