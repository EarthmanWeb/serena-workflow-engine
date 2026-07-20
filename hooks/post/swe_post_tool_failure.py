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

# Prefix identifying Serena MCP tools. ANY tool under this prefix that fails with
# a parameter-schema error gets the correction — no per-tool list to maintain, so
# edit_memory, write_memory, replace_content, and any future Serena tool are all
# covered automatically.
SERENA_TOOL_PREFIX = 'mcp__plugin_swe_serena__'

# Optional curated signatures — used ONLY as enrichment when the failing tool
# happens to be listed. The generic catch above does the real work; these just
# add precise param names for the most commonly-misused tools. Missing from this
# map ≠ no correction — an unlisted Serena tool still gets the generic guidance.
SERENA_EDIT_SIGNATURES = {
    'mcp__plugin_swe_serena__replace_content': (
        "replace_content(relative_path, needle, repl, mode) — ALL FOUR required.\n"
        "  • relative_path: path to the file\n"
        "  • needle:        the string OR regex to search for (NOT `pattern`)\n"
        "  • repl:          the replacement string (regex backrefs: $!1, $!2, …)\n"
        "  • mode:          \"literal\" or \"regex\"  (REQUIRED — no default)\n"
        "  • allow_multiple_occurrences: optional bool, default false"
    ),
    'mcp__plugin_swe_serena__edit_memory': (
        "edit_memory(memory_name, needle, repl, mode) — needle/repl/mode all "
        "required (NOT `pattern`). Same needle/repl/mode contract as "
        "replace_content, but targets a memory by `memory_name` instead of a "
        "file path. To overwrite a whole memory instead, use "
        "write_memory(memory_name, content)."
    ),
    'mcp__plugin_swe_serena__write_memory': (
        "write_memory(memory_name, content) — writes/overwrites the FULL memory "
        "body. No needle/repl/mode. Use this (not edit_memory) when rewriting a "
        "memory wholesale."
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

# Bare (unqualified) Serena tool names the assistant sometimes calls by dropping
# the mcp__plugin_swe_serena__ prefix. In a deferred-tools session the schema is
# not loaded, so a bare call fails at NAME RESOLUTION with "No such tool
# available: <name>" — before any parameter check. We map the bare name back to
# its fully-qualified form so the correction can name the exact tool to load.
_BARE_SERENA_NAMES = frozenset([
    'read_memory', 'list_memories', 'write_memory', 'edit_memory',
    'delete_memory', 'search_memories_by_name', 'search_memories_by_front_matter',
    'get_symbols_overview', 'find_symbol', 'find_referencing_symbols',
    'search_for_pattern', 'replace_content', 'replace_symbol_body',
    'insert_after_symbol', 'insert_before_symbol', 'initial_instructions',
])

# Substrings that mark an unresolved-tool-name failure (deferred tool not loaded).
_UNRESOLVED_NAME_MARKERS = (
    'no such tool available',
    'no such tool',
    'tool not found',
    'is not available',
)


def unresolved_serena_correction(tool_name: str, tool_error: str) -> str:
    """Return a correction when a BARE (unqualified) Serena tool name failed to
    resolve because its deferred schema was never loaded, else empty string.

    This is the exact trap behind the "No such tool available: read_memory"
    class of first-move errors: the assistant calls `read_memory` instead of
    `mcp__plugin_swe_serena__read_memory`, and in a deferred-tools session the
    bare name resolves to nothing. We tell it to ToolSearch the fully-qualified
    tool first, then re-call by that name.

    NOTE: whether this fires depends on the harness delivering a tool-failure
    event for an unresolved name — some harnesses reject the call before any
    PostToolUse hook runs. It is a best-effort safety net; the durable fix is the
    instruction strings (SessionStart / workflow-gate / init-gate) that mandate
    ToolSearch-first and the fully-qualified name.
    """
    bare = str(tool_name).strip()
    err = str(tool_error).lower()
    # Only act on a bare Serena name AND an unresolved-name style error. A bare
    # name that is already fully-qualified (has the prefix) is not our case.
    if bare not in _BARE_SERENA_NAMES:
        return ''
    if not any(marker in err for marker in _UNRESOLVED_NAME_MARKERS):
        return ''
    fq = f"{SERENA_TOOL_PREFIX}{bare}"
    return (
        f"🔧 UNRESOLVED TOOL: `{bare}` is not callable — you used the BARE name.\n"
        f"The Serena MCP tools are DEFERRED (schema not loaded) and MUST be "
        f"called by their FULLY-QUALIFIED name. Load the schema, then re-call:\n"
        f"  ToolSearch(\"select:{fq}\")\n"
        f"Then call {fq}(...) — NEVER the bare {bare}."
    )


def schema_correction(tool_name: str, tool_error: str) -> str:
    """Return a signature-correction string for ANY Serena tool that fails with a
    parameter-schema error, else empty string.

    Generic by design: keys off the Serena tool-name PREFIX + schema-error
    markers, NOT a hardcoded tool list — so edit_memory, write_memory,
    replace_content, and every future Serena tool are covered automatically.
    A curated exact signature (SERENA_EDIT_SIGNATURES) is appended when available.

    Fires on the FIRST failure (before the flailing threshold) so the assistant
    re-calls with the right params immediately instead of guessing again.
    """
    if not tool_name.startswith(SERENA_TOOL_PREFIX):
        return ''
    err = str(tool_error).lower()
    if not any(marker in err for marker in _SCHEMA_ERROR_MARKERS):
        return ''

    sig = SERENA_EDIT_SIGNATURES.get(tool_name)
    if sig:
        detail = f"Correct signature:\n\n{sig}\n\n"
    else:
        detail = ""
    return (
        f"🔧 WRONG PARAMS for {tool_name} (schema validation failed).\n{detail}"
        f"Do NOT guess param names — fetch the authoritative schema and re-call:\n"
        f"  ToolSearch(\"select:{tool_name}\")\n"
        f"Then call {tool_name} with the EXACT params from that schema."
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

        # Bare/unqualified Serena name that failed to resolve (deferred schema not
        # loaded): tell the assistant to ToolSearch the fully-qualified tool and
        # re-call by that name. Checked BEFORE schema_correction — an unresolved
        # name is a name-resolution failure, not a parameter-schema failure.
        name_fix = unresolved_serena_correction(tool_name, tool_error)
        if name_fix:
            output_message(name_fix, "PostToolUse")
            return

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
