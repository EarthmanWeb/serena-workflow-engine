"""Coverage for previously-untested pure functions across SWE hooks.

Targets deterministic, input->output helpers so the hooks keep matching ONLY
what they should. Stdlib unittest only; no third-party deps.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_hook  # noqa: E402


class TestBashTestGate(unittest.TestCase):
    mod = import_hook("pre/swe_pre_bash_test_gate")

    def test_is_test_command_matches_playwright(self):
        self.assertTrue(self.mod.is_test_command("npx playwright test"))
        self.assertTrue(self.mod.is_test_command("cd x && npx playwright test tests/foo.spec.ts"))

    def test_is_test_command_ignores_non_test(self):
        for cmd in ("ls -la", "npm run build", "playwright install", "npx tsc --noEmit"):
            self.assertFalse(self.mod.is_test_command(cmd), cmd)

    def test_check_bash_policy_matches_and_reports_rule(self):
        # Monkeypatch load_bash_policy to a known rule set (avoids fs dependency).
        original = self.mod.load_bash_policy
        self.mod.load_bash_policy = lambda: [
            {"pattern": r"docker\s+exec.*wp\b", "message": "use wp_cli MCP"}
        ]
        try:
            hit = self.mod.check_bash_policy("docker exec site wp option get home")
            self.assertIsNotNone(hit)
            self.assertEqual(hit["message"], "use wp_cli MCP")
            self.assertIsNone(self.mod.check_bash_policy("echo hello"))
        finally:
            self.mod.load_bash_policy = original

    def test_check_bash_policy_skips_malformed_regex(self):
        original = self.mod.load_bash_policy
        self.mod.load_bash_policy = lambda: [
            {"pattern": "(unclosed", "message": "bad"},
            {"pattern": "rm -rf", "message": "danger"},
        ]
        try:
            # Malformed pattern is skipped, the valid one still matches.
            hit = self.mod.check_bash_policy("rm -rf /")
            self.assertEqual(hit["message"], "danger")
        finally:
            self.mod.load_bash_policy = original


class TestInitGate(unittest.TestCase):
    mod = import_hook("pre/swe_pre_tool_init_gate")

    def test_is_working_memory_write_true_for_wm_write(self):
        self.assertTrue(self.mod.is_working_memory_write(
            "Write", {"file_path": "/p/.serena/memories/WM_abc123.md"}))

    def test_is_working_memory_write_false_for_other_tool_or_path(self):
        self.assertFalse(self.mod.is_working_memory_write(
            "Edit", {"file_path": "/p/.serena/memories/WM_abc123.md"}))
        self.assertFalse(self.mod.is_working_memory_write(
            "Write", {"file_path": "/p/.serena/memory/feature/FEATURE_X.md"}))
        self.assertFalse(self.mod.is_working_memory_write(
            "Write", {"file_path": "/p/.serena/memories/WM_abc123.txt"}))


class TestPromptWorkflow(unittest.TestCase):
    mod = import_hook("prompt/swe_user_prompt_workflow")

    def test_detect_slash_command_from_command_marker(self):
        self.assertEqual(
            self.mod.detect_slash_command("<command-name>/swe-init</command-name> args"),
            "/swe-init",
        )

    def test_detect_slash_command_from_bare_slash(self):
        self.assertEqual(self.mod.detect_slash_command("/swe-status now"), "/swe-status")
        self.assertEqual(self.mod.detect_slash_command("/gherkin-dev"), "/gherkin-dev")

    def test_detect_slash_command_none_for_plain_prompt(self):
        self.assertIsNone(self.mod.detect_slash_command("please fix the bug"))
        self.assertIsNone(self.mod.detect_slash_command(""))
        self.assertIsNone(self.mod.detect_slash_command(None))


class TestTodoSync(unittest.TestCase):
    mod = import_hook("post/swe_post_todo_wm_sync")

    def test_format_todos_status_glyphs(self):
        todos = [
            {"content": "done thing", "status": "completed"},
            {"content": "doing thing", "status": "in_progress"},
            {"content": "todo thing", "status": "pending"},
        ]
        out = self.mod.format_todos(todos)
        self.assertIn("- [x] done thing", out)
        self.assertIn("- [~] doing thing *(in progress)*", out)
        self.assertIn("- [ ] todo thing", out)

    def test_format_todos_empty(self):
        self.assertEqual(self.mod.format_todos([]), "")

    def test_format_todos_defaults_to_pending(self):
        self.assertEqual(self.mod.format_todos([{"content": "x"}]), "- [ ] x")


class TestToolFailureSchemaCorrection(unittest.TestCase):
    mod = import_hook("post/swe_post_tool_failure")

    def test_serena_tool_schema_error_returns_correction(self):
        msg = self.mod.schema_correction(
            "mcp__plugin_swe_serena__replace_content",
            "2 validation errors: needle Field required, mode Field required",
        )
        self.assertIn("WRONG PARAMS", msg)
        self.assertIn("ToolSearch", msg)

    def test_non_serena_tool_returns_empty(self):
        self.assertEqual(self.mod.schema_correction("Bash", "field required"), "")

    def test_serena_tool_non_schema_error_returns_empty(self):
        # A Serena tool failing for a NON-schema reason must not fire.
        self.assertEqual(
            self.mod.schema_correction(
                "mcp__plugin_swe_serena__read_memory", "memory not found"),
            "",
        )

    def test_count_consecutive_failures_missing_stream(self):
        self.assertEqual(
            self.mod.count_consecutive_failures("/no/such/stream.jsonl", "Bash"), 0)


class TestStopContinueWorking(unittest.TestCase):
    mod = import_hook("stop/swe_stop_continue_working")

    def test_count_stop_blocks_missing_stream_is_zero(self):
        self.assertEqual(
            self.mod.count_stop_blocks("/no/such/stream.jsonl", "WF_EXECUTE"), 0)


class TestSessionEnd(unittest.TestCase):
    mod = import_hook("session/swe_session_end")

    def test_get_session_duration_missing_stream_is_zero(self):
        self.assertEqual(self.mod.get_session_duration("/no/such/stream.jsonl"), 0)

    def test_get_session_duration_computes_elapsed_from_first_event(self):
        # First event carries a 't' epoch; duration = now - t (>= 0).
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write('{"t": 1000, "event": "start"}\n')
            f.write('{"t": 1005, "event": "next"}\n')
            path = f.name
        try:
            dur = self.mod.get_session_duration(path)
            self.assertIsInstance(dur, int)
            self.assertGreater(dur, 0)  # now (epoch seconds) is well past t=1000
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
