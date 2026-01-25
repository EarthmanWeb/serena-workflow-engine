#!/usr/bin/env python3
"""PreToolUse hook for Edit/Write - Validate state and check staleness.

Ensures edits only happen in appropriate workflow states.
BLOCKS edits if WM is stale (>3 edits without update).
Uses session isolation for state checking.

ENFORCEMENT: This hook adds staleness blocking per SPEC_WM_ENFORCEMENT.
"""

import os
import sys
import json

PLUGIN_ROOT = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
if PLUGIN_ROOT:
    hooks_dir = os.path.join(PLUGIN_ROOT, 'hooks')
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)

try:
    from swe_hooks.core.output import HookOutput, output_empty, output_block, output_status
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.state_manager import StateManager
    from swe_hooks.core.session import extract_session_id, find_working_memory_for_session
    from swe_hooks.core.config import check_wm_staleness
except ImportError as e:
    output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": f"SWE import error: {e}"}}
    print(json.dumps(output), file=sys.stdout)
    sys.exit(0)

# States where edits are allowed
EDIT_ALLOWED = {'WF_EXECUTE', 'WF_DEBUG_TDD', 'WF_CHECKPOINT', 'WF_UPDATE_MEMORY', 'WF_CLEANUP', 'WF_INITIAL_SETUP', 'UNINITIALIZED', 'WF_INIT'}

# States where edits should show a warning
WARN_STATES = {'WF_PLAN_ARCHITECTURE', 'WF_ARCH_REVIEW', 'WF_RESEARCH'}

# Edit threshold for staleness check
STALENESS_THRESHOLD = 3


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())

        # Extract session ID for session isolation
        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)

        # Find working memory for this session
        wm_filepath = find_working_memory_for_session(cwd, session_id)

        # Check staleness FIRST (before state check)
        if wm_filepath:
            is_stale, edit_count, last_updated = check_wm_staleness(
                cwd, wm_filepath, STALENESS_THRESHOLD
            )
            
            if is_stale:
                # BLOCK: WM is stale
                output = HookOutput(event_name="PreToolUse")
                output.block(f"""🛑 WM STALE

Your WM is outdated ({edit_count} edits since last update).

**UPDATE WM before continuing edits:**
1. Update `## Progress` section with completed work
2. Mark completed items with `[x]`
3. Update `**Files:**` with files you've edited

After updating WM, you may continue editing.""")
                output.output_and_exit()
                return

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

        # Default: allow the edit (don't block workflow)
        output_status(f"✓ Edit allowed ({current})", event="PreToolUse")

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": f"Pre-edit error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
