#!/usr/bin/env python3
"""PostToolUse for Bash - pass through."""

import os
import sys
import json

PLUGIN_ROOT = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
if PLUGIN_ROOT:
    hooks_dir = os.path.join(PLUGIN_ROOT, 'hooks')
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)

try:
    from swe_hooks.core.output import output_empty
    from swe_hooks.core.input import read_stdin_safe
except ImportError as e:
    output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"SWE import error: {e}"}}
    print(json.dumps(output), file=sys.stdout)
    sys.exit(0)

def main():
    try:
        read_stdin_safe(timeout_seconds=2.0)
        output_empty()
    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"Post-bash error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)

if __name__ == '__main__':
    main()
