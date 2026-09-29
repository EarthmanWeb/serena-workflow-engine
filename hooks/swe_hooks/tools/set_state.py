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
from swe_hooks.core.state_manager import load_transition_matrix, is_valid_transition, load_subflows


def main():
    parser = argparse.ArgumentParser(description='Set workflow state for a session')
    parser.add_argument('session_id', help='Session ID (e.g., b1028d68)')
    parser.add_argument('target_state', help='Target state (e.g., WF_EXECUTE)')
    parser.add_argument('--force', action='store_true', help='Skip transition validation')
    args = parser.parse_args()

    # Subflows (WF_INIT, WF_CLEANUP, ...) are documented procedures, not FSM
    # states — set_state must never target one, force or not, since there is
    # no FSM node to land on. Checked first so this gets its own clear reason
    # rather than falling through to "Unknown state".
    subflows = load_subflows()
    if args.target_state in subflows:
        result = {
            'success': False,
            'error': (
                f'{args.target_state} is a subflow, not an FSM state — it is a documented '
                f'procedure entered by reading its memory, not by set_state.'
            ),
            'subflows': sorted(subflows),
        }
        print(json.dumps(result, indent=2))
        sys.exit(1)

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

    # clarify_entered_from: stamp the caller state on entry into WF_CLARIFY so
    # a later exit (in this or another process — every hook rebuilds state
    # from disk) can allow returning to it; clear it on exit from WF_CLARIFY.
    clarify_entered_from = "__unset__"
    if args.target_state == "WF_CLARIFY":
        clarify_entered_from = current_state
    elif current_state == "WF_CLARIFY":
        clarify_entered_from = None

    # Write state file
    if not write_state_file(args.session_id, args.target_state, prev_state=current_state,
                             clarify_entered_from=clarify_entered_from):
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
