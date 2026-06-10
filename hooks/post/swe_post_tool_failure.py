#!/usr/bin/env python3
"""PostToolUseFailure hook - Track failed tool calls and detect flailing.

Inspired by IronBee's track-action PostToolUseFailure pattern.

Responsibilities:
  1. Log failed tool calls to the JSONL stream
  2. Detect flailing: 2+ consecutive failures of the same tool
  3. After flailing threshold, inject CLAUDE_OBLIGATIONS reminder
"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.output import output_empty, output_message
    from swe_hooks.core.session import extract_session_id
    from swe_hooks.core.stream import get_stream_path, append_event, get_stream_dir
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PostToolUseFailure")

# Consecutive same-tool failures before injecting a warning
FLAIL_THRESHOLD = 2


def count_consecutive_failures(stream_path: str, tool_name: str) -> int:
    """Count consecutive failure events for the same tool from the end of stream.

    Reads backwards through the stream. Stops at the first non-failure event
    or a failure of a different tool.
    """
    if not os.path.exists(stream_path):
        return 0
    try:
        file_size = os.path.getsize(stream_path)
        with open(stream_path, 'r') as f:
            if file_size > 10240:
                f.seek(max(0, file_size - 10240))
                f.readline()  # Skip partial line
            lines = f.readlines()

        count = 0
        for line in reversed(lines):
            try:
                event = json.loads(line.strip())
                if event.get('type') == 'tool_failure' and event.get('name') == tool_name:
                    count += 1
                else:
                    break  # Any other event type or different tool stops the streak
            except (json.JSONDecodeError, ValueError):
                continue
        return count
    except IOError:
        return 0


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        tool_name = get_input_field(input_data, 'tool_name', default='unknown')
        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        tool_input = input_data.get('tool_input', {})
        tool_error = get_input_field(input_data, 'tool_error', default='')

        session_id = extract_session_id(transcript_path)
        if not session_id:
            output_empty()
            return

        # Log failure to stream
        stream_path = get_stream_path(session_id)
        error_summary = str(tool_error)[:200] if tool_error else ''
        append_event(stream_path, 'tool_failure',
                     name=tool_name, s=session_id, err=error_summary)

        # Check for flailing (consecutive same-tool failures)
        consecutive = count_consecutive_failures(stream_path, tool_name)

        if consecutive >= FLAIL_THRESHOLD:
            output_message(
                f"⚠️ FLAILING DETECTED: {tool_name} has failed {consecutive} "
                f"consecutive times. Per CLAUDE_OBLIGATIONS:\n"
                f"1. STOP immediately\n"
                f"2. Re-read the relevant skill/memory\n"
                f"3. Try again with a DIFFERENT approach\n"
                f"4. Ask the user if still failing\n\n"
                f"DO NOT retry the same broken approach.",
                "PostToolUse"
            )
            return

        output_empty()

    except Exception:
        output_empty()


if __name__ == '__main__':
    main()
