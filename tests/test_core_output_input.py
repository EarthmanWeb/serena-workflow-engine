"""Tests for swe_hooks.core.output and swe_hooks.core.input.

output.py: HookOutput builder + module-level output_* helpers (which print JSON
to stdout and sys.exit(0)).
input.py: get_input_field nested traversal (read_stdin_safe reads real stdin and
is deliberately not exercised — see note in the module docstring / final report).

Run:
    python3 -m unittest tests.test_core_output_input -v
"""
import contextlib
import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_core  # noqa: E402

output = import_core("swe_hooks.core.output")
inp = import_core("swe_hooks.core.input")

HookOutput = output.HookOutput


def _capture_exit(fn, *args, **kwargs):
    """Call fn (which prints JSON then sys.exit(0)), return (parsed_json, exit_code).

    Raises AssertionError if fn does not raise SystemExit.
    """
    buf = io.StringIO()
    exit_code = None
    with contextlib.redirect_stdout(buf):
        try:
            fn(*args, **kwargs)
        except SystemExit as e:
            exit_code = e.code
        else:  # pragma: no cover - defensive
            raise AssertionError("expected SystemExit, none raised")
    printed = buf.getvalue()
    return json.loads(printed), exit_code, printed


# ---------------------------------------------------------------------------
# HookOutput builder (no exit / no print)
# ---------------------------------------------------------------------------
class TestHookOutputInit(unittest.TestCase):
    def test_default_event_name(self):
        h = HookOutput()
        self.assertEqual(h.event_name, "PostToolUse")

    def test_custom_event_name(self):
        h = HookOutput("UserPromptSubmit")
        self.assertEqual(h.event_name, "UserPromptSubmit")

    def test_initial_state(self):
        h = HookOutput()
        self.assertEqual(h.messages, [])
        self.assertFalse(h.should_block)
        self.assertIsNone(h.block_reason)


class TestHookOutputAddMessage(unittest.TestCase):
    def test_add_message_appends(self):
        h = HookOutput()
        h.add_message("first")
        h.add_message("second")
        self.assertEqual(h.messages, ["first", "second"])

    def test_add_message_does_not_block(self):
        h = HookOutput()
        h.add_message("hi")
        self.assertFalse(h.should_block)
        self.assertIsNone(h.block_reason)


class TestHookOutputBlock(unittest.TestCase):
    def test_block_sets_flags(self):
        h = HookOutput()
        h.block("nope")
        self.assertTrue(h.should_block)
        self.assertEqual(h.block_reason, "nope")

    def test_block_flips_event_to_pretooluse(self):
        h = HookOutput("PostToolUse")
        h.block("nope")
        self.assertEqual(h.event_name, "PreToolUse")

    def test_block_appends_reason_as_message(self):
        h = HookOutput()
        h.block("denied because X")
        self.assertIn("denied because X", h.messages)
        self.assertEqual(h.messages, ["denied because X"])


