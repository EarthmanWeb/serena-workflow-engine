#!/usr/bin/env python3
"""PreToolUse gate - BLOCKS all tools until workflow is initialized.

Requires WORKING_MEMORY file with proper workflow state.
Uses sentinel file cache to avoid re-validation on every tool call.

Session isolation: Each conversation must have its own working memory.
"""

import os
import sys
import json
import glob
import re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.session import extract_session_id
    from swe_hooks.core.config import get_project_root
    from swe_hooks.core.stream import get_sentinel_path, get_stream_path, append_event
    from swe_hooks.core.input import read_stdin_safe
    _STREAM_AVAILABLE = True
except ImportError:
    _STREAM_AVAILABLE = False

# Tools ALWAYS ALLOWED before initialization (O(1) exact match)
ALLOWED_TOOLS = frozenset([
    'ToolSearch',
    'WebSearch',
    'Read',
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
    'mcp__plugin_swe_serena__activate_project',
    'mcp__serena__activate_project',
    'mcp__plugin_swe_serena__list_projects',
    'mcp__serena__list_projects',
    'mcp__plugin_swe_serena__add_project',
    'mcp__serena__add_project',
    'mcp__plugin_swe_serena__get_symbols_overview',
    'mcp__serena__get_symbols_overview',
    'mcp__plugin_swe_serena__find_symbol',
    'mcp__serena__find_symbol',
    'mcp__plugin_swe_serena__find_referencing_symbols',
    'mcp__serena__find_referencing_symbols',
    'mcp__plugin_swe_serena__find_file',
    'mcp__serena__find_file',
    'mcp__plugin_swe_serena__search_for_pattern',
    'mcp__serena__search_for_pattern',
])

# Tools to skip in stream logging (too noisy, low value)
SKIP_STREAM_TOOLS = frozenset([
    'ToolSearch', 'TaskList', 'TaskGet', 'TaskUpdate', 'TaskCreate',
    'TaskOutput', 'TaskStop', 'AskUserQuestion', 'ExitPlanMode',
    'EnterPlanMode', 'SendMessage', 'TeamCreate', 'TeamDelete',
])


def _get_project_root():
    """Fallback project root if core module unavailable.

    Uses .git/ not .serena/ — the plugin creates .serena/ itself, so it
    can't be used as a root marker on first run or in subdirectory cwd.
    """
    project_dir = os.environ.get('CLAUDE_PROJECT_DIR', '')
    if project_dir and os.path.isdir(os.path.join(project_dir, '.git')):
        return project_dir
    current = os.getcwd()
    while current != os.path.dirname(current):
        if os.path.isdir(os.path.join(current, '.git')):
            return current
        current = os.path.dirname(current)
    return os.getcwd()


def _extract_session_id(transcript_path):
    """Fallback session ID extraction if core module unavailable."""
    if not transcript_path:
        return None
    uuid_match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', transcript_path)
    if uuid_match:
        return uuid_match.group(1)[:8]
    return None


def is_working_memory_write(tool_name, tool_input):
    """Check if this is a Write to WORKING_MEMORY file."""
    if tool_name != 'Write':
        return False
    file_path = tool_input.get('file_path', '')
    return '.serena/memories/WM_' in file_path and file_path.endswith('.md')


def check_lite_mode(session_id):
    """Check if lite mode is active for this session."""
    if not session_id:
        return False
    try:
        project_root = get_project_root() if _STREAM_AVAILABLE else _get_project_root()
    except Exception:
        project_root = _get_project_root()
    memories_dir = os.path.join(project_root, '.serena', 'memories')
    return os.path.exists(os.path.join(memories_dir, f'LITE_MODE_{session_id}.md'))


