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

from swe_hooks.core.config import (
    read_state_file, write_state_file,
    get_most_recent_working_memory, write_working_memory_state
)
from swe_hooks.core.state_manager import load_transition_matrix, is_valid_transition


def main():
    parser = argparse.ArgumentParser(description='Set workflow state for a session')
    parser.add_argument('session_id', help='Session ID (e.g., b1028d68)')
    parser.add_argument('target_state', help='Target state (e.g., WF_EXECUTE)')
    parser.add_argument('--force', action='store_true', help='Skip transition validation')
    args = parser.parse_args()

    # Validate target state exists in states.json
    matrix = load_transition_matrix()
    all_states = set(matrix.keys())
    for targets in matrix.values():
        for t in targets:
            if t:
                all_states.add(t)

    if args.target_state not in all_states:
        result = {
            'success': False,
            'error': f'Unknown state: {args.target_state}',
            'valid_states': sorted(all_states)
        }
        print(json.dumps(result, indent=2))
        sys.exit(1)

    # Check current state
    current = read_state_file(args.session_id)
    current_state = current.get('current_state', 'UNKNOWN') if current else 'UNKNOWN'

    # Validate transition unless forced
    if not args.force:
        is_valid, error_msg = is_valid_transition(current_state, args.target_state)
        if not is_valid:
            result = {
                'success': False,
                'error': error_msg,
                'current_state': current_state,
                'target_state': args.target_state,
                'hint': 'Use --force to override'
            }
            print(json.dumps(result, indent=2))
            sys.exit(1)

    # Write state file
    if not write_state_file(args.session_id, args.target_state, prev_state=current_state):
        result = {'success': False, 'error': 'Failed to write state file'}
        print(json.dumps(result, indent=2))
        sys.exit(1)

    # Best-effort WM update
    cwd = os.environ.get('CLAUDE_PROJECT_DIR', os.getcwd())
    wm_path = get_most_recent_working_memory(cwd)
    wm_updated = False
    if wm_path:
        wm_updated = write_working_memory_state(cwd, wm_path, args.target_state)

    result = {
        'success': True,
        'session_id': args.session_id,
        'previous_state': current_state,
        'new_state': args.target_state,
        'state_file': True,
        'wm_updated': wm_updated,
        'forced': args.force
    }
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
