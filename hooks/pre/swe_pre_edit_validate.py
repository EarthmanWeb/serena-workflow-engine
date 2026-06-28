#!/usr/bin/env python3
"""PreToolUse hook for Edit/Write - Validate workflow state for edits.

Ensures edits only happen in appropriate workflow states.
No staleness blocking — checkpoint is informational only.
"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import HookOutput, output_status
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.state_manager import StateManager
    from swe_hooks.core.session import extract_session_id
    from swe_hooks.core.config import get_project_root, resolve_setup_state
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PreToolUse")

# States where edits are allowed
# WF_VERIFY may edit: verification must fix violations in place.
EDIT_ALLOWED = {'WF_EXECUTE', 'WF_DEBUG_TDD', 'WF_CHECKPOINT', 'WF_INITIAL_SETUP', 'WF_ONBOARD', 'WF_VERIFY'}

# States where edits should show a warning
WARN_STATES = {'WF_ARCH_REVIEW', 'WF_RESEARCH'}


def _is_bypass_write_attempt(input_data):
    """True if this Edit/Write would enable the project bypass.

    The bypass ("bypass": true in swe-setup-complete.json) may ONLY be set by
    the user via /swe-bypass — never by the assistant, under any rationalization.
    This guard makes it un-settable by an LLM tool call regardless of intent:
    any Edit/Write/write_memory that targets swe-setup-complete.json AND
    introduces a truthy bypass is hard-blocked here, before the state check.
    """
    tool_input = input_data.get('tool_input', {}) or {}
    target = (
        tool_input.get('file_path')
        or tool_input.get('memory_name')
        or ''
    )
    if 'swe-setup-complete' not in str(target):
        return False
    # Gather any content this call would write.
    blob = ' '.join(str(tool_input.get(k, '')) for k in (
        'content', 'new_string', 'new_str', 'replacement', 'repl',
    ))
    normalized = blob.replace(' ', '').replace("'", '"').lower()
    # Match "bypass":true / "bypass": true (whitespace/quote-insensitive)
    return '"bypass":true' in normalized


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())

        # HARD GUARD (runs before any state logic): the assistant may NEVER
        # set the project bypass. Only the user, via /swe-bypass, can do that.
        if _is_bypass_write_attempt(input_data):
            output = HookOutput(event_name="PreToolUse")
            output.block(
                "🛑 BLOCKED: the SWE workflow bypass can only be enabled by the "
                "user via the /swe-bypass command — never by the assistant.\n"
                "Do not edit swe-setup-complete.json to add \"bypass\": true. "
                "If the user wants to disable the workflow, tell them to run "
                "/swe-bypass themselves."
            )
            output.output_and_exit()
            return

        # Project-level bypass: if "bypass": true in swe-setup-complete.json,
        # skip the state-based edit gate entirely — same as the init gate does.
        # Runs AFTER the hard-guard above so a bypassed project still cannot have
        # the assistant flip the flag further. SessionStart announces the bypass.
        try:
            project_root = get_project_root()
            if resolve_setup_state(project_root).get('bypassed'):
                output_status("✓ Edit allowed (bypassed)", event="PreToolUse")
                return
        except Exception:
            pass  # bypass check is best-effort; fall through to state gate

        # Extract session ID for session isolation
        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)

        # Create state manager with session isolation
        state_mgr = StateManager(cwd, session_id=session_id)
        current = state_mgr.get_current_state()

        # Allow edits in execution states
        if current in EDIT_ALLOWED:
            output_status(f"✓ Edit allowed ({current})", event="PreToolUse")
            return

        # Warn but allow in planning states
        if current in WARN_STATES:
            output = HookOutput(event_name="PreToolUse")
            output.add_message(f"⚠️ Edit in planning state: {current}")
            output.output_and_exit()
            return

        # BLOCK: editing not allowed in this state
        output = HookOutput(event_name="PreToolUse")
        output.block(f"🛑 Edit blocked in state {current}. Move to WF_EXECUTE first.")
        output.output_and_exit()

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": f"Pre-edit error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
