#!/usr/bin/env python3
"""PreToolUse hook for task_orchestrate - Enforce WF_SWARM_ORCHESTRATE read.

Ensures the AI has read the swarm orchestration workflow instructions before
launching multi-agent task orchestration.

ENFORCEMENT: Blocks task_orchestrate until WF_SWARM_ORCHESTRATE is visited.
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
    from swe_hooks.core.output import HookOutput, output_status
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.state_manager import StateManager
    from swe_hooks.core.session import extract_session_id, find_working_memory_for_session
except ImportError as e:
    output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": f"SWE import error: {e}"}}
    print(json.dumps(output), file=sys.stdout)
    sys.exit(0)

# States that indicate swarm orchestration workflow has been visited
SWARM_ALLOWED_STATES = {'WF_SWARM_ORCHESTRATE', 'WF_EXECUTE'}


def check_swarm_orchestrate_visited(wm_filepath):
    """Check if WF_SWARM_ORCHESTRATE has been visited in the workflow.

    Returns: tuple (bool, str) - (is_valid, diagnostic_message)
    """
    if not wm_filepath or not os.path.exists(wm_filepath):
        return False, "No working memory found"

    try:
        with open(wm_filepath, 'r') as f:
            content = f.read()

        # Check for evidence of swarm orchestration workflow visit
        swarm_indicators = [
            'WF_SWARM_ORCHESTRATE',
            '## Swarm Orchestration',
            'swarm_orchestrate',
        ]

        for indicator in swarm_indicators:
            if indicator in content:
                return True, "Swarm orchestration context found"

        return False, "WF_SWARM_ORCHESTRATE not visited"

    except Exception as e:
        return False, f"Error reading WM: {e}"


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())

        # Extract session ID for session isolation
        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)

        # Find working memory for this session
        wm_filepath = find_working_memory_for_session(cwd, session_id)

        # Create state manager with session isolation
        state_mgr = StateManager(cwd, session_id=session_id)
        current = state_mgr.get_current_state()

        # Allow if already in swarm orchestration or execute states
        if current in SWARM_ALLOWED_STATES:
            output_status(f"✓ task_orchestrate allowed ({current})", event="PreToolUse")
            return

        # Check if swarm orchestrate was visited
        is_valid, diagnostic = check_swarm_orchestrate_visited(wm_filepath)

        if is_valid:
            output_status("✓ task_orchestrate allowed (swarm context found)", event="PreToolUse")
            return

        # BLOCK: WF_SWARM_ORCHESTRATE not visited
        output = HookOutput(event_name="PreToolUse")
        output.block(f"""🛑 BLOCKED: WF_SWARM_ORCHESTRATE not read

Before using task_orchestrate, you MUST read the swarm orchestration workflow.

**MANDATORY ACTION - Call this tool NOW:**
   → mcp__plugin_swe_serena__read_memory(memory_file_name="WF_SWARM_ORCHESTRATE")

This ensures you understand:
- Proper swarm topology selection
- Agent coordination patterns
- Memory synchronization requirements
- Error handling for distributed tasks

Diagnostic: {diagnostic}
Current state: {current}""")
        output.output_and_exit()

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": f"Task orchestrate gate error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