def check_working_memory_exists(session_id):
    """Check if a WORKING_MEMORY file exists for THIS SESSION.

    Returns: tuple (bool, str) - (is_valid, diagnostic_message)
    """
    try:
        project_root = get_project_root() if _STREAM_AVAILABLE else _get_project_root()
    except Exception:
        project_root = _get_project_root()
    memories_dir = os.path.join(project_root, '.serena', 'memories')
    if not os.path.exists(memories_dir):
        return False, "No .serena/memories directory found"

    if session_id:
        pattern = os.path.join(memories_dir, f'WM_{session_id}.md')
        working_memories = glob.glob(pattern)
    else:
        pattern = os.path.join(memories_dir, 'WM_*.md')
        working_memories = glob.glob(pattern)

    if not working_memories:
        return False, f"No WM_{session_id}.md file found"

    latest = max(working_memories, key=os.path.getmtime)
    filename = os.path.basename(latest)

    try:
        with open(latest, 'r') as f:
            content = f.read()

        required_patterns = [
            ('## Workflow Context', 'Section header'),
            ('**Current State**:', 'Current State field'),
        ]

        missing = []
        for pattern_str, desc in required_patterns:
            if pattern_str not in content:
                missing.append(f"'{pattern_str}' ({desc})")

        if missing:
            found_patterns = []
            alt_patterns = [
                ('## Workflow State', 'Wrong section header'),
                ('**Current**:', 'Wrong field format'),
                ('Current State:', 'Missing bold markers'),
            ]
            for alt_pat, alt_desc in alt_patterns:
                if alt_pat in content:
                    found_patterns.append(f"'{alt_pat}' ({alt_desc})")

            diag = f"File {filename} missing: {', '.join(missing)}"
            if found_patterns:
                diag += f". Found instead: {', '.join(found_patterns)}"
            return False, diag

        if session_id:
            session_match = re.search(r'\*\*Session ID\*\*:\s*(\S+)', content)
            if session_match and session_match.group(1) == session_id:
                return True, "Valid"
            if session_id in filename:
                return True, "Valid"
            return False, f"Session ID mismatch: expected {session_id}"
        return True, "Valid"
    except Exception as e:
        return False, f"Error reading {filename}: {e}"


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0) if _STREAM_AVAILABLE else json.load(sys.stdin)
        tool_name = input_data.get('tool_name', '')
        transcript_path = input_data.get('transcript_path', '')
        tool_input = input_data.get('tool_input', {})

        # Resolve project root for bypass/setup checks
        try:
            project_root = get_project_root() if _STREAM_AVAILABLE else _get_project_root()
        except Exception:
            project_root = _get_project_root()

        # Bypass check — plugin disabled for this project
        bypass_file = os.path.join(project_root, '.serena', 'swe-bypass.json')
        if os.path.exists(bypass_file):
            print(json.dumps({}))
            sys.exit(0)

        # If setup not complete, don't enforce init gate
        # This allows /swe-init and bootstrap to run freely
        setup_file = os.path.join(project_root, '.serena', 'swe-setup-complete.json')
        if not os.path.exists(setup_file):
            print(json.dumps({}))  # No setup at all — don't block
            sys.exit(0)
        try:
            with open(setup_file) as f:
                setup_data = json.load(f)
            if not setup_data.get('complete'):
                print(json.dumps({}))  # Bootstrapped but not complete — don't block
                sys.exit(0)
        except (json.JSONDecodeError, IOError):
            print(json.dumps({}))  # Corrupt — don't block
            sys.exit(0)

        # Extract session ID
        try:
            session_id = extract_session_id(transcript_path) if _STREAM_AVAILABLE else _extract_session_id(transcript_path)
        except Exception:
            session_id = _extract_session_id(transcript_path)

        # FAST PATH 1: Allowed tools bypass (O(1) frozenset lookup)
        if tool_name in ALLOWED_TOOLS:
            print(json.dumps({}))
            sys.exit(0)

        # Allow Write to WORKING_MEMORY files
        if is_working_memory_write(tool_name, tool_input):
            print(json.dumps({}))
            sys.exit(0)

        # FAST PATH 2: Sentinel file check (~0.5ms)
        if session_id and _STREAM_AVAILABLE:
            sentinel = get_sentinel_path(session_id)
            if os.path.exists(sentinel):
                # Already validated - append tool event to stream and allow
                if tool_name not in SKIP_STREAM_TOOLS:
                    stream_path = get_stream_path(session_id)
                    append_event(stream_path, 'tool', name=tool_name, s=session_id)
                print(json.dumps({}))
                sys.exit(0)

        # Check lite mode
        if check_lite_mode(session_id):
            print(json.dumps({"systemMessage": "🔎 LITE_MODE active - minimal workflow"}))
            sys.exit(0)

        # Full validation (only runs once per session until sentinel created)
        is_valid, diagnostic = check_working_memory_exists(session_id)
        if is_valid:
            # Create sentinel for future fast-path
            if session_id and _STREAM_AVAILABLE:
                sentinel = get_sentinel_path(session_id)
                try:
                    os.makedirs(os.path.dirname(sentinel), exist_ok=True)
                    open(sentinel, 'w').close()
                except IOError:
                    pass

                # Append tool event to stream
                if tool_name not in SKIP_STREAM_TOOLS:
                    stream_path = get_stream_path(session_id)
                    append_event(stream_path, 'tool', name=tool_name, s=session_id)

            print(json.dumps({}))
            sys.exit(0)

        # BLOCK - not initialized
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"""🛑 BLOCKED: No Working Memory for session {session_id or 'unknown'}

═══════════════════════════════════════════════════════════════════════════════
                         ⚠️  WORKFLOW NOT INITIALIZED  ⚠️
═══════════════════════════════════════════════════════════════════════════════

You must complete the WF_INIT workflow before using other tools.

⛔ NO EXCEPTIONS MEANS NO EXCEPTIONS:
- "But the user wants a quick answer" → NO. Initialize first.
- "But this is meta-work on the workflow itself" → NO. Initialize first.
- "But I already know what to do" → NO. Initialize first.
- "But it's just a simple edit" → NO. Initialize first.
DO NOT RATIONALIZE. DO NOT NEGOTIATE. INITIALIZE.

MANDATORY ACTION - Call this tool NOW:
   → mcp__plugin_swe_serena__read_memory(memory_name="wf/WF_INIT")

Then follow WF_INIT instructions to:
1. Read WF_START (which creates the Working Memory)
2. Proceed with task classification

Diagnostic: {diagnostic}

═══════════════════════════════════════════════════════════════════════════════
              COMPLETE WF_INIT BEFORE PROCEEDING
═══════════════════════════════════════════════════════════════════════════════"""
            }
        }
        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        print(json.dumps({"systemMessage": f"Init gate error: {e}"}))
        sys.exit(0)

if __name__ == '__main__':
    main()
