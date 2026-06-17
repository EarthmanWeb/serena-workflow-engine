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
import shutil
import subprocess
import time
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.config import (
        load_setup_complete, resolve_setup_state, BYPASS_NOTICE,
        get_most_recent_working_memory, get_working_memory_filename,
        read_working_memory_state, get_paths
    )
    from swe_hooks.core.state_manager import StateManager
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "SessionStart")


def _self_update():
    """Pull latest and install as new cache entry if version changed.

    For git-managed installs (dev checkouts): git pull in place.
    For marketplace cache installs: pull marketplace clone, create new versioned
    cache directory, orphan old cache, update installed_plugins.json.

    Returns: (updated: bool, old_version: str|None, new_version: str|None)
    """
    plugin_root = os.path.normpath(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )

    # Git-managed install (dev checkout) — pull in place
    if os.path.isdir(os.path.join(plugin_root, '.git')):
        return _self_update_git(plugin_root)

    # Marketplace cache install — replicate Claude Code's install mechanism
    return _self_update_marketplace(plugin_root)


def _self_update_git(plugin_root):
    """Git pull in place for dev checkouts with a .git directory."""
    # Don't update if this is a local dev checkout with uncommitted changes
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

    # Pull (fast-forward only)
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


def _self_update_marketplace(plugin_root):
    """Update marketplace cache install by pulling the marketplace clone and
    creating a new versioned cache directory — replicating Claude Code's
    install mechanism.

    Cache path structure: ~/.claude/plugins/cache/{marketplace}/{plugin}/{version}/
    Marketplace clone:    ~/.claude/plugins/marketplaces/{marketplace}/
    """
    # Derive paths from cache directory structure
    version_dir = plugin_root  # .../cache/Marketplace/plugin/1.1.30
    plugin_dir = os.path.dirname(version_dir)  # .../cache/Marketplace/plugin
    marketplace_dir = os.path.dirname(plugin_dir)  # .../cache/Marketplace
    cache_dir = os.path.dirname(marketplace_dir)  # .../cache

    # Validate we're actually in a cache directory
    if os.path.basename(cache_dir) != 'cache':
        return False, None, None

    marketplace_name = os.path.basename(marketplace_dir)
    plugin_name = os.path.basename(plugin_dir)
    plugins_dir = os.path.dirname(cache_dir)  # ~/.claude/plugins

    # Find the marketplace clone (git repo that Claude Code maintains)
    marketplace_clone = os.path.join(plugins_dir, 'marketplaces', marketplace_name)
    if not os.path.isdir(os.path.join(marketplace_clone, '.git')):
        return False, None, None

    # Read current version from cache
    plugin_json_path = os.path.join(plugin_root, '.claude-plugin', 'plugin.json')
    old_version = None
    try:
        with open(plugin_json_path) as f:
            old_version = json.load(f).get('version')
    except (IOError, json.JSONDecodeError):
        pass

    # Pull marketplace clone (same as Claude Code's auto-update)
    try:
        result = subprocess.run(
            ['git', 'pull', '--ff-only', 'origin', 'main'],
            cwd=marketplace_clone, capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return False, old_version, None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, old_version, None

    # Read new version from pulled marketplace clone
    marketplace_plugin_json = os.path.join(
        marketplace_clone, '.claude-plugin', 'plugin.json'
    )
    new_version = None
    try:
        with open(marketplace_plugin_json) as f:
            new_version = json.load(f).get('version')
    except (IOError, json.JSONDecodeError):
        return False, old_version, None

    # No update needed
    if not new_version or new_version == old_version:
        return False, old_version, old_version

    # Create new versioned cache directory
    new_cache_dir = os.path.join(plugin_dir, new_version)
    if os.path.exists(new_cache_dir):
        return False, old_version, new_version  # Already exists

    try:
        shutil.copytree(
            marketplace_clone, new_cache_dir,
            ignore=shutil.ignore_patterns('.git'),
            symlinks=True
        )
    except (OSError, shutil.Error):
        # Clean up partial copy
        if os.path.exists(new_cache_dir):
            shutil.rmtree(new_cache_dir, ignore_errors=True)
        return False, old_version, None

    # Get git commit SHA from marketplace clone
    git_sha = None
    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=marketplace_clone, capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            git_sha = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Orphan old cache directory (Claude Code cleans up after 7 days)
    try:
        with open(os.path.join(plugin_root, '.orphaned_at'), 'w') as f:
            f.write(str(int(time.time() * 1000)))
    except IOError:
        pass

    # Update installed_plugins.json — point all matching entries to new cache
    installed_json = os.path.join(plugins_dir, 'installed_plugins.json')
    try:
        with open(installed_json) as f:
            registry = json.load(f)

        plugin_key = f"{plugin_name}@{marketplace_name}"
        now_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.') + \
            f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"

        for entry in registry.get('plugins', {}).get(plugin_key, []):
            if os.path.normpath(entry.get('installPath', '')) == plugin_root:
                entry['installPath'] = new_cache_dir
                entry['version'] = new_version
                entry['lastUpdated'] = now_iso
                if git_sha:
                    entry['gitCommitSha'] = git_sha

        with open(installed_json, 'w') as f:
            json.dump(registry, f, indent=2)
            f.write('\n')
    except (IOError, json.JSONDecodeError, KeyError):
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

        # Check bypass FIRST. Bypass lives as "bypass": true inside
        # swe-setup-complete.json (the same file used for init). When set, SWE
        # is disabled for the project — but we ANNOUNCE it (with removal
        # instructions) rather than exiting silently, so it's never forgotten.
        # NOTE: the bypass is only ever written by the user via /swe-bypass —
        # never by the assistant.
        try:
            _setup_state = resolve_setup_state(cwd)
        except Exception:
            _setup_state = {}
        legacy_bypass_file = os.path.join(cwd, '.serena', 'swe-bypass.json')
        if _setup_state.get('bypassed') or os.path.exists(legacy_bypass_file):
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": BYPASS_NOTICE,
                }
            }
            print(json.dumps(output))
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

**Option 2:** Disable SWE for this project:
   → Run the /swe-bypass command yourself (user-only; the assistant cannot do this for you)

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
            plugin_version = new_ver or plugin_version
            update_line = f"\n🔄 Auto-updated: v{old_ver} → v{new_ver}"

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