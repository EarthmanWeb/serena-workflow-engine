#!/usr/bin/env python3
"""CLI tool for /swe-edit-mode.

Usage:
    python3 edit_mode.py <session_id> <on|off|status|toggle>

Sets, clears, or reports the session's edit-mode sentinel
(.serena/streams/.edit_mode_{session_id}). Returns JSON status.
"""

import argparse
import json
import os
import sys

# Add hooks dir to path so we can import core modules
script_dir = os.path.dirname(os.path.abspath(__file__))
hooks_dir = os.path.dirname(os.path.dirname(script_dir))
if hooks_dir not in sys.path:
    sys.path.insert(0, hooks_dir)

from swe_hooks.core.stream import is_edit_mode, set_edit_mode


def main():
    parser = argparse.ArgumentParser(description='Get/set edit-mode flag for a session')
    parser.add_argument('session_id', help='Session ID (e.g., b1028d68)')
    parser.add_argument('action', choices=['on', 'off', 'status', 'toggle'],
                        help='on: turn ON; off: turn OFF; status: report only; '
                             'toggle: flip current state')
    args = parser.parse_args()

    before = is_edit_mode(args.session_id)

    if args.action == 'status':
        result = {"success": True, "session_id": args.session_id, "edit_mode": before}
        print(json.dumps(result, indent=2))
        return

    if args.action == 'on':
        target = True
    elif args.action == 'off':
        target = False
    else:  # toggle
        target = not before

    ok = set_edit_mode(args.session_id, target)
    result = {
        "success": ok,
        "session_id": args.session_id,
        "edit_mode": target if ok else before,
        "previous": before,
    }
    if not ok:
        result["error"] = "failed to write/remove edit-mode sentinel"
        print(json.dumps(result, indent=2))
        sys.exit(1)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
