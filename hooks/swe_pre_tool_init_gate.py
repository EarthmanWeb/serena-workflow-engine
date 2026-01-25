#!/usr/bin/env python3
"""PreToolUse gate - BLOCKS all tools until workflow is initialized.

Requires WORKING_MEMORY file with proper workflow state.

Initialization is complete when:
- A WM_{session}_* file exists with proper workflow state

LITE MODE: Only available when user explicitly requests it (e.g., "/lite", "use lite mode").
Never offered as an automatic option.

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

# Tools that are ALWAYS ALLOWED before initialization (no path checking needed)
ALLOWED_TOOLS = [
    # ToolSearch - CRITICAL: needed to load deferred MCP tools (prevents deadlock)
    'ToolSearch',
    # Read - needed to read workflow files and understand context before WM creation
    'Read',
    # Memory tools (needed for reading WF_INIT and creating WORKING_MEMORY)
    'mcp__plugin_swe_serena__read_memory',
    'mcp__serena__read_memory',
    'mcp__plugin_swe_serena__write_memory',
    'mcp__serena__write_memory',
    'mcp__plugin_swe_serena__list_memories',
    'mcp__serena__list_memories',
    'mcp__plugin_swe_serena__edit_memory',
    'mcp__serena__edit_memory',
    'mcp__plugin_swe_serena__delete_memory',
    'mcp__serena__delete_memory',
    # Project activation tools (needed when no active project - chicken/egg problem)
    'mcp__plugin_swe_serena__activate_project',
    'mcp__serena__activate_project',
    'mcp__plugin_swe_serena__list_projects',
    'mcp__serena__list_projects',
    'mcp__plugin_swe_serena__add_project',
    'mcp__serena__add_project',
]

def is_working_memory_write(tool_name, tool_input):
    """Check if this is a Write to WORKING_MEMORY file (allowed for initialization)."""
    if tool_name != 'Write':
        return False
    file_path = tool_input.get('file_path', '')
    # Allow writes to WORKING_MEMORY files in .serena/memories/
    return '.serena/memories/WM_' in file_path and file_path.endswith('.md')

def find_project_root(start_dir):
    """Find the MAIN project root by walking up directory tree.

    Skips any .serena folders inside .claude/plugins/ (nested plugin repos).
    Returns the highest .serena folder in the tree (main project).
    """
    current = os.path.abspath(start_dir)
    main_project_root = None

    while current != os.path.dirname(current):  # Stop at filesystem root
        serena_dir = os.path.join(current, '.serena')
        if os.path.isdir(serena_dir):
            # Only accept if NOT inside a plugin directory
            if '/.claude/plugins/' not in current and '\\.claude\\plugins\\' not in current:
                # Keep updating - we want the HIGHEST in the tree (main project)
                main_project_root = current
        current = os.path.dirname(current)

    return main_project_root if main_project_root else start_dir

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

def check_lite_mode(cwd, session_id):
    """Check if lite mode is active for this session.

    Lite mode allows simple lookups without full WORKING_MEMORY overhead.
    Activated by creating LITE_MODE_{session_id} file in memories dir.

    Returns: bool - True if lite mode is active
    """
    if not session_id:
        return False

    memories_dir = get_serena_memories_dir(cwd)
    lite_marker = os.path.join(memories_dir, f'LITE_MODE_{session_id}.md')
    return os.path.exists(lite_marker)

def check_working_memory_exists(cwd, session_id):
    """Check if a WORKING_MEMORY file exists for THIS SESSION with proper workflow state.

    Returns: tuple (bool, str) - (is_valid, diagnostic_message)
    """
    memories_dir = get_serena_memories_dir(cwd)
    if not os.path.exists(memories_dir):
        return False, "No .serena/memories directory found"

    # Look for WM_<session_id>_* files specifically
    if session_id:
        pattern = os.path.join(memories_dir, f'WM_{session_id}_*.md')
        working_memories = glob.glob(pattern)
    else:
        # Fallback: any working memory (legacy support)
        pattern = os.path.join(memories_dir, 'WM_*.md')
        working_memories = glob.glob(pattern)

    if not working_memories:
        return False, f"No WM_{session_id}_*.md file found"

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

        tool_input = input_data.get('tool_input', {})

        # Allow memory tools through (needed for initialization)
        if any(allowed in tool_name for allowed in ALLOWED_TOOLS):
            print(json.dumps({}))
            sys.exit(0)

        # Allow Write to WORKING_MEMORY files (needed to create initialization file)
        if is_working_memory_write(tool_name, tool_input):
            print(json.dumps({}))
            sys.exit(0)

        # Check if LITE MODE is active (lightweight research path)
        if check_lite_mode(cwd, session_id):
            # Lite mode - allow through without full working memory
            print(json.dumps({"systemMessage": "🔎 LITE_MODE active - minimal workflow"}))
            sys.exit(0)

        # Check if full initialization is complete (WORKING_MEMORY exists with state FOR THIS SESSION)
        is_valid, diagnostic = check_working_memory_exists(cwd, session_id)
        if is_valid:
            # Initialized - allow through
            print(json.dumps({}))
            sys.exit(0)

        # NOT initialized - BLOCK the tool call with specific diagnostic
        # NOTE: WM should have been auto-created by session_start hook
        # DEBUG: Show where we're looking
        memories_dir = get_serena_memories_dir(cwd)
        project_root = find_project_root(cwd)
        output = {
            "decision": "block",
            "reason": f"""🛑🛑🛑 CRITICAL: WORKFLOW NOT INITIALIZED - ALL TOOLS BLOCKED 🛑🛑🛑

Session: {session_id or 'unknown'}
Diagnostic: {diagnostic}
DEBUG - cwd: {cwd}
DEBUG - project_root: {project_root}
DEBUG - memories_dir: {memories_dir}

═══════════════════════════════════════════════════════════════════════════════
                    ⚠️  WORKING MEMORY VALIDATION FAILED  ⚠️
═══════════════════════════════════════════════════════════════════════════════

Working Memory should have been auto-created by session start.
If you see this message, the WM file exists but is missing required sections.

STEP 1: Read the existing WM file to check its contents
   → Read the file at .serena/memories/WM_{session_id}_*.md

STEP 2: Ensure these required sections exist:
   → '## Workflow Context' section header
   → '**Current State**:' field with valid WF_* state

STEP 3: If WM is corrupted, read REF_WM template and recreate:
   → mcp__plugin_swe_serena__read_memory("REF_WM")

If "No active project" error:
   → mcp__plugin_swe_serena__list_projects() to see available projects
   → mcp__plugin_swe_serena__activate_project("project_name") to activate

═══════════════════════════════════════════════════════════════════════════════
              FIX WORKING MEMORY BEFORE PROCEEDING
═══════════════════════════════════════════════════════════════════════════════"""
        }
        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        # On error, don't block (fail open for safety)
        print(json.dumps({"systemMessage": f"Init gate error: {e}"}))
        sys.exit(0)

if __name__ == '__main__':
    main()