class TestHookOutputBuild(unittest.TestCase):
    def test_build_empty_returns_empty_dict(self):
        h = HookOutput()
        self.assertEqual(h.build(), {})

    def test_build_message_case(self):
        h = HookOutput("PostToolUse")
        h.add_message("line one")
        h.add_message("line two")
        result = h.build()
        self.assertEqual(
            result,
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": "line one\nline two",
                }
            },
        )

    def test_build_message_join_with_newline(self):
        h = HookOutput()
        h.add_message("a")
        h.add_message("b")
        self.assertEqual(
            h.build()["hookSpecificOutput"]["additionalContext"], "a\nb"
        )

    def test_build_block_case(self):
        h = HookOutput()
        h.block("blocked reason")
        result = h.build()
        hso = result["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "PreToolUse")
        self.assertEqual(hso["permissionDecision"], "deny")
        self.assertEqual(hso["permissionDecisionReason"], "blocked reason")

    def test_build_block_has_no_additional_context(self):
        # When blocked, the elif branch for additionalContext is not taken.
        h = HookOutput()
        h.block("blocked reason")
        hso = h.build()["hookSpecificOutput"]
        self.assertNotIn("additionalContext", hso)

    def test_build_block_without_reason_omits_reason_key(self):
        # Force should_block True but block_reason None (bypassing block()).
        h = HookOutput()
        h.should_block = True
        h.block_reason = None
        hso = h.build()["hookSpecificOutput"]
        self.assertEqual(hso["permissionDecision"], "deny")
        self.assertNotIn("permissionDecisionReason", hso)

    def test_build_single_message(self):
        h = HookOutput("Notification")
        h.add_message("only")
        self.assertEqual(
            h.build(),
            {
                "hookSpecificOutput": {
                    "hookEventName": "Notification",
                    "additionalContext": "only",
                }
            },
        )


# ---------------------------------------------------------------------------
# HookOutput.output_and_exit (prints + sys.exit)
# ---------------------------------------------------------------------------
class TestHookOutputAndExit(unittest.TestCase):
    def test_output_and_exit_empty(self):
        h = HookOutput()
        parsed, code, _ = _capture_exit(h.output_and_exit)
        self.assertEqual(parsed, {})
        self.assertEqual(code, 0)

    def test_output_and_exit_message(self):
        h = HookOutput("PostToolUse")
        h.add_message("hello")
        parsed, code, _ = _capture_exit(h.output_and_exit)
        self.assertEqual(code, 0)
        self.assertEqual(
            parsed["hookSpecificOutput"]["additionalContext"], "hello"
        )
        self.assertEqual(
            parsed["hookSpecificOutput"]["hookEventName"], "PostToolUse"
        )

    def test_output_and_exit_block(self):
        h = HookOutput()
        h.block("stop right there")
        parsed, code, _ = _capture_exit(h.output_and_exit)
        self.assertEqual(code, 0)
        hso = parsed["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "PreToolUse")
        self.assertEqual(hso["permissionDecision"], "deny")
        self.assertEqual(hso["permissionDecisionReason"], "stop right there")

    def test_output_and_exit_prints_valid_single_json_line(self):
        h = HookOutput()
        h.add_message("x")
        _, _, printed = _capture_exit(h.output_and_exit)
        # A single JSON document terminated by newline (print adds \n).
        self.assertTrue(printed.endswith("\n"))
        json.loads(printed)  # must parse; raises if not


# ---------------------------------------------------------------------------
# Module-level output_* helpers (print + sys.exit(0))
# ---------------------------------------------------------------------------
class TestOutputEmpty(unittest.TestCase):
    def test_output_empty(self):
        parsed, code, _ = _capture_exit(output.output_empty)
        self.assertEqual(parsed, {})
        self.assertEqual(code, 0)


class TestOutputMessage(unittest.TestCase):
    def test_output_message_default_event(self):
        parsed, code, _ = _capture_exit(output.output_message, "a message")
        self.assertEqual(code, 0)
        self.assertEqual(
            parsed,
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": "a message",
                }
            },
        )

    def test_output_message_custom_event(self):
        parsed, _, _ = _capture_exit(
            output.output_message, "ctx", "UserPromptSubmit"
        )
        hso = parsed["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "UserPromptSubmit")
        self.assertEqual(hso["additionalContext"], "ctx")


class TestOutputBlock(unittest.TestCase):
    def test_output_block(self):
        parsed, code, _ = _capture_exit(output.output_block, "denied!")
        self.assertEqual(code, 0)
        self.assertEqual(
            parsed,
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "denied!",
                }
            },
        )


class TestOutputStatus(unittest.TestCase):
    def test_output_status_default_event(self):
        parsed, code, _ = _capture_exit(output.output_status, "WM: edit #3 tracked")
        self.assertEqual(code, 0)
        self.assertEqual(
            parsed,
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": "WM: edit #3 tracked",
                }
            },
        )

    def test_output_status_custom_event(self):
        parsed, _, _ = _capture_exit(
            output.output_status, "state unchanged", "Stop"
        )
        self.assertEqual(parsed["hookSpecificOutput"]["hookEventName"], "Stop")
        self.assertEqual(
            parsed["hookSpecificOutput"]["additionalContext"], "state unchanged"
        )


