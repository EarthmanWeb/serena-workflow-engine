#!/usr/bin/env python3
"""CLI tool for /swe-goto and recovery.

Usage:
    python3 set_state.py <session_id> <target_state> [--force]

Validates target exists in states.json and validates transition
unless --force is specified. Writes state file + best-effort WM update.
Returns JSON status.
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

from swe_hooks.core.config import read_state_file
from swe_hooks.core.state_manager import perform_transition


def main():
    parser = argparse.ArgumentParser(description='Set workflow state for a session')
    parser.add_argument('session_id', help='Session ID (e.g., b1028d68)')
    parser.add_argument('target_state', help='Target state (e.g., WF_EXECUTE)')
    parser.add_argument('--force', action='store_true', help='Skip transition validation')
    args = parser.parse_args()

    cwd = os.environ.get('CLAUDE_PROJECT_DIR', os.getcwd())

    # current_state (pre-transition) is only needed for the loop-guard
    # advisory below — perform_transition resolves the authoritative
    # previous_state itself via StateManager.
    current = read_state_file(args.session_id)
    current_state = current.get('current_state', 'UNKNOWN') if current else 'UNKNOWN'

    result = perform_transition(cwd, args.session_id, args.target_state, force=args.force)

    if not result.get('success'):
        print(json.dumps(result, indent=2))
        sys.exit(1)

    # Best-effort loop-guard advisory — set_state is itself the escape hatch
    # for a capped/oscillating loop, so this never blocks here, only informs.
    try:
        from swe_hooks.core import loop_guard
        from swe_hooks.core.state_manager import load_loop_caps
        from swe_hooks.core.stream import get_stream_path
        stream_path = get_stream_path(args.session_id)
        events = []
        if os.path.exists(stream_path):
            with open(stream_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except (json.JSONDecodeError, ValueError):
                            pass
        caps = load_loop_caps()
        if events and caps:
            ok, count, cap, message = loop_guard.check_loop_cap(events, current_state, args.target_state, caps)
            if not ok:
                result['loop_guard'] = message
            osc = loop_guard.detect_oscillation(
                events + [{"type": "state", "from_s": current_state, "to_s": args.target_state}]
            )
            if osc:
                result['oscillation_warning'] = osc
    except Exception:
        pass

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
