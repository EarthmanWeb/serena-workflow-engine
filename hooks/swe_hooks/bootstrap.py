"""Bootstrap module for SWE hooks.
Import this module FIRST in any hook script to set up sys.path.
Path setup runs at module import time (replaces 5-line boilerplate in every hook).
"""
import os, sys, json

# Setup sys.path at import time
PLUGIN_ROOT = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
if PLUGIN_ROOT:
    hooks_dir = os.path.join(PLUGIN_ROOT, 'hooks')
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)


def import_error_exit(error, event_name="PostToolUse"):
    """Exit with import error message. Call in except ImportError blocks."""
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": event_name,
        "additionalContext": f"SWE import error: {error}"
    }}), file=sys.stdout)
    sys.exit(0)