class TestOutputError(unittest.TestCase):
    def test_output_error_prefixes_message(self):
        parsed, code, _ = _capture_exit(output.output_error, "boom")
        self.assertEqual(code, 0)
        self.assertEqual(
            parsed["hookSpecificOutput"]["additionalContext"],
            "SWE Hook Error: boom",
        )
        self.assertEqual(
            parsed["hookSpecificOutput"]["hookEventName"], "PostToolUse"
        )

    def test_output_error_custom_event(self):
        parsed, _, _ = _capture_exit(output.output_error, "oops", "Notification")
        self.assertEqual(
            parsed["hookSpecificOutput"]["hookEventName"], "Notification"
        )
        self.assertEqual(
            parsed["hookSpecificOutput"]["additionalContext"],
            "SWE Hook Error: oops",
        )


# ---------------------------------------------------------------------------
# input.get_input_field — nested traversal
# ---------------------------------------------------------------------------
class TestGetInputField(unittest.TestCase):
    def test_single_key_present(self):
        data = {"tool_name": "Edit"}
        self.assertEqual(inp.get_input_field(data, "tool_name"), "Edit")

    def test_nested_key_present(self):
        data = {"tool_input": {"file_path": "/a/b.py"}}
        self.assertEqual(
            inp.get_input_field(data, "tool_input", "file_path"), "/a/b.py"
        )

    def test_deeply_nested_key_present(self):
        data = {"a": {"b": {"c": 42}}}
        self.assertEqual(inp.get_input_field(data, "a", "b", "c"), 42)

    def test_missing_top_level_key_returns_default(self):
        data = {"tool_name": "Edit"}
        self.assertIsNone(inp.get_input_field(data, "nope"))

    def test_missing_key_returns_explicit_default(self):
        data = {"tool_name": "Edit"}
        self.assertEqual(
            inp.get_input_field(data, "nope", default="fallback"), "fallback"
        )

    def test_missing_nested_key_returns_default(self):
        data = {"tool_input": {"file_path": "/a/b.py"}}
        self.assertEqual(
            inp.get_input_field(data, "tool_input", "missing", default="d"), "d"
        )

    def test_non_dict_intermediate_returns_default(self):
        # Second key traverses into a string -> not a dict -> default.
        data = {"tool_input": "not-a-dict"}
        self.assertEqual(
            inp.get_input_field(data, "tool_input", "file_path", default="X"), "X"
        )

    def test_non_dict_intermediate_returns_default_none(self):
        data = {"a": 5}
        self.assertIsNone(inp.get_input_field(data, "a", "b"))

    def test_no_keys_returns_input_unchanged(self):
        # Empty *keys: loop never runs, returns current (the input dict itself).
        data = {"x": 1}
        self.assertEqual(inp.get_input_field(data), data)

    def test_no_keys_on_none_input_returns_default(self):
        # current is None, loop never runs -> `current if not None else default`.
        self.assertIsNone(inp.get_input_field(None))

    def test_no_keys_on_none_input_returns_explicit_default(self):
        self.assertEqual(inp.get_input_field(None, default="dd"), "dd")

    def test_none_input_with_key_returns_default(self):
        # input_data None: not a dict -> default on first iteration.
        self.assertEqual(inp.get_input_field(None, "k", default="d"), "d")

    def test_value_present_but_none_returns_default(self):
        # get() finds the key, value is None -> final ternary swaps in default.
        data = {"k": None}
        self.assertEqual(inp.get_input_field(data, "k", default="d"), "d")

    def test_value_none_no_default_returns_none(self):
        data = {"k": None}
        self.assertIsNone(inp.get_input_field(data, "k"))

    def test_falsy_but_not_none_values_preserved(self):
        # 0, "", False, [] are not None -> returned as-is, not swapped for default.
        self.assertEqual(inp.get_input_field({"k": 0}, "k", default="d"), 0)
        self.assertEqual(inp.get_input_field({"k": ""}, "k", default="d"), "")
        self.assertEqual(inp.get_input_field({"k": False}, "k", default="d"), False)
        self.assertEqual(inp.get_input_field({"k": []}, "k", default="d"), [])

    def test_empty_dict_input_returns_default(self):
        self.assertEqual(inp.get_input_field({}, "anything", default="d"), "d")

    def test_intermediate_default_short_circuits_next_key(self):
        # First key missing -> current becomes the default (a dict here); next
        # key then does current.get(...) on that default dict.
        data = {}
        result = inp.get_input_field(data, "missing", "deeper", default={"deeper": 9})
        self.assertEqual(result, 9)


if __name__ == "__main__":
    unittest.main()
