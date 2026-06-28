#!/usr/bin/env python3
"""SWE Bypass - Enable the project-level workflow bypass.

Sets "bypass": true inside .serena/swe-setup-complete.json (the same file used
for initialization — no separate bypass file). If the file does not exist yet,
it is created as {"complete": false, "bypass": true}.

USER-ONLY ACTION. This script is the single, auditable write path for the
bypass. It exists ONLY to back the /swe-bypass command (disable-model-invocation:
true). The PreToolUse guards block every OTHER way of writing "bypass": true into
the setup file (Edit/Write/write_memory/ad-hoc Bash), so the assistant cannot
set the bypass incidentally or by inferring intent — only this explicit,
named invocation does it, which is equivalent to the user editing the file by
hand (already permitted).

Operates on the project root (CLAUDE_PROJECT_DIR or nearest .git ancestor).
Outputs a confirmation line. Always exits 0.
"""

import os
import sys
import json

SETUP_REL = os.path.join('.serena', 'swe-setup-complete.json')


def resolve_project_root():
    """Project root: CLAUDE_PROJECT_DIR if it has .git, else nearest .git ancestor."""
    project_dir = os.environ.get('CLAUDE_PROJECT_DIR', '')
    if project_dir and os.path.isdir(os.path.join(project_dir, '.git')):
        return project_dir
    current = os.getcwd()
    while current != os.path.dirname(current):
        if os.path.isdir(os.path.join(current, '.git')):
            return current
        current = os.path.dirname(current)
    return os.getcwd()


def main():
    project_root = resolve_project_root()
    setup_path = os.path.join(project_root, SETUP_REL)

    data = {}
    if os.path.exists(setup_path):
        with open(setup_path, 'r') as f:
            data = json.load(f)

    data['bypass'] = True
    if 'complete' not in data:
        data['complete'] = False

    os.makedirs(os.path.dirname(setup_path), exist_ok=True)
    with open(setup_path, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')

    print(
        "SWE workflow bypassed for this project.\n"
        "To re-enable: set \"bypass\": false (or remove the field) in "
        ".serena/swe-setup-complete.json."
    )
    sys.exit(0)


if __name__ == '__main__':
    main()
