#!/usr/bin/env python3
"""UserPromptSubmit hook - Ensure workflow state and provide instructions."""

import os
import sys
import json

PLUGIN_ROOT = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
if PLUGIN_ROOT:
    hooks_dir = os.path.join(PLUGIN_ROOT, 'hooks')
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)

try:
    from swe_hooks.core.config import load_setup_complete
    from swe_hooks.core.state_manager import StateManager
except ImportError as e:
    print(json.dumps({"systemMessage": f"SWE import error: {e}"}), file=sys.stdout)
    sys.exit(0)





def main():
    try:
        # Read input
        input_data = {}
        try:
            input_data = json.load(sys.stdin)
        except:
            pass
        
        prompt = input_data.get('prompt', '')
        cwd = input_data.get('cwd', os.getcwd())
        
        if not prompt or not prompt.strip():
            sys.exit(0)
        
        # Check setup
        setup = load_setup_complete(cwd)
        if not setup or not setup.get('complete'):
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": "⚠️ SWE not initialized. Run /swe-init first."
                }
            }
            print(json.dumps(output))
            sys.exit(0)
        
        # Get current state
        state_mgr = StateManager(cwd)
        current_state = state_mgr.get_current_state()
        
        # Transition to WF_INIT if needed
        if current_state in ['UNINITIALIZED', 'WF_DONE', 'WF_CLEANUP', None]:
            state_mgr.transition_to('WF_INIT')
            current_state = 'WF_INIT'
        
        # Get working memory
        wm_file = state_mgr.get_working_memory()
        
        context = f"""📋 WORKFLOW STATE: {current_state}
Working Memory: {wm_file or 'None'}

Follow the {current_state} instructions:
Use: mcp__serena__read_memory("{current_state}")
"""
        
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context
            }
        }
        print(json.dumps(output))
        sys.exit(0)
        
    except Exception as e:
        print(json.dumps({"systemMessage": f"Workflow hook error: {e}"}), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
