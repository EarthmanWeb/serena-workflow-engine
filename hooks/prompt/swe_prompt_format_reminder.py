#!/usr/bin/env python3
"""UserPromptSubmit hook: pre-emptive response-format-budget reminder.

swe_stop_response_format.py (Stop gate) writes a per-session sentinel whenever
it blocks a turn for exceeding the word budget or emitting recap scaffolding.
This hook injects a one-line reminder into the NEXT turn's context and clears
the sentinel — making the budget salient at the decision point instead of only
post-hoc. Fires at most once per block.

Config-aware: silent when SWE is bypassed / the project is uninitialized / the
gate is disabled, so it never nags on a project that opted out.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.config import (
        get_project_root,
        get_response_format_config,
        resolve_setup_state,
    )
    from swe_hooks.core.stream import get_stream_dir
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "UserPromptSubmit")


def sentinel_path(session):
    return os.path.join(get_stream_dir(), f".format-gate-block-{session}")


def main():
    data = read_stdin_safe()
    if data is None:
        sys.exit(0)

    transcript_path = get_input_field(data, "transcript_path", "") or "unknown"
    session = os.path.splitext(os.path.basename(transcript_path))[0]

    # Respect the same guards as the Stop gate.
    setup = resolve_setup_state(get_project_root())
    if setup.get("bypassed") or not setup.get("initialized"):
        sys.exit(0)
    if not get_response_format_config().get("enabled"):
        sys.exit(0)

    path = sentinel_path(session)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
        print(
            "⚠️ FORMAT BUDGET: your previous turn was BLOCKED by the response-format "
            "gate. This turn: lead with the result, bullets over paragraphs, NO "
            "recap/status/next-steps block, end on the result or the one blocking "
            "question. Prefix the message with `DETAIL:` only if you genuinely need "
            "a long answer."
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
