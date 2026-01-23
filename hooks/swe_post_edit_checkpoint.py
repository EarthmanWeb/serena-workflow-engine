#!/usr/bin/env python3
"""PostToolUse hook for Edit - Checkpoint enforcement.

Tracks edit count and BLOCKS further edits after threshold until WORKING_MEMORY is updated.
Uses session isolation for edit counting and persistence to WM file.

ENFORCEMENT: This hook converts soft reminders to hard blocking per SPEC_WORKING_MEMORY_ENFORCEMENT.
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
    from swe_hooks.core.output import HookOutput, output_empty, output_status
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.state_manager import StateManager
    from swe_hooks.core.session import extract_session_id, find_working_memory_for_session
    from swe_hooks.core.config import (
        persist_edit_to_wm, check_wm_staleness, check_wm_progress_updated
    )
except ImportError as e:
    output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"SWE import error: {e}"}}
    print(json.dumps(output), file=sys.stdout)
    sys.exit(0)

# Edit threshold before checkpoint is REQUIRED (not just reminded)
CHECKPOINT_THRESHOLD = 3


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())

        # Extract session ID for session isolation
        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)

        # Get edited file path if available
        tool_input = input_data.get('tool_input', {})
        edited_file = tool_input.get('file_path', '') or tool_input.get('path', '')

        # Find working memory for this session
        wm_filepath = find_working_memory_for_session(cwd, session_id)
        
        if not wm_filepath:
            # No working memory yet - use in-memory tracking only
            state_mgr = StateManager(cwd, session_id=session_id)
            count = state_mgr.increment_edits()
            
            if state_mgr.should_checkpoint(CHECKPOINT_THRESHOLD):
                output = HookOutput(event_name="PostToolUse")
                output.add_message(f"💾 CHECKPOINT: {count} edits - Create WORKING_MEMORY first")
                state_mgr.reset_edit_counter()
                output.output_and_exit()
                return
            
            output_status(f"WM: edit #{count} (no WM yet)")
            return

        # Persist edit to working memory file
        success, edit_count = persist_edit_to_wm(cwd, wm_filepath, edited_file)
        
        if not success:
            # Fallback to in-memory tracking
            state_mgr = StateManager(cwd, session_id=session_id)
            edit_count = state_mgr.increment_edits()

        # Check if checkpoint is needed
        if edit_count >= CHECKPOINT_THRESHOLD:
            # Check if WM was updated (progress section has content)
            wm_updated = check_wm_progress_updated(cwd, wm_filepath)
            
            if not wm_updated:
                # BLOCK: WM is stale, require update
                output = HookOutput(event_name="PostToolUse")
                output.add_message(f"""🛑 CHECKPOINT REQUIRED: {edit_count} edits since last update

You have made {edit_count} edits without updating WORKING_MEMORY.

**UPDATE WORKING_MEMORY NOW:**
1. Update `## Progress` section with completed work
2. Mark completed items with `[x]`
3. Update `**Files:**` with files you've edited
4. Verify `## Workflow Context` is current

After updating, you may continue editing.""")
                output.output_and_exit()
                return
            else:
                # WM was updated - this is just a notification
                output = HookOutput(event_name="PostToolUse")
                output.add_message(f"💾 Edit tracked ({edit_count} total)")
                output.output_and_exit()
                return

        # Under threshold - just track silently with concise status
        output_status(f"WM: edit #{edit_count}")

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"Checkpoint error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
