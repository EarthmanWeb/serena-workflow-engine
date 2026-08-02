#!/usr/bin/env python3
"""PreToolUse hook for AskUserQuestion — blanket-consent gate.

When the operator has granted blanket consent for the session ("continue
through to completion", "all authorized", "you have your marching orders"),
the agent must NOT stop to ask scope/approach questions — it derives the most
logical choice and proceeds (session 264de5e5 Failure 7: agent asked twice
after explicit blanket authorization).

Mechanism: WF_CLASSIFY / WF_ARCH_REVIEW note `auto_approve: true` or
`blanket_consent: true` in the session WM. While either flag is present,
AskUserQuestion is DENIED unless the call explicitly overrides.

Override: include the literal tag [consent-override] in a question's text plus
the reason — reserved for destructive actions or genuine scope changes that
blanket consent cannot cover. The tag is an assertion, not a bypass.
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
    from swe_hooks.core.session import extract_session_id, find_working_memory_for_session
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PreToolUse")

CONSENT_FLAG_RE = re.compile(
    r'\b(blanket_consent|auto_approve)\s*:\s*true\b', re.IGNORECASE)
OVERRIDE_TAG = '[consent-override]'


def wm_has_blanket_consent(cwd: str, session_id: str) -> bool:
    """True when this session's WM carries a blanket-consent flag."""
    try:
        wm_filepath = find_working_memory_for_session(cwd, session_id)
        if not wm_filepath or not os.path.exists(wm_filepath):
            return False
        with open(wm_filepath, 'r', encoding='utf-8') as f:
            return bool(CONSENT_FLAG_RE.search(f.read()))
    except (IOError, OSError):
        return False


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)

        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)
        cwd = input_data.get('cwd', os.getcwd())
        if not session_id:
            output_empty()
            return

        if not wm_has_blanket_consent(cwd, session_id):
            output_empty()
            return

        # Explicit override present in the call → allowed.
        tool_input = input_data.get('tool_input', {})
        if OVERRIDE_TAG in json.dumps(tool_input):
            output_empty()
            return

        output_block(
            "🚫 BLANKET CONSENT IS ACTIVE for this session (WM flag "
            "blanket_consent/auto_approve: true — the operator already said to "
            "continue through to completion).\n\n"
            "Do NOT stop to ask scope/approach questions. Derive the most logical "
            "choice from the loaded memories and existing patterns, note the "
            "decision in WM, and proceed.\n\n"
            "Genuinely blocked on a DESTRUCTIVE action or a scope change blanket "
            "consent cannot cover? Re-call AskUserQuestion with the literal tag "
            "[consent-override] plus the reason inside the question text. The tag "
            "is an assertion that the stated condition holds — not a bypass."
        )

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                         "additionalContext": f"Consent gate error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
