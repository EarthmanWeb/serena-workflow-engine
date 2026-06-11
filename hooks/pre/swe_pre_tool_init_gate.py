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

# NOTE: Post-init, ALL tools are allowed (sentinel fast-path passes everything).
# Pre-init, only specific tools are allowed — see the PRE-INIT GATE section in main().
# This frozenset is NO LONGER used for gating. Kept for documentation only.
_FORMERLY_ALLOWED_TOOLS = frozenset([
    'ToolSearch', 'WebSearch', 'Read',
    'mcp__plugin_swe_serena__read_memory', 'mcp__serena__read_memory',
    'mcp__plugin_swe_serena__write_memory', 'mcp__serena__write_memory',
    'mcp__plugin_swe_serena__list_memories', 'mcp__serena__list_memories',
    'mcp__plugin_swe_serena__edit_memory', 'mcp__serena__edit_memory',
    'mcp__plugin_swe_serena__delete_memory', 'mcp__serena__delete_memory',
    'mcp__plugin_swe_serena__activate_project', 'mcp__serena__activate_project',
    'mcp__plugin_swe_serena__list_projects', 'mcp__serena__list_projects',
    'mcp__plugin_swe_serena__add_project', 'mcp__serena__add_project',
    'mcp__plugin_swe_serena__get_symbols_overview', 'mcp__serena__get_symbols_overview',
    'mcp__plugin_swe_serena__find_symbol', 'mcp__serena__find_symbol',
    'mcp__plugin_swe_serena__find_referencing_symbols', 'mcp__serena__find_referencing_symbols',
    'mcp__plugin_swe_serena__find_file', 'mcp__serena__find_file',
    'mcp__plugin_swe_serena__search_for_pattern', 'mcp__serena__search_for_pattern',
])

# Memory names allowed BEFORE initialization (WF_INIT workflow chain only)
# read_memory calls with any other memory_name will be BLOCKED pre-init
INIT_ALLOWED_MEMORIES = frozenset([
    'wf/WF_INIT',
    'wf/WF_START',
    'wf/WF_CLASSIFY',
    'wf/WF_RESEARCH',
    'wf/WF_RESEARCH_LITE',
    'claude/CLAUDE_OBLIGATIONS',
])

# Tools eligible for metadata injection (Serena MCP tools)
SERENA_TOOL_PREFIX = 'mcp__plugin_swe_serena__'
SERENA_TOOL_PREFIX_ALT = 'mcp__serena__'

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
    """Check if workflow state exists for THIS SESSION.

    Checks JSON state file first (fast), falls back to WM markdown.
    Returns: tuple (bool, str) - (is_valid, diagnostic_message)
    """
    try:
        project_root = get_project_root() if _STREAM_AVAILABLE else _get_project_root()
    except Exception:
        project_root = _get_project_root()

    # Primary: check JSON state file (fast, no markdown parsing)
    if session_id:
        state_dir = os.path.join(project_root, '.serena', 'swe-state')
        state_file = os.path.join(state_dir, f'{session_id}.state')
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    content = f.read().strip()
                if content:
                    # JSON format or legacy text — either means session was initialized
                    return True, "Valid (state file)"
            except IOError:
                pass

    # Fallback: check WM markdown file
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
        return False, f"No state file or WM_{session_id}.md found"

    # WM file exists — check it has basic structure
    latest = max(working_memories, key=os.path.getmtime)
    filename = os.path.basename(latest)

    try:
        with open(latest, 'r') as f:
            content = f.read()
        if '## Workflow Context' in content or '**Current State**:' in content:
            return True, "Valid (WM file)"
        if session_id and session_id in filename:
            return True, "Valid (WM filename match)"
        return False, f"File {filename} missing workflow context"
    except Exception as e:
        return False, f"Error reading {filename}: {e}"


