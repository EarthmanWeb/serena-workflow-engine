#!/usr/bin/env python3
"""PostToolUse hook for read_memory - State transitions."""

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
    from swe_hooks.core.state_manager import StateManager, STATE_ICONS
except ImportError as e:
    output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"SWE import error: {e}"}}
    print(json.dumps(output), file=sys.stdout)
    sys.exit(0)

def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())
        memory_name = get_input_field(input_data, 'tool_input', 'memory_file_name', default='')
        if not memory_name or not memory_name.startswith('WF_'):
            output_empty()
        output = HookOutput(event_name="PostToolUse")
        state_mgr = StateManager(cwd)
        icon = STATE_ICONS.get(memory_name, '📍')
        current = state_mgr.get_current_state()
        output.add_message(f"{icon} ON STEP: {memory_name}")
        if current != memory_name:
            success, msg = state_mgr.transition_to(memory_name)
            output.add_message(msg)
        output.output_and_exit()
    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"Post-read error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)

if __name__ == '__main__':
    main()
