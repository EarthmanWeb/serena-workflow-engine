#!/usr/bin/env python3
"""PreToolUse gate - BLOCKS all tools until WF_INIT workflow is COMPLETED.

Initialization is NOT complete until:
1. WF_INIT is read
2. A WORKING_MEMORY file is created with workflow state FOR THIS SESSION

This hook ensures Claude CANNOT do anything until the full init workflow is done.
Session isolation: Each conversation must have its own working memory (matched by session ID).
"""

import os
import sys
import json
import glob
import re

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

def find_project_root(start_dir):
    """Walk up directory tree to find project root containing .serena folder."""
    current = os.path.abspath(start_dir)
    while current != os.path.dirname(current):  # Stop at filesystem root
        if os.path.isdir(os.path.join(current, '.serena')):
            return current
        current = os.path.dirname(current)
    return start_dir  # Fallback to original if not found

def get_serena_memories_dir(cwd):
    project_root = find_project_root(cwd)
    return os.path.join(project_root, '.serena', 'memories')

def extract_session_id(transcript_path):
    """Extract session ID from transcript_path UUID."""
    if not transcript_path:
        return None
    uuid_match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', transcript_path)
    if uuid_match:
        return uuid_match.group(1)[:8]
    return None

def check_working_memory_exists(cwd, session_id):
    """Check if a WORKING_MEMORY file exists for THIS SESSION with proper workflow state.

    Returns: tuple (bool, str) - (is_valid, diagnostic_message)
    """
    memories_dir = get_serena_memories_dir(cwd)
    if not os.path.exists(memories_dir):
        return False, "No .serena/memories directory found"

    # Look for WORKING_MEMORY_<session_id>_* files specifically
    if session_id:
        pattern = os.path.join(memories_dir, f'WORKING_MEMORY_{session_id}_*.md')
        working_memories = glob.glob(pattern)
    else:
        # Fallback: any working memory (legacy support)
        pattern = os.path.join(memories_dir, 'WORKING_MEMORY_*.md')
        working_memories = glob.glob(pattern)

    if not working_memories:
        return False, f"No WORKING_MEMORY_{session_id}_*.md file found"

    # Check the most recent one for workflow state
    latest = max(working_memories, key=os.path.getmtime)
    filename = os.path.basename(latest)

    try:
        with open(latest, 'r') as f:
            content = f.read()

            # Required patterns for valid workflow state
            required_patterns = [
                ('## Workflow Context', 'Section header'),
                ('**Current State**:', 'Current State field'),
            ]

            # Check for required patterns
            missing = []
            for pattern_str, desc in required_patterns:
                if pattern_str not in content:
                    missing.append(f"'{pattern_str}' ({desc})")

            if missing:
                # Check what WAS found (for diagnostic)
                found_patterns = []
                alt_patterns = [
                    ('## Workflow State', 'Wrong section header'),
                    ('**Current**:', 'Wrong field format'),
                    ('Current State:', 'Missing bold markers'),
                    ('Workflow State:', 'Legacy format'),
                ]
                for alt_pat, alt_desc in alt_patterns:
                    if alt_pat in content:
                        found_patterns.append(f"'{alt_pat}' ({alt_desc})")

                diag = f"File {filename} missing: {', '.join(missing)}"
                if found_patterns:
                    diag += f". Found instead: {', '.join(found_patterns)}"
                return False, diag

            # Verify session ID matches (if we have one)
            if session_id:
                session_match = re.search(r'\*\*Session ID\*\*:\s*(\S+)', content)
                if session_match and session_match.group(1) == session_id:
                    return True, "Valid"
                # Also check filename contains session ID
                if session_id in filename:
                    return True, "Valid"
                return False, f"Session ID mismatch: expected {session_id}, file has different ID"
            return True, "Valid"
    except Exception as e:
        return False, f"Error reading {filename}: {e}"

    return False, "Unknown validation failure"

def main():
    try:
        input_data = json.load(sys.stdin)
        tool_name = input_data.get('tool_name', '')
        cwd = input_data.get('cwd', os.getcwd())
        transcript_path = input_data.get('transcript_path', '')

        # Extract session ID from transcript_path
        session_id = extract_session_id(transcript_path)

        # Allow memory tools through (needed for initialization)
        if any(allowed in tool_name for allowed in ALLOWED_TOOLS):
            print(json.dumps({}))
            sys.exit(0)

        # Check if initialization is complete (WORKING_MEMORY exists with state FOR THIS SESSION)
        if check_working_memory_exists(cwd, session_id):
            # Initialized - allow through
            print(json.dumps({}))
            sys.exit(0)

        # NOT initialized - BLOCK the tool call
        output = {
            "decision": "block",
            "reason": f"""🛑 BLOCKED: Workflow initialization NOT complete for session {session_id or 'unknown'}.

You MUST complete the WF_INIT workflow BEFORE using any other tools:
1. Read WF_INIT: mcp__serena__read_memory("WF_INIT")
2. Follow its instructions to create WORKING_MEMORY_{session_id}_<descriptor> with workflow state

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
