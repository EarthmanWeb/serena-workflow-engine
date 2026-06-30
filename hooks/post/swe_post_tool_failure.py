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

# Authoritative signatures for Serena edit tools whose param names are commonly
# guessed wrong (e.g. `pattern`/`repl` instead of `needle`/`mode`). When one of
# these fails with a pydantic "Field required" / validation error, we inject the
# correct call signature on the FIRST failure — no need to wait for flailing.
SERENA_EDIT_SIGNATURES = {
    'mcp__plugin_swe_serena__replace_content': (
        "replace_content(relative_path, needle, repl, mode) — ALL FOUR required.\n"
        "  • relative_path: path to the file\n"
        "  • needle:        the string OR regex to search for (NOT `pattern`)\n"
        "  • repl:          the replacement string (regex backrefs: $!1, $!2, …)\n"
        "  • mode:          \"literal\" or \"regex\"  (REQUIRED — no default)\n"
        "  • allow_multiple_occurrences: optional bool, default false"
    ),
    'mcp__plugin_swe_serena__replace_symbol_body': (
        "replace_symbol_body(name_path, relative_path, body) — all three required.\n"
        "  • name_path:     symbol path, e.g. ClassName/method_name\n"
        "  • relative_path: file containing the symbol\n"
        "  • body:          new symbol body, verbatim and correctly indented"
    ),
    'mcp__plugin_swe_serena__insert_after_symbol': (
        "insert_after_symbol(name_path, relative_path, body) — all three required."
    ),
    'mcp__plugin_swe_serena__insert_before_symbol': (
        "insert_before_symbol(name_path, relative_path, body) — all three required."
    ),
}

# Substrings that mark a parameter-schema (validation) failure, as opposed to a
# logic/runtime failure. Only schema failures get the signature-correction.
_SCHEMA_ERROR_MARKERS = (
    'field required',
    'validation error',
    'unexpected keyword',
    'missing',
    'extra fields not permitted',
)


def schema_correction(tool_name: str, tool_error: str) -> str:
    """Return a signature-correction string if this is a Serena edit-tool schema
    failure, else empty string.

    Fires on the FIRST failure (before the flailing threshold) so the assistant
    re-calls with the right params immediately instead of guessing again.
    """
    sig = SERENA_EDIT_SIGNATURES.get(tool_name)
    if not sig:
        return ''
    err = str(tool_error).lower()
    if not any(marker in err for marker in _SCHEMA_ERROR_MARKERS):
        return ''
    return (
        f"🔧 WRONG PARAMS for {tool_name}. Correct signature:\n\n{sig}\n\n"
        f"Re-call now with these EXACT param names. Do not guess — if still "
        f"unsure, fetch the live schema: "
        f"ToolSearch(\"select:{tool_name}\")."
    )


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

        # First-failure signature correction for Serena edit tools: if the call
        # failed because of wrong/missing params, inject the correct signature
        # immediately so the assistant re-calls correctly instead of guessing.
        correction = schema_correction(tool_name, tool_error)
        if correction:
            output_message(correction, "PostToolUse")
            return

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
