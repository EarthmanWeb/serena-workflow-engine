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
"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.output import output_empty, output_message
    from swe_hooks.core.session import extract_session_id
    from swe_hooks.core.stream import get_stream_path, append_event
    from swe_hooks.core.doc_claims import (
        find_wm_claims, near_match, stream_has_event_key)
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
        if tool_name != 'Bash':
            output_empty()
            return
        tool_input = input_data.get('tool_input', {}) or {}
        command = str(tool_input.get('command', ''))
        if not command:
            output_empty()
            return

        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)
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
