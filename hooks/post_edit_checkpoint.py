#!/usr/bin/env python3
"""PostToolUse hook for Edit - Checkpoint tracking."""

import os
import sys
import json

PLUGIN_ROOT = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
if PLUGIN_ROOT:
    hooks_dir = os.path.join(PLUGIN_ROOT, 'hooks')
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)

try:
    from swe_hooks.core.output import HookOutput, output_empty
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.state_manager import StateManager
except ImportError as e:
    output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"SWE import error: {e}"}}
    print(json.dumps(output), file=sys.stdout)
    sys.exit(0)

def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())
        state_mgr = StateManager(cwd)
        count = state_mgr.increment_edits()
        if state_mgr.should_checkpoint(3):
            output = HookOutput(event_name="PostToolUse")
            output.add_message(f"💾 CHECKPOINT: {count} edits - Update WORKING_MEMORY")
            state_mgr.reset_edit_counter()
            output.output_and_exit()
        output_empty()
    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"Checkpoint error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)

if __name__ == '__main__':
    main()
