#!/usr/bin/env python3
"""SessionStart hook - Initialize WF_INIT workflow and working memory."""

import os
import sys
import json
from datetime import datetime

PLUGIN_ROOT = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
if PLUGIN_ROOT:
    hooks_dir = os.path.join(PLUGIN_ROOT, 'hooks')
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)

try:
    from swe_hooks.core.config import (
        load_setup_complete, load_workflow_state, save_workflow_state, 
        create_initial_state
    )
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
        
        cwd = input_data.get('cwd', os.getcwd())
        session_id = input_data.get('session_id', datetime.now().strftime('%Y%m%d_%H%M%S'))

        # Check setup
        setup = load_setup_complete(cwd)
        if not setup or not setup.get('complete'):
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "⚠️ SERENA WORKFLOW ENGINE not initialized. Run /swe-init first."
                }
            }
            print(json.dumps(output))
            sys.exit(0)

        # Initialize or load state
        state_mgr = StateManager(cwd)
        current_state = state_mgr.get_current_state()
        
        # Transition to WF_INIT if uninitialized or completed
        if current_state in ['UNINITIALIZED', 'WF_DONE', 'WF_CLEANUP', None]:
            state_mgr.transition_to('WF_INIT')
            current_state = 'WF_INIT'
        
        # Update session info
        state = load_workflow_state(cwd) or create_initial_state()
        state['session_id'] = session_id
        state['session_start'] = datetime.now().isoformat()
        save_workflow_state(cwd, state)
        
        # Build context message
        wm_file = state.get('working_memory_file')
        
        if current_state == 'WF_INIT':
            context = f"""🚀 SERENA WORKFLOW ENGINE - Session {session_id}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Current State: WF_INIT
Working Memory: {wm_file or 'Not created yet'}

MANDATORY: Read and follow the WF_INIT workflow instructions.
Use: mcp__serena__read_memory("WF_INIT")
"""
        else:
            context = f"""🔄 SERENA WORKFLOW ENGINE - Resuming Session {session_id}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Current State: {current_state}
Working Memory: {wm_file or 'None'}

MANDATORY: Read and follow the {current_state} workflow instructions.
Use: mcp__serena__read_memory("{current_state}")
"""

        output = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context
            }
        }
        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        print(json.dumps({"systemMessage": f"Session start error: {e}"}), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