def inject_metadata(tool_name, tool_input, session_id, cwd):
    """Inject _swe_metadata into Serena tool calls for session correlation.

    Inspired by IronBee's require-verification input rewriting pattern.
    Enables server-side correlation of tool calls to workflow sessions.
    """
    if not (tool_name.startswith(SERENA_TOOL_PREFIX) or
            tool_name.startswith(SERENA_TOOL_PREFIX_ALT)):
        return None  # Not a Serena tool — no injection

    # Read current workflow state from decoupled state file
    current_state = ''
    feature_keys = ''
    try:
        state_dir = os.path.join(cwd, '.serena', 'swe-state')
        state_file = os.path.join(state_dir, f'{session_id}.state')
        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                state_data = json.load(f)
            current_state = state_data.get('current_state', '')
            feature_keys = state_data.get('feature_keys', '')
    except (IOError, json.JSONDecodeError):
        pass

    metadata = {
        'session_id': session_id,
        'state': current_state,
        'feature_keys': feature_keys,
    }

    updated_input = dict(tool_input)
    updated_input['_swe_metadata'] = metadata
    return updated_input


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0) if _STREAM_AVAILABLE else json.load(sys.stdin)
        tool_name = input_data.get('tool_name', '')
        transcript_path = input_data.get('transcript_path', '')
        tool_input = input_data.get('tool_input', {})

        # Resolve project root for setup checks
        try:
            project_root = get_project_root() if _STREAM_AVAILABLE else _get_project_root()
        except Exception:
            project_root = _get_project_root()

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

        # Allow Write to WORKING_MEMORY files (always, pre- and post-init)
        if is_working_memory_write(tool_name, tool_input):
            print(json.dumps({}))
            sys.exit(0)

        # FAST PATH: Sentinel file check (~0.5ms) — session already initialized
        session_initialized = False
        if session_id and _STREAM_AVAILABLE:
            sentinel = get_sentinel_path(session_id)
            if os.path.exists(sentinel):
                session_initialized = True
                # Post-init: ALL tools pass (sentinel = WM validated this session)
                if tool_name not in SKIP_STREAM_TOOLS:
                    stream_path = get_stream_path(session_id)
                    append_event(stream_path, 'tool', name=tool_name, s=session_id)

                # Inject metadata into Serena tool calls for session correlation
                cwd = input_data.get('cwd', os.getcwd())
                updated_input = inject_metadata(tool_name, tool_input, session_id, cwd)
                if updated_input is not None:
                    result = {
                        'hookSpecificOutput': {
                            'hookEventName': 'PreToolUse',
                            'permissionDecision': 'allow',
                            'updatedInput': updated_input
                        }
                    }
                    print(json.dumps(result))
                    sys.exit(0)

                print(json.dumps({}))
                sys.exit(0)

        # Self-healing sentinel recovery: if sentinel missing but WM valid,
        # recreate sentinel. Fixes deadlock on mid-session task pivots where
        # the daemon blocks re-running the init chain but the gate demands it.
        if not session_initialized and session_id and _STREAM_AVAILABLE:
            is_valid, _ = check_working_memory_exists(session_id)
            if is_valid:
                sentinel = get_sentinel_path(session_id)
                try:
                    os.makedirs(os.path.dirname(sentinel), exist_ok=True)
                    sentinel_data = {
                        "session_id": session_id,
                        "wm_file": f"WM_{session_id}",
                        "validated_at": int(__import__('time').time()),
                    }
                    with open(sentinel, 'w') as f:
                        json.dump(sentinel_data, f, separators=(',', ':'))
                    session_initialized = True
                except IOError:
                    pass

        # Fallback: if stream unavailable, check WM directly for init status
        if not session_initialized and not _STREAM_AVAILABLE:
            is_valid, _ = check_working_memory_exists(session_id)
            if is_valid:
                session_initialized = True

        # ═══ PRE-INIT GATE: Block task-work tools before initialization ═══
        # If session is NOT initialized, only allow the init workflow chain
        if not session_initialized:
            # ToolSearch is always allowed (needed to fetch tool schemas)
            if tool_name == 'ToolSearch':
                print(json.dumps({}))
                sys.exit(0)

            # read_memory: only allow init-chain memories
            if tool_name in ('mcp__plugin_swe_serena__read_memory', 'mcp__serena__read_memory'):
                memory_name = tool_input.get('memory_name', '')
                if memory_name in INIT_ALLOWED_MEMORIES or memory_name.startswith('wf/'):
                    print(json.dumps({}))
                    sys.exit(0)
                else:
                    output = {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": f"""🛑 BLOCKED: read_memory("{memory_name}") called before WF_INIT complete.

Pre-init, only these memories are allowed: {', '.join(sorted(INIT_ALLOWED_MEMORIES))}

Your FIRST read_memory call MUST be: read_memory("wf/WF_INIT")
Then follow the init chain: WF_INIT → CLAUDE_OBLIGATIONS → WF_START → WF_CLASSIFY

DO NOT read task-specific memories before initialization is complete."""
                        }
                    }
                    print(json.dumps(output))
                    sys.exit(0)

            # write_memory / edit_memory / list_memories: allow (needed for WM creation and feature loading during init)
            if tool_name in (
                'mcp__plugin_swe_serena__write_memory', 'mcp__serena__write_memory',
                'mcp__plugin_swe_serena__edit_memory', 'mcp__serena__edit_memory',
                'mcp__plugin_swe_serena__list_memories', 'mcp__serena__list_memories',
            ):
                print(json.dumps({}))
                sys.exit(0)

            # swe-wm MCP tools: allow (needed for WM updates during init chain)
            if tool_name in (
                'mcp__plugin_swe_swe-wm__swe_wm_read',
                'mcp__plugin_swe_swe-wm__swe_wm_update_section',
                'mcp__plugin_swe_swe-wm__swe_wm_update_status',
                'mcp__plugin_swe_swe-wm__swe_wm_list',
            ):
                print(json.dumps({}))
                sys.exit(0)

            # activate_project / list_projects / add_project: allow (needed for Serena setup)
            if tool_name in (
                'mcp__plugin_swe_serena__activate_project', 'mcp__serena__activate_project',
                'mcp__plugin_swe_serena__list_projects', 'mcp__serena__list_projects',
                'mcp__plugin_swe_serena__add_project', 'mcp__serena__add_project',
                'mcp__plugin_swe_serena__initial_instructions', 'mcp__serena__initial_instructions',
                'mcp__plugin_swe_serena__check_onboarding_performed', 'mcp__serena__check_onboarding_performed',
                'mcp__plugin_swe_serena__onboarding', 'mcp__serena__onboarding',
            ):
                print(json.dumps({}))
                sys.exit(0)

            # BLANKET DENY: Everything not explicitly allowed above is blocked pre-init
            # This catches Bash, Grep, Glob, Edit, Write (non-WM),
            # find_symbol, get_symbols_overview, and ANY other tool
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"""🛑 BLOCKED: {tool_name} called before WF_INIT complete.

This tool is NOT allowed before initialization.
Only read_memory and list_memories (init-chain) are permitted.

MANDATORY ACTION — Complete the full init chain:
   1. mcp__plugin_swe_serena__read_memory(memory_name="wf/WF_INIT")
   2. mcp__plugin_swe_serena__read_memory(memory_name="claude/CLAUDE_OBLIGATIONS")
   3. mcp__plugin_swe_serena__read_memory(memory_name="wf/WF_START")

The sentinel that unlocks all tools is created when WF_START is read.
Do NOT use {tool_name} until the full chain is complete."""
                }
            }
            print(json.dumps(output))
            sys.exit(0)

        # Check lite mode
        if check_lite_mode(session_id):
            print(json.dumps({"systemMessage": "🔎 LITE_MODE active - minimal workflow"}))
            sys.exit(0)

        # Full validation (only runs once per session until sentinel created)
        is_valid, diagnostic = check_working_memory_exists(session_id)
        if is_valid:
            # Create sentinel with WM info for future fast-path
            if session_id and _STREAM_AVAILABLE:
                sentinel = get_sentinel_path(session_id)
                try:
                    os.makedirs(os.path.dirname(sentinel), exist_ok=True)
                    # Sentinel stores the validated WM filename — source of truth
                    sentinel_data = {
                        "session_id": session_id,
                        "wm_file": f"WM_{session_id}",
                        "validated_at": int(__import__('time').time()),
                    }
                    with open(sentinel, 'w') as f:
                        json.dump(sentinel_data, f, separators=(',', ':'))
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

MANDATORY ACTION — Complete the full init chain:
   1. mcp__plugin_swe_serena__read_memory(memory_name="wf/WF_INIT")
   2. mcp__plugin_swe_serena__read_memory(memory_name="claude/CLAUDE_OBLIGATIONS")
   3. mcp__plugin_swe_serena__read_memory(memory_name="wf/WF_START")

The sentinel that unlocks all tools is created when WF_START is read.
Do NOT stop after reading WF_INIT — you must complete all 3 steps.

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

def reset_sentinel(session_id=None):
    """Manual escape hatch: reset init sentinel for a session.

    Usage:
        python3 swe_pre_tool_init_gate.py --reset-sentinel [session_id]

    If session_id is omitted, resets ALL sentinels in the streams directory.
    Creates a fresh sentinel if a valid WM exists for the session.
    """
    import time as _time

    try:
        project_root = get_project_root() if _STREAM_AVAILABLE else _get_project_root()
    except Exception:
        project_root = _get_project_root()

    stream_dir = os.path.join(project_root, '.serena', 'streams')
    if not os.path.isdir(stream_dir):
        print(f"No streams directory at {stream_dir}")
        return

    # Delete existing sentinel(s)
    if session_id:
        targets = [os.path.join(stream_dir, f'.init_{session_id}')]
    else:
        targets = glob.glob(os.path.join(stream_dir, '.init_*'))

    for sentinel_path in targets:
        if os.path.exists(sentinel_path):
            os.remove(sentinel_path)
            print(f"Deleted: {os.path.basename(sentinel_path)}")

    # Recreate sentinel if WM is valid for the specified session
    if session_id:
        is_valid, diag = check_working_memory_exists(session_id)
        if is_valid:
            sentinel = os.path.join(stream_dir, f'.init_{session_id}')
            sentinel_data = {
                "session_id": session_id,
                "wm_file": f"WM_{session_id}",
                "validated_at": int(_time.time()),
            }
            with open(sentinel, 'w') as f:
                json.dump(sentinel_data, f, separators=(',', ':'))
            print(f"Created: .init_{session_id} (WM valid)")
        else:
            print(f"No valid WM for session {session_id}: {diag}")
            print("Sentinel deleted but not recreated — next init chain will create it.")
    else:
        print("All sentinels cleared. Next init chain will recreate them.")


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--reset-sentinel':
        sid = sys.argv[2] if len(sys.argv) > 2 else None
        reset_sentinel(sid)
    else:
        main()
