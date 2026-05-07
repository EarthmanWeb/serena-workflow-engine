#!/usr/bin/env python3
"""SessionStart hook - Initialize WF_INIT workflow using WM.

State is stored in WM files (session-isolated), NOT in a global state file.
This allows multiple concurrent sessions without state conflicts.

Includes self-update workaround for Claude Code plugin auto-update bugs:
- anthropics/claude-code#29071: fetch without pull
- anthropics/claude-code#52218: installed_plugins.json not updated
"""

import os
import sys
import json
import subprocess
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.config import (
        load_setup_complete,
        get_most_recent_working_memory, get_working_memory_filename,
        read_working_memory_state, get_paths
    )
    from swe_hooks.core.state_manager import StateManager
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "SessionStart")


def _self_update():
    """Pull latest from remote if the marketplace clone is behind.

    Claude Code's autoUpdate fetches but never pulls (anthropics/claude-code#29071).
    This runs git pull in the marketplace clone so hooks/memories stay current.

    Returns: (updated: bool, old_version: str|None, new_version: str|None)
    """
    # Find the marketplace clone — walk up from this hook file
    # hooks/session/swe_session_start.py -> hooks/ -> plugin root
    plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    git_dir = os.path.join(plugin_root, '.git')

    # Only act on git-managed installs (marketplace clones), not submodules
    if not os.path.isdir(git_dir):
        return False, None, None

    # Don't update if this is a local dev checkout (has uncommitted changes)
    try:
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=plugin_root, capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip():
            return False, None, None  # Dirty tree — developer working locally
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, None, None

    # Read current version before update
    plugin_json = os.path.join(plugin_root, '.claude-plugin', 'plugin.json')
    old_version = None
    try:
        with open(plugin_json) as f:
            old_version = json.load(f).get('version')
    except (IOError, json.JSONDecodeError):
        pass

    # Fetch + check if behind
    try:
        subprocess.run(
            ['git', 'fetch', 'origin', '--quiet'],
            cwd=plugin_root, capture_output=True, timeout=10
        )
        result = subprocess.run(
            ['git', 'rev-list', 'HEAD..origin/main', '--count'],
            cwd=plugin_root, capture_output=True, text=True, timeout=5
        )
        behind = int(result.stdout.strip()) if result.stdout.strip() else 0
        if behind == 0:
            return False, old_version, old_version
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        return False, old_version, None

    # Pull (fast-forward only — safe, no merge conflicts possible)
    try:
        result = subprocess.run(
            ['git', 'pull', '--ff-only', 'origin', 'main'],
            cwd=plugin_root, capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return False, old_version, None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, old_version, None

    # Read new version
    new_version = None
    try:
        with open(plugin_json) as f:
            new_version = json.load(f).get('version')
    except (IOError, json.JSONDecodeError):
        pass

    return True, old_version, new_version





def main():
    try:
        # Self-update FIRST — before anything reads from the plugin tree
        updated, old_ver, new_ver = _self_update()

        # Read input
        input_data = {}
        try:
            input_data = json.load(sys.stdin)
        except:
            pass

        cwd = input_data.get('cwd', os.getcwd())
        
        # Extract unique session ID from transcript_path (contains UUID per conversation)
        # This ensures each chat gets its own isolated session
        transcript_path = input_data.get('transcript_path', '')
        if transcript_path:
            # Extract UUID from path like ~/.claude/projects/.../00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl
            import re
            uuid_match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', transcript_path)
            if uuid_match:
                session_id = uuid_match.group(1)[:8]  # Use first 8 chars for brevity
            else:
                session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        else:
            session_id = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Check bypass FIRST
        bypass_file = os.path.join(cwd, '.serena', 'swe-bypass.json')
        if os.path.exists(bypass_file):
            print(json.dumps({}))  # Silent — plugin disabled
            sys.exit(0)

        # Check setup
        setup = load_setup_complete(cwd)
        if not setup or not setup.get('complete'):
            if setup and setup.get('bootstrapped'):
                # Bootstrapped but needs full init
                context = "⚠️ SWE bootstrapped but not fully initialized. Run /swe-init or /swe-scaffold-project to complete."
            else:
                # Not set up — PROMPT (not block)
                context = """🔧 SWE Plugin Detected — Project Not Initialized

This project doesn't have SWE workflow configured.

**Option 1:** Set up SWE for this project:
   → Say "yes" or run /swe-init

**Option 2:** Permanently disable SWE for this project:
   → Say "skip swe" or "no swe"

The workflow will not block you while you decide."""
            # Return as additionalContext (NOT a hard block)
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context
                }
            }
            print(json.dumps(output))
            sys.exit(0)

        # DO NOT auto-create WM here - it should only be created during WF_START transition
        # This ensures the init_gate can block tools until WF_INIT is read
        # WM creation happens in WF_INIT workflow instructions

        # Read plugin version from plugin.json
        plugin_version = "unknown"
        plugin_root = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
        if plugin_root:
            plugin_json = os.path.join(plugin_root, '.claude-plugin', 'plugin.json')
        else:
            # Derive from this file's location: session/ -> hooks/ -> plugin root
            plugin_json = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                '.claude-plugin', 'plugin.json'
            )
        try:
            with open(plugin_json) as f:
                plugin_version = json.load(f).get('version', 'unknown')
        except (IOError, json.JSONDecodeError):
            pass

        update_line = ""
        if updated:
            update_line = f"\n🔄 Auto-updated: v{old_ver} → v{plugin_version}"

        context = f"""🚀 SERENA WORKFLOW ENGINE v{plugin_version} - Session {session_id}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{update_line}

⏳ Working Memory: Not yet created (will be created after WF_INIT)
Current State: WF_INIT

═══════════════════════════════════════════════════════════════════════════════
STEP 1: Read WF_INIT workflow instructions
   → mcp__plugin_swe_serena__read_memory(memory_name="wf/WF_INIT")

STEP 2: Follow WF_INIT to classify and execute user's task
═══════════════════════════════════════════════════════════════════════════════
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