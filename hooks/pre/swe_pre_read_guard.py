#!/usr/bin/env python3
"""PreToolUse hook for Read — large-code-file windowing guard.

Measured basis: 10 full Reads >10k tokens in one transcript study = ~130k
tokens, 27% of all Read tokens in that session. A full Read of a large
source file is rarely needed — Grep -n to locate the relevant lines, then a
windowed Read (offset/limit, ~80 lines) gets the same answer far cheaper.

DENIES a Read with no `offset`/`limit` when the target is a CODE file
(by extension: .py .php .ts .tsx .js .jsx .scss .css .go .rb .java) AND its
line count exceeds LARGE_FILE_LINES (300). Everything else (non-code files,
small code files, any Read that already passes offset/limit) is ALLOWED.

Applies to BOTH the main agent and spawned subagents — unlike the retired
docs-first search gate, this is a pure cost control with no doc-discovery
semantics, so there is no spawned-agent exemption.

Fails open: any error (unreadable file, bad input, missing fields) ALLOWS
the Read rather than blocking on a guard bug.
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import output_empty, output_block
    from swe_hooks.core.input import read_stdin_safe, get_input_field
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PreToolUse")

CODE_EXTENSIONS = {
    '.py', '.php', '.ts', '.tsx', '.js', '.jsx', '.scss', '.css', '.go',
    '.rb', '.java',
}
LARGE_FILE_LINES = 300


def is_code_file(file_path: str) -> bool:
    """True when file_path's extension is one of CODE_EXTENSIONS."""
    if not file_path:
        return False
    _, ext = os.path.splitext(file_path)
    return ext.lower() in CODE_EXTENSIONS


def count_lines(file_path: str) -> int:
    """Line count of file_path, or -1 if it cannot be read."""
    try:
        with open(file_path, 'rb') as f:
            return sum(1 for _ in f)
    except OSError:
        return -1


def should_deny(tool_input: dict) -> bool:
    """True when this Read call must be denied: no offset/limit given,
    target resolves to an existing CODE file over LARGE_FILE_LINES lines."""
    if not isinstance(tool_input, dict):
        return False
    if tool_input.get('offset') is not None or tool_input.get('limit') is not None:
        return False
    file_path = tool_input.get('file_path')
    if not is_code_file(file_path):
        return False
    lines = count_lines(file_path)
    return lines > LARGE_FILE_LINES


def build_deny_message(file_path: str, lines: int) -> str:
    return (
        f"🚫 LARGE FILE READ BLOCKED: {file_path} has {lines} lines "
        f"(> {LARGE_FILE_LINES}) and no offset/limit was given.\n\n"
        "Use Grep -n to locate the relevant lines, then Read with "
        "offset/limit (~80 lines around the match) instead of reading the "
        "whole file."
    )


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        tool_input = get_input_field(input_data, 'tool_input', default={})

        if not should_deny(tool_input):
            output_empty()
            return

        file_path = tool_input.get('file_path', '')
        output_block(build_deny_message(file_path, count_lines(file_path)))

    except Exception as e:
        # Fail open: never block a Read on a guard bug.
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                         "additionalContext": f"Read guard error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
