#!/usr/bin/env python3
"""PreToolUse gate - BLOCKS all tools until WF_INIT workflow is COMPLETED.

Initialization is NOT complete until:
1. WF_INIT is read
2. A WORKING_MEMORY file is created with workflow state

This hook ensures Claude CANNOT do anything until the full init workflow is done.
"""

import os
import sys
import json
import glob

PLUGIN_ROOT = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
if PLUGIN_ROOT:
    hooks_dir = os.path.join(PLUGIN_ROOT, 'hooks')
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)

# Tools that are ALLOWED before initialization
ALLOWED_TOOLS = [
    'mcp__plugin_serena-workflow-engine_serena__read_memory',
    'mcp__serena__read_memory',
    'mcp__plugin_serena-workflow-engine_serena__write_memory',
    'mcp__serena__write_memory',
    'mcp__plugin_serena-workflow-engine_serena__list_memories',
    'mcp__serena__list_memories',
]

def get_serena_memories_dir(cwd):
    return os.path.join(cwd, '.serena', 'memories')

def check_working_memory_exists(cwd):
    """Check if a WORKING_MEMORY file exists with proper workflow state."""
    memories_dir = get_serena_memories_dir(cwd)
    if not os.path.exists(memories_dir):
        return False

    # Look for WORKING_MEMORY_* files
    pattern = os.path.join(memories_dir, 'WORKING_MEMORY_*.md')
    working_memories = glob.glob(pattern)

    if not working_memories:
        return False

    # Check the most recent one for workflow state
    latest = max(working_memories, key=os.path.getmtime)
    try:
        with open(latest, 'r') as f:
            content = f.read()
            # Must have workflow state indicating initialization is complete
            # Check for any of the patterns used in working memory
            if any(pattern in content for pattern in [
                'Current State:',
                'Workflow State:',
                'Calling Step:',
                '## Workflow Context'
            ]):
                return True
    except:
        pass

    return False

def main():
    try:
        input_data = json.load(sys.stdin)
        tool_name = input_data.get('tool_name', '')
        cwd = input_data.get('cwd', os.getcwd())

        # Allow memory tools through (needed for initialization)
        if any(allowed in tool_name for allowed in ALLOWED_TOOLS):
            print(json.dumps({}))
            sys.exit(0)

        # Check if initialization is complete (WORKING_MEMORY exists with state)
        if check_working_memory_exists(cwd):
            # Initialized - allow through
            print(json.dumps({}))
            sys.exit(0)

        # NOT initialized - BLOCK the tool call
        output = {
            "decision": "block",
            "reason": """🛑 BLOCKED: Workflow initialization NOT complete.

You MUST complete the WF_INIT workflow BEFORE using any other tools:
1. Read WF_INIT: mcp__serena__read_memory("WF_INIT")
2. Follow its instructions to create WORKING_MEMORY with workflow state

NO EXCEPTIONS. Complete initialization first."""
        }
        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        # On error, don't block (fail open for safety)
        print(json.dumps({"systemMessage": f"Init gate error: {e}"}))
        sys.exit(0)

if __name__ == '__main__':
    main()
