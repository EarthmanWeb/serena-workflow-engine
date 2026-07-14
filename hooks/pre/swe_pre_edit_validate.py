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


def _is_raw_memory_write(input_data):
    """True if a raw Edit/Write targets a Serena memory file.

    Memory files under .serena/memory/ and .serena/memories/ must be edited
    via Serena's write_memory/edit_memory tools (which keep frontmatter,
    indexing hooks, and sync behavior intact) — never via raw Edit/Write.
    Exception: session Working Memory (WM_*.md), which the harness/daemon
    writes with the Write tool by design.
    """
    if input_data.get('tool_name', '') not in ('Edit', 'Write'):
        return False
    file_path = str((input_data.get('tool_input') or {}).get('file_path', ''))
    norm = file_path.replace('\\', '/')
    if '/.serena/memory/' not in norm and '/.serena/memories/' not in norm:
        return False
    return not os.path.basename(norm).startswith('WM_')


def _block_message(current):
    """Build the edit-block message, tailored to the blocking state.

    WF_CLASSIFY is the common case: the assistant tried to edit the target file
    before routing. The message explains WHY (classification-only state) and what
    to do (finish routing, then transition) so it self-corrects instead of
    retrying the same blocked edit.
    """
    if current == 'WF_CLASSIFY':
        return (
            "🛑 Edit blocked in WF_CLASSIFY — this is a classification/routing "
            "state, not an execution state. No edits happen here.\n"
            "You do NOT need to open or edit the target file to classify the task. "
            "Finish routing first:\n"
            "  1. Classify task type + count files touched (Step 3 / 3b)\n"
            "  2. Load the primary FEATURE_[KEY] (Step 4)\n"
            "  3. Transition: minor patch (≤5 files) → WF_EXECUTE; "
            "new feature / >5 files → WF_ARCH_REVIEW\n"
            "Then make the edit in WF_EXECUTE."
        )
    return (
        f"🛑 Edit blocked in state {current}. Edits are only allowed in "
        f"WF_EXECUTE / WF_DEBUG_TDD / WF_CHECKPOINT / WF_VERIFY. "
        f"Transition to WF_EXECUTE first."
    )


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

        # Raw Edit/Write on Serena memory files: always denied (state-independent).
        # Memories are edited via write_memory/edit_memory; WM_* files are exempt.
        if _is_raw_memory_write(input_data):
            output = HookOutput(event_name="PreToolUse")
            output.block(
                "🛑 BLOCKED: raw Edit/Write on a Serena memory file.\n"
                "Files under .serena/memory(ies)/ must be modified via Serena's "
                "memory tools:\n"
                "  - mcp__plugin_swe_serena__edit_memory(memory_name, needle, repl, mode)\n"
                "  - mcp__plugin_swe_serena__write_memory(memory_name, content)  # full rewrite\n"
                "Address the memory by its logical name (e.g. \"feature/FEATURE_X\"), "
                "not its file path."
            )
            output.output_and_exit()
            return

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
        output.block(_block_message(current))
        output.output_and_exit()

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": f"Pre-edit error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
