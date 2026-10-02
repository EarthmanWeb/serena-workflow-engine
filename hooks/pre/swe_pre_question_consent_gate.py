#!/usr/bin/env python3
"""PreToolUse hook for AskUserQuestion — blanket-consent gate.

When the operator has granted blanket consent for the CURRENT TASK with an
explicit no-question phrase ("no questions", "don't ask me (any) questions",
"don't ask me anything", "skip all questions"), the agent must NOT stop to ask
scope/approach questions mid-task — it picks the most logical option, acts,
and queues the decision as a deferred Open Decisions entry.

Mechanism: WF_ARCH_REVIEW notes `blanket_consent: true` in the session WM
(an explicit no-question phrase only — see wf/WF_ARCH_REVIEW Consent-Skip
Check). While that flag is present, AskUserQuestion is DENIED unless the
call explicitly overrides. `auto_approve: true` (WF_CLASSIFY 2b) is a
SEPARATE flag that only skips the WF_ARCH_REVIEW plan-approval question —
it NEVER denies AskUserQuestion.

Override: include the literal tag [consent-override] in a question's text plus
the reason — reserved for destructive actions or genuine scope changes that
blanket consent cannot cover. The tag is an assertion, not a bypass.

WF_DONE: ALLOWED regardless of consent — the completion round asks every
`— deferred: chose <X>` Open Decisions entry queued under blanket consent.
The flag itself is cleared on WF_CLASSIFY re-entry (StateManager.transition_to).
"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import output_empty, output_block
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.session import extract_session_id, wm_has_blanket_consent
    from swe_hooks.core.state_manager import StateManager
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PreToolUse")

OVERRIDE_TAG = '[consent-override]'


def question_denied(blanket_consent: bool, current_state: str, tool_input) -> bool:
    """True when AskUserQuestion must be denied: blanket consent active,
    not in the WF_DONE completion round, and no [consent-override] tag."""
    if not blanket_consent or current_state == 'WF_DONE':
        return False
    return OVERRIDE_TAG not in json.dumps(tool_input)


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

        current_state = StateManager(cwd, session_id=session_id).get_current_state()
        if not question_denied(True, current_state,
                               input_data.get('tool_input', {})):
            output_empty()
            return

        output_block(
            "🚫 BLANKET CONSENT IS ACTIVE for this session (WM flag "
            "blanket_consent: true — the operator said no questions "
            "for this task).\n\n"
            "Do NOT stop to ask scope/approach questions now. Pick the most "
            "logical option from the loaded memories and existing patterns, act "
            "on it, and RECORD it in WM `## Open Decisions` as "
            "`- [ ] <decision> — options: A | B — deferred: chose <A>` — every "
            "deferred entry is asked via AskUserQuestion at WF_DONE.\n\n"
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
