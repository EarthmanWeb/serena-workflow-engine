"""Tests for experiments/harness-ab/{run.py,analyze.py} pure functions.

experiments/harness-ab is a hyphenated directory name, so run.py/analyze.py
are loaded via importlib.util.spec_from_file_location (see _hookutil.py's
load_script() strategy for hyphen-named scripts), not via normal import.
"""
import argparse
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
HARNESS_DIR = os.path.join(REPO_ROOT, "experiments", "harness-ab")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run = _load("harness_ab_run", os.path.join(HARNESS_DIR, "run.py"))
analyze = _load("harness_ab_analyze", os.path.join(HARNESS_DIR, "analyze.py"))


class ParseUnittestOutputTest(unittest.TestCase):
    def test_ok(self):
        text = "....\n----------------------------------------------------------------------\nRan 4 tests in 0.010s\n\nOK\n"
        result = run.parse_unittest_output(text)
        self.assertEqual(result["total"], 4)
        self.assertEqual(result["passed"], 4)
        self.assertTrue(result["ok"])
        self.assertEqual(result["failures"], 0)
        self.assertEqual(result["errors"], 0)

    def test_ok_with_skipped(self):
        text = "Ran 5 tests in 0.02s\n\nOK (skipped=1)\n"
        result = run.parse_unittest_output(text)
        self.assertEqual(result["total"], 5)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["passed"], 4)
        self.assertTrue(result["ok"])

    def test_failed_failures_only(self):
        text = "Ran 6 tests in 0.03s\n\nFAILED (failures=2)\n"
        result = run.parse_unittest_output(text)
        self.assertEqual(result["total"], 6)
        self.assertEqual(result["failures"], 2)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(result["passed"], 4)
        self.assertFalse(result["ok"])

    def test_failed_failures_and_errors(self):
        text = "Ran 10 tests in 0.1s\n\nFAILED (failures=3, errors=1)\n"
        result = run.parse_unittest_output(text)
        self.assertEqual(result["total"], 10)
        self.assertEqual(result["failures"], 3)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["passed"], 6)
        self.assertFalse(result["ok"])

    def test_failed_with_skipped(self):
        text = "Ran 8 tests in 0.1s\n\nFAILED (failures=1, errors=1, skipped=2)\n"
        result = run.parse_unittest_output(text)
        self.assertEqual(result["passed"], 4)
        self.assertFalse(result["ok"])

    def test_no_tests_ran(self):
        result = run.parse_unittest_output("")
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["passed"], 0)
        self.assertFalse(result["ok"])

    def test_unparseable_text(self):
        result = run.parse_unittest_output("some random garbage with no markers")
        self.assertEqual(result["total"], 0)
        self.assertFalse(result["ok"])


class ParseTranscriptTest(unittest.TestCase):
    def _sample_lines(self):
        events = [
            {
                "type": "system",
                "subtype": "init",
                "mcp_servers": [{"name": "serena"}, {"name": "swe-wm"}],
                "plugins": [{"name": "swe"}],
            },
            {
                "type": "assistant",
                "message": {"content": [
                    {"type": "text", "text": "Let me look."},
                    {"type": "tool_use", "name": "Read", "input": {}},
                ]},
            },
            {
                "type": "assistant",
                "message": {"content": [
                    {"type": "tool_use", "name": "Agent", "input": {}},
                    {"type": "tool_use", "name": "Bash", "input": {}},
                ]},
            },
            {
                "type": "user",
                "message": {"content": [
                    {"type": "tool_result", "is_error": True,
                     "content": [{"type": "text", "text": "PreToolUse hook BLOCKED this action"}]},
                ]},
            },
            {
                "type": "user",
                "message": {"content": [
                    {"type": "tool_result", "is_error": True,
                     "content": "generic failure, not a hook"},
                ]},
            },
            {
                "type": "user",
                "message": {"content": [
                    {"type": "text", "text": "Stop hook prevented completion, retrying"},
                ]},
            },
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "num_turns": 12,
                "duration_ms": 5000,
                "duration_api_ms": 4000,
                "total_cost_usd": 0.42,  # raw transcript field name; mapped to metrics["est_cost_usd"]
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_creation_input_tokens": 10,
                    "cache_read_input_tokens": 20,
                },
                # Real shape (per results/20260929-123133/runs/*/transcript.jsonl
                # `result` events): camelCase per-model dict keyed by model id,
                # each value carrying the 4 token fields + costUSD + extras.
                "modelUsage": {
                    "claude-sonnet-5": {
                        "inputTokens": 90, "outputTokens": 45,
                        "cacheReadInputTokens": 15, "cacheCreationInputTokens": 8,
                        "costUSD": 0.40, "contextWindow": 200000,
                    },
                    "claude-haiku": {
                        "inputTokens": 10, "outputTokens": 5,
                        "cacheReadInputTokens": 5, "cacheCreationInputTokens": 2,
                        "costUSD": 0.02, "contextWindow": 200000,
                    },
                },
            },
        ]
        return [json.dumps(e) for e in events]

    def test_full_sample(self):
        m = run.parse_transcript(self._sample_lines())
        self.assertEqual(m["assistant_message_count"], 2)
        self.assertEqual(m["tool_calls_by_name"], {"Read": 1, "Agent": 1, "Bash": 1})
        self.assertEqual(m["total_tool_calls"], 3)
        self.assertEqual(m["subagent_launches"], 1)
        self.assertEqual(m["tool_result_errors"], 2)
        self.assertEqual(m["hook_denials"], 1)
        self.assertEqual(m["stop_hook_blocks"], 1)
        self.assertEqual(m["subtype"], "success")
        self.assertFalse(m["is_error"])
        self.assertEqual(m["num_turns"], 12)
        self.assertEqual(m["est_cost_usd"], 0.42)
        self.assertEqual(m["usage"]["input_tokens"], 100)
        self.assertEqual(m["main_tokens"], 180)
        # all_model_tokens sums the 4 token fields over every model in
        # modelUsage: (90+45+15+8) + (10+5+5+2) = 158 + 22 = 180.
        self.assertEqual(m["all_model_tokens"], 180)
        # total_tokens follows all_model_tokens when modelUsage is present.
        self.assertEqual(m["total_tokens"], 180)
        self.assertEqual(m["distinct_models_used"], 2)
        self.assertEqual(
            sorted(m["model_usage"].keys()), ["claude-haiku", "claude-sonnet-5"]
        )
        self.assertEqual(
            sorted(s["name"] for s in m["mcp_servers"]), ["serena", "swe-wm"]
        )
        self.assertEqual(m["plugins"], [{"name": "swe"}])

    def test_empty_lines_and_garbage_are_skipped(self):
        lines = ["", "   ", "not json {{{", json.dumps({"type": "result"})]
        m = run.parse_transcript(lines)
        self.assertEqual(m["subtype"], None)
        self.assertEqual(m["total_tool_calls"], 0)

    def test_no_result_event(self):
        lines = [json.dumps({"type": "assistant", "message": {"content": []}})]
        m = run.parse_transcript(lines)
        self.assertIsNone(m["num_turns"])
        self.assertEqual(m["total_tokens"], 0)

    def test_missing_usage_fields_default_zero(self):
        lines = [json.dumps({"type": "result", "usage": {"input_tokens": 5}})]
        m = run.parse_transcript(lines)
        self.assertEqual(m["usage"]["input_tokens"], 5)
        self.assertEqual(m["usage"]["output_tokens"], 0)
        # No modelUsage on this result -> total_tokens falls back to
        # main_tokens (the main-agent-only usage sum).
        self.assertEqual(m["main_tokens"], 5)
        self.assertEqual(m["all_model_tokens"], 0)
        self.assertEqual(m["total_tokens"], 5)

    def test_real_result_event_model_usage_shape(self):
        # Redacted excerpt of an actual `result` event from
        # results/20260929-123133/runs/v5-t0/transcript.jsonl: single model,
        # modelUsage token counts roughly 4x the main `usage` block because
        # the run delegated to subagents whose tokens only show up here.
        event = {
            "type": "result", "subtype": "success", "is_error": False,
            "num_turns": 31, "total_cost_usd": 5.25275125,
            "usage": {
                "input_tokens": 7063, "cache_creation_input_tokens": 97211,
                "cache_read_input_tokens": 1609030, "output_tokens": 27254,
            },
            "modelUsage": {
                "claude-sonnet-5": {
                    "inputTokens": 30074, "outputTokens": 68680,
                    "cacheReadInputTokens": 3174255,
                    "cacheCreationInputTokens": 229394,
                    "webSearchRequests": 0, "costUSD": 5.25275125,
                    "contextWindow": 200000, "maxOutputTokens": 32000,
                }
            },
            "permission_denials": [],
        }
        m = run.parse_transcript([json.dumps(event)])
        self.assertEqual(m["main_tokens"], 7063 + 97211 + 1609030 + 27254)
        self.assertEqual(m["all_model_tokens"], 30074 + 68680 + 3174255 + 229394)
        self.assertEqual(m["total_tokens"], m["all_model_tokens"])
        self.assertGreater(m["all_model_tokens"], m["main_tokens"])
        self.assertEqual(m["distinct_models_used"], 1)

    def test_subagent_events_counted_separately(self):
        # Real shape: an assistant/user event that belongs to a subagent's
        # own turn carries a non-null top-level parent_tool_use_id.
        events = [
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Agent", "input": {}},
            ]}},
            {"type": "assistant", "parent_tool_use_id": "toolu_01subagent",
             "message": {"content": [{"type": "text", "text": "working"}]}},
            {"type": "user", "parent_tool_use_id": "toolu_01subagent",
             "message": {"content": [{"type": "tool_result", "content": "ok"}]}},
        ]
        m = run.parse_transcript([json.dumps(e) for e in events])
        self.assertEqual(m["subagent_launches"], 1)
        self.assertEqual(m["assistant_message_count"], 1)  # main agent only
        self.assertEqual(m["assistant_turns_incl_subagents"], 2)  # main + subagent
        self.assertEqual(m["subagent_messages"], 2)  # 1 assistant + 1 user


class ParseTranscriptMemoryFileReadsTest(unittest.TestCase):
    def test_counts_memory_mcp_tools_and_serena_memory_reads(self):
        events = [
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "mcp__plugin_swe_serena__read_memory",
                 "input": {"memory_name": "wf/WF_INIT"}},
                {"type": "tool_use", "name": "mcp__plugin_swe_serena__list_memories", "input": {}},
                {"type": "tool_use", "name": "mcp__plugin_swe_serena__search_memories_by_name",
                 "input": {"query": "x"}},
                {"type": "tool_use", "name": "mcp__plugin_swe_serena__search_memories_by_front_matter",
                 "input": {"query": "x"}},
                # A Read of a memory file (file_path variant).
                {"type": "tool_use", "name": "Read",
                 "input": {"file_path": "/repo/.serena/memory/feature/FOO.md"}},
                # A Read of a memory file (path variant).
                {"type": "tool_use", "name": "Read", "input": {"path": ".serena/memory/ref/BAR.md"}},
                # A Read that is NOT a memory file -> not counted.
                {"type": "tool_use", "name": "Read", "input": {"file_path": "/repo/src/main.py"}},
                # Some other tool entirely -> not counted.
                {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
            ]}},
        ]
        m = run.parse_transcript([json.dumps(e) for e in events])
        self.assertEqual(m["memory_file_reads"], 6)
        self.assertEqual(m["total_tool_calls"], 8)

    def test_zero_when_no_memory_activity(self):
        events = [
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
                {"type": "tool_use", "name": "Read", "input": {"file_path": "/repo/README.md"}},
            ]}},
        ]
        m = run.parse_transcript([json.dumps(e) for e in events])
        self.assertEqual(m["memory_file_reads"], 0)

    def test_read_with_missing_or_non_dict_input(self):
        events = [
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Read"},  # no "input" key at all
                {"type": "tool_use", "name": "Read", "input": "not-a-dict"},
            ]}},
        ]
        m = run.parse_transcript([json.dumps(e) for e in events])
        self.assertEqual(m["memory_file_reads"], 0)
        self.assertEqual(m["total_tool_calls"], 2)


class ParseFailedTestIdsTest(unittest.TestCase):
    def test_extracts_fail_and_error_lines(self):
        text = (
            "FF.E\n"
            "======================================================================\n"
            "FAIL: test_foo (tests.test_bar.MyTest)\n"
            "----------------------------------------------------------------------\n"
            "AssertionError\n"
            "======================================================================\n"
            "ERROR: test_baz (tests.test_bar.MyTest)\n"
            "----------------------------------------------------------------------\n"
            "ValueError\n"
            "----------------------------------------------------------------------\n"
            "Ran 4 tests in 0.01s\n\nFAILED (failures=1, errors=1)\n"
        )
        ids = run.parse_failed_test_ids(text)
        self.assertEqual(ids, [
            "test_foo (tests.test_bar.MyTest)",
            "test_baz (tests.test_bar.MyTest)",
        ])

    def test_empty_text(self):
        self.assertEqual(run.parse_failed_test_ids(""), [])
        self.assertEqual(run.parse_failed_test_ids(None), [])

    def test_no_failures(self):
        text = "....\n----------------------------------------------------------------------\nRan 4 tests in 0.01s\n\nOK\n"
        self.assertEqual(run.parse_failed_test_ids(text), [])

    def test_dedup_preserves_order(self):
        text = "FAIL: test_a (m.T)\nFAIL: test_a (m.T)\nFAIL: test_b (m.T)\n"
        self.assertEqual(run.parse_failed_test_ids(text), ["test_a (m.T)", "test_b (m.T)"])


class ScoreRunPersistenceTest(unittest.TestCase):
    """score_run() with a run_dir: writes acceptance.txt/regression.txt and
    populates failed_tests on both result dicts. Uses a synthetic work_dir
    (not a real reference_solution/) so this exercises the FAILED path."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="harness_score_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.work_dir = os.path.join(self.tmp, "work")
        os.makedirs(self.work_dir)
        self.run_dir = os.path.join(self.tmp, "run")

        # A regression tests/ dir with one failing test (no hidden_tests/
        # dir on disk in the real fixture path, so acceptance takes the
        # "hidden_tests/ not present" branch — still exercises log writing).
        tests_dir = os.path.join(self.work_dir, "tests")
        os.makedirs(tests_dir)
        with open(os.path.join(tests_dir, "__init__.py"), "w") as f:
            f.write("")
        with open(os.path.join(tests_dir, "test_sample.py"), "w") as f:
            f.write(
                "import unittest\n"
                "class T(unittest.TestCase):\n"
                "    def test_fails(self):\n"
                "        self.fail('boom')\n"
                "    def test_passes(self):\n"
                "        pass\n"
            )

    def test_writes_log_files_and_failed_tests(self):
        acceptance, regression = run.score_run(self.work_dir, run_dir=self.run_dir)

        self.assertIn("failed_tests", acceptance)
        self.assertIn("failed_tests", regression)
        self.assertEqual(regression["failed_tests"], ["test_fails (tests.test_sample.T.test_fails)"])
        self.assertFalse(regression["ok"])

        acc_log = os.path.join(self.run_dir, "acceptance.txt")
        reg_log = os.path.join(self.run_dir, "regression.txt")
        self.assertTrue(os.path.exists(acc_log))
        self.assertTrue(os.path.exists(reg_log))
        with open(reg_log) as f:
            reg_content = f.read()
        self.assertIn("test_fails", reg_content)
        self.assertIn("exit_code:", reg_content)

    def test_run_dir_none_does_not_raise(self):
        # Default (no run_dir) must behave exactly as before: no files
        # written, no exception.
        acceptance, regression = run.score_run(self.work_dir)
        self.assertIn("failed_tests", acceptance)
        self.assertIn("failed_tests", regression)


class CleanEnvTest(unittest.TestCase):
    def test_strips_claude_and_swe_prefixed_keys(self):
        src = {
            "CLAUDE_SESSION_ID": "abc",
            "CLAUDESOMETHING": "x",
            "SWE_FOO": "y",
            "SWE_BAR_BAZ": "z",
            "PATH": "/usr/bin",
        }
        env = run.clean_env(src)
        self.assertNotIn("CLAUDE_SESSION_ID", env)
        self.assertNotIn("CLAUDESOMETHING", env)
        self.assertNotIn("SWE_FOO", env)
        self.assertNotIn("SWE_BAR_BAZ", env)
        self.assertEqual(env["PATH"], "/usr/bin")

    def test_keeps_claude_config_dir(self):
        src = {"CLAUDE_CONFIG_DIR": "/home/x/.config/claude"}
        env = run.clean_env(src)
        self.assertEqual(env["CLAUDE_CONFIG_DIR"], "/home/x/.config/claude")

    def test_strips_all_anthropic_keys(self):
        # A stray ANTHROPIC_* key must never be able to switch the child
        # process from subscription auth to API billing.
        src = {
            "ANTHROPIC_API_KEY": "sk-x",
            "ANTHROPIC_AUTH_TOKEN": "tok",
            "ANTHROPIC_BASE_URL": "https://example.com",
            "ANTHROPIC_MODEL": "claude-x",
            "ANTHROPIC_SOMETHING_ELSE": "y",
        }
        env = run.clean_env(src)
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", env)
        self.assertNotIn("ANTHROPIC_BASE_URL", env)
        self.assertNotIn("ANTHROPIC_MODEL", env)
        self.assertNotIn("ANTHROPIC_SOMETHING_ELSE", env)

    def test_strips_aws_bedrock_bearer_token(self):
        src = {"AWS_BEARER_TOKEN_BEDROCK": "tok", "PATH": "/usr/bin"}
        env = run.clean_env(src)
        self.assertNotIn("AWS_BEARER_TOKEN_BEDROCK", env)
        self.assertEqual(env["PATH"], "/usr/bin")

    def test_strips_bedrock_vertex_flags_via_claude_prefix(self):
        src = {"CLAUDE_CODE_USE_BEDROCK": "1", "CLAUDE_CODE_USE_VERTEX": "1"}
        env = run.clean_env(src)
        self.assertNotIn("CLAUDE_CODE_USE_BEDROCK", env)
        self.assertNotIn("CLAUDE_CODE_USE_VERTEX", env)

    def test_sets_mcp_timeout(self):
        env = run.clean_env({})
        self.assertEqual(env["MCP_TIMEOUT"], "300000")


class BuildCommandTest(unittest.TestCase):
    def test_control_arm_no_plugin_dir(self):
        cmd = run.build_command("do the task", "claude-sonnet-5", 5.0)
        self.assertIn("claude", cmd)
        self.assertIn("-p", cmd)
        self.assertIn("do the task", cmd)
        self.assertIn("--output-format", cmd)
        self.assertIn("stream-json", cmd)
        self.assertIn("--dangerously-skip-permissions", cmd)
        self.assertIn("--no-session-persistence", cmd)
        self.assertNotIn("--plugin-dir", cmd)
        self.assertIn("--setting-sources", cmd)
        idx = cmd.index("--setting-sources")
        self.assertEqual(cmd[idx + 1], "project,local")

    def test_plugin_arm_includes_plugin_dir(self):
        cmd = run.build_command("do the task", "claude-sonnet-5", 5.0,
                                 plugin_dir="/tmp/armdir")
        self.assertIn("--plugin-dir", cmd)
        idx = cmd.index("--plugin-dir")
        self.assertEqual(cmd[idx + 1], "/tmp/armdir")

    def test_effort_optional(self):
        cmd_no_effort = run.build_command("t", "m", 1.0)
        self.assertNotIn("--effort", cmd_no_effort)
        cmd_effort = run.build_command("t", "m", 1.0, effort="high")
        self.assertIn("--effort", cmd_effort)
        idx = cmd_effort.index("--effort")
        self.assertEqual(cmd_effort[idx + 1], "high")

    def test_budget_and_model_present(self):
        cmd = run.build_command("t", "claude-sonnet-5", 3.5)
        idx = cmd.index("--max-budget-usd")
        self.assertEqual(cmd[idx + 1], "3.5")
        idx = cmd.index("--model")
        self.assertEqual(cmd[idx + 1], "claude-sonnet-5")

    def test_budget_none_omits_flag(self):
        # Default budget_usd is None at the CLI level: no --max-budget-usd
        # flag is passed at all (no dollar cap on a flat-rate subscription).
        cmd = run.build_command("t", "claude-sonnet-5", None)
        self.assertNotIn("--max-budget-usd", cmd)


class ParseAuthStatusTest(unittest.TestCase):
    def test_subscription_logged_in_ok(self):
        text = json.dumps({
            "loggedIn": True, "authMethod": "claude.ai",
            "apiProvider": "firstParty", "subscriptionType": "max",
        })
        status = run.parse_auth_status(text)
        self.assertTrue(status["ok"])
        self.assertTrue(status["loggedIn"])
        self.assertEqual(status["authMethod"], "claude.ai")
        self.assertEqual(status["subscriptionType"], "max")
        self.assertEqual(status["apiProvider"], "firstParty")
        self.assertIsNone(status["reason"])

    def test_api_key_auth_not_ok(self):
        text = json.dumps({"loggedIn": True, "authMethod": "apiKey",
                            "apiProvider": "firstParty"})
        status = run.parse_auth_status(text)
        self.assertFalse(status["ok"])
        self.assertIsNotNone(status["reason"])

    def test_not_logged_in_not_ok(self):
        text = json.dumps({"loggedIn": False, "authMethod": None})
        status = run.parse_auth_status(text)
        self.assertFalse(status["ok"])

    def test_empty_output_not_ok(self):
        status = run.parse_auth_status("")
        self.assertFalse(status["ok"])
        self.assertIsNotNone(status["reason"])

    def test_unparseable_json_not_ok(self):
        status = run.parse_auth_status("not json {{{")
        self.assertFalse(status["ok"])
        self.assertIsNotNone(status["reason"])

    def test_non_dict_json_not_ok(self):
        status = run.parse_auth_status(json.dumps([1, 2, 3]))
        self.assertFalse(status["ok"])
        self.assertIsNotNone(status["reason"])

    def test_missing_fields_default_none(self):
        status = run.parse_auth_status(json.dumps({}))
        self.assertFalse(status["ok"])
        self.assertIsNone(status["loggedIn"])
        self.assertIsNone(status["authMethod"])


class CheckAuthTest(unittest.TestCase):
    def test_ok_status_returns_without_raising(self):
        orig = run.subprocess.run
        fake_stdout = json.dumps({"loggedIn": True, "authMethod": "claude.ai",
                                   "apiProvider": "firstParty", "subscriptionType": "max"})

        class FakeResult:
            stdout = fake_stdout
            stderr = ""

        run.subprocess.run = lambda *a, **k: FakeResult()
        try:
            status = run.check_auth({}, allow_api_billing=False)
            self.assertTrue(status["ok"])
        finally:
            run.subprocess.run = orig

    def test_bad_status_raises_systemexit_by_default(self):
        orig = run.subprocess.run

        class FakeResult:
            stdout = json.dumps({"loggedIn": False, "authMethod": None})
            stderr = ""

        run.subprocess.run = lambda *a, **k: FakeResult()
        try:
            with self.assertRaises(SystemExit):
                run.check_auth({}, allow_api_billing=False)
        finally:
            run.subprocess.run = orig

    def test_bad_status_allowed_with_flag(self):
        orig = run.subprocess.run

        class FakeResult:
            stdout = json.dumps({"loggedIn": False, "authMethod": None})
            stderr = ""

        run.subprocess.run = lambda *a, **k: FakeResult()
        try:
            status = run.check_auth({}, allow_api_billing=True)
            self.assertFalse(status["ok"])
        finally:
            run.subprocess.run = orig


class ValidateBillingArgsTest(unittest.TestCase):
    def test_subscription_auth_always_valid(self):
        # allow_api_billing False: caps stay optional, no errors regardless
        # of what budget_usd / total_budget_usd are.
        self.assertEqual(run.validate_billing_args(False, None, None), [])
        self.assertEqual(run.validate_billing_args(False, 5.0, None), [])
        self.assertEqual(run.validate_billing_args(False, None, 50.0), [])
        self.assertEqual(run.validate_billing_args(False, -1.0, -1.0), [])

    def test_api_billing_requires_both_caps(self):
        errors = run.validate_billing_args(True, None, None)
        self.assertEqual(len(errors), 2)

    def test_api_billing_missing_budget_usd_only(self):
        errors = run.validate_billing_args(True, None, 100.0)
        self.assertEqual(len(errors), 1)
        self.assertIn("--budget-usd", errors[0])

    def test_api_billing_missing_total_budget_usd_only(self):
        errors = run.validate_billing_args(True, 5.0, None)
        self.assertEqual(len(errors), 1)
        self.assertIn("--total-budget-usd", errors[0])

    def test_api_billing_zero_or_negative_caps_rejected(self):
        self.assertEqual(len(run.validate_billing_args(True, 0, 100.0)), 1)
        self.assertEqual(len(run.validate_billing_args(True, -5.0, 100.0)), 1)
        self.assertEqual(len(run.validate_billing_args(True, 5.0, 0)), 1)
        self.assertEqual(len(run.validate_billing_args(True, 5.0, -100.0)), 1)

    def test_api_billing_valid_caps_no_errors(self):
        self.assertEqual(run.validate_billing_args(True, 5.0, 100.0), [])


class BudgetAllowsNextTest(unittest.TestCase):
    def test_no_total_cap_always_allows(self):
        self.assertTrue(run.budget_allows_next(1000.0, 5.0, None))
        self.assertTrue(run.budget_allows_next(0, None, None))

    def test_allows_when_within_cap(self):
        self.assertTrue(run.budget_allows_next(spent=10.0, per_run_cap=5.0, total_cap=20.0))

    def test_allows_at_exact_boundary(self):
        self.assertTrue(run.budget_allows_next(spent=15.0, per_run_cap=5.0, total_cap=20.0))

    def test_disallows_when_next_run_would_exceed(self):
        self.assertFalse(run.budget_allows_next(spent=16.0, per_run_cap=5.0, total_cap=20.0))

    def test_per_run_cap_none_treated_as_zero(self):
        self.assertTrue(run.budget_allows_next(spent=20.0, per_run_cap=None, total_cap=20.0))
        self.assertFalse(run.budget_allows_next(spent=20.01, per_run_cap=None, total_cap=20.0))


class ShuffledArmOrderTest(unittest.TestCase):
    def test_deterministic_with_seed(self):
        arms = ["baseline", "v5", "control"]
        order1 = run.shuffled_arm_order(arms, 5, seed=42)
        order2 = run.shuffled_arm_order(arms, 5, seed=42)
        self.assertEqual(order1, order2)

    def test_different_seed_can_differ(self):
        arms = ["baseline", "v5", "control"]
        order_a = run.shuffled_arm_order(arms, 10, seed=1)
        order_b = run.shuffled_arm_order(arms, 10, seed=2)
        self.assertNotEqual(order_a, order_b)

    def test_each_trial_is_a_permutation(self):
        arms = ["baseline", "v5", "control"]
        order = run.shuffled_arm_order(arms, 4, seed=7)
        self.assertEqual(len(order), 4)
        for trial_arms in order:
            self.assertEqual(sorted(trial_arms), sorted(arms))

    def test_interleaving_not_blocked(self):
        # With a fixed seed the same arm should not occupy the same slot
        # every trial across enough trials (weak sanity check the shuffle
        # actually shuffles, not proof of statistical quality).
        arms = ["baseline", "v5", "control"]
        order = run.shuffled_arm_order(arms, 6, seed=42)
        first_slot_values = set(trial[0] for trial in order)
        self.assertGreater(len(first_slot_values), 1)


class CountStreamEventsTest(unittest.TestCase):
    def test_counts_by_type(self):
        lines = [
            json.dumps({"type": "tool"}),
            json.dumps({"type": "tool"}),
            json.dumps({"type": "state", "to_s": "WF_EXECUTE"}),
            json.dumps({"type": "edit"}),
            "",
            "garbage{{{",
        ]
        counts = run.count_stream_events(lines)
        self.assertEqual(counts, {"tool": 2, "state": 1, "edit": 1})

    def test_missing_type_bucketed_unknown(self):
        counts = run.count_stream_events([json.dumps({"foo": "bar"})])
        self.assertEqual(counts, {"unknown": 1})

    def test_real_stream_excerpt_gated_state_delegation(self):
        # Redacted excerpt of an actual .serena/streams/<session>.jsonl file
        # (results/20260929-123133/runs/v5-t0/work/.serena/streams/*.jsonl).
        # `gated` marks an internal SWE gate firing; `state` carries
        # from_s/to_s workflow-state transitions; `delegation` marks a
        # subagent kickoff via the Agent tool. All keyed by the same `type`
        # field count_stream_events already reads generically.
        lines = [
            json.dumps({"t": 1, "type": "session_boot", "s": "abc123"}),
            json.dumps({"t": 2, "type": "docread", "s": "abc123", "name": "wf/WF_INIT"}),
            json.dumps({"t": 3, "type": "state", "s": "abc123",
                        "from_s": "WF_CLASSIFY", "to_s": "WF_ARCH_REVIEW"}),
            json.dumps({"t": 4, "type": "delegation", "s": "abc123", "tool": "Agent"}),
            json.dumps({"t": 5, "type": "gated", "t2": 1}),
            json.dumps({"t": 6, "type": "edit", "s": "abc123", "file": "ledgerlite/store.py"}),
            json.dumps({"t": 7, "type": "session_end", "s": "abc123",
                        "final_state": "WF_EXECUTE", "duration_s": 513}),
        ]
        counts = run.count_stream_events(lines)
        self.assertEqual(counts["state"], 1)
        self.assertEqual(counts["gated"], 1)
        self.assertEqual(counts["delegation"], 1)
        self.assertEqual(counts["session_boot"], 1)
        self.assertEqual(counts["session_end"], 1)


class MedianTest(unittest.TestCase):
    def test_odd_count(self):
        self.assertEqual(run.median([3, 1, 2]), 2)

    def test_even_count(self):
        self.assertEqual(run.median([1, 2, 3, 4]), 2.5)

    def test_empty(self):
        self.assertIsNone(run.median([]))

    def test_ignores_none(self):
        self.assertEqual(run.median([1, None, 3, None]), 2)


class AggregateTest(unittest.TestCase):
    def _row(self, arm, trial, ok=True, turns=10, tokens=1000, cost=0.5, wall=60.0,
             timed_out=False, tool_calls=5, hook_denials=0, stop_hook_blocks=0):
        return {
            "run_id": f"{arm}-t{trial}",
            "arm": arm,
            "trial": trial,
            "wall_s": wall,
            "timed_out": timed_out,
            "metrics": {
                "num_turns": turns,
                "total_tokens": tokens,
                "usage": {"output_tokens": tokens // 2, "cache_read_input_tokens": 10},
                "est_cost_usd": cost,
                "total_tool_calls": tool_calls,
                "hook_denials": hook_denials,
                "stop_hook_blocks": stop_hook_blocks,
            },
            "acceptance": {"ok": ok, "passed": 8 if ok else 2, "total": 8},
            "regression": {"ok": True},
        }

    def test_aggregate_basic_stats(self):
        rows = [
            self._row("baseline", 0, turns=10, tokens=1000),
            self._row("baseline", 1, turns=20, tokens=2000),
            self._row("v5", 0, turns=5, tokens=500),
            self._row("v5", 1, turns=15, tokens=1500),
        ]
        agg = analyze.aggregate(rows)
        self.assertEqual(agg["arms"]["baseline"]["n"], 2)
        self.assertEqual(agg["arms"]["baseline"]["stats"]["num_turns"]["median"], 15)
        self.assertEqual(agg["arms"]["v5"]["stats"]["num_turns"]["median"], 10)

    def test_success_rate(self):
        rows = [
            self._row("baseline", 0, ok=True),
            self._row("baseline", 1, ok=False),
        ]
        agg = analyze.aggregate(rows)
        self.assertEqual(agg["arms"]["baseline"]["success_rate"], 0.5)

    def test_vs_baseline_delta(self):
        rows = [
            self._row("baseline", 0, tokens=1000),
            self._row("v5", 0, tokens=500),
        ]
        agg = analyze.aggregate(rows)
        delta = agg["arms"]["v5"]["vs_baseline_pct"]["total_tokens"]
        self.assertAlmostEqual(delta, -50.0)

    def test_no_baseline_no_delta_key(self):
        rows = [self._row("v5", 0, tokens=500)]
        agg = analyze.aggregate(rows)
        self.assertNotIn("vs_baseline_pct", agg["arms"]["v5"])

    def test_timeout_counting(self):
        rows = [
            self._row("control", 0, timed_out=True),
            self._row("control", 1, timed_out=False),
        ]
        agg = analyze.aggregate(rows)
        self.assertEqual(agg["arms"]["control"]["timeouts"], 1)
        self.assertEqual(agg["arms"]["control"]["timeout_rate"], 0.5)

    def test_format_markdown_runs_without_error(self):
        rows = [self._row("baseline", 0), self._row("v5", 0)]
        agg = analyze.aggregate(rows)
        md = analyze.format_markdown(agg)
        self.assertIn("baseline", md)
        self.assertIn("v5", md)

    def test_analyze_median_matches_run_median(self):
        self.assertEqual(analyze.median([1, 2, 3]), run.median([1, 2, 3]))

    def test_reads_old_total_cost_usd_field_for_backward_compat(self):
        # Rows written before the est_cost_usd rename used total_cost_usd;
        # analyze must still read those for old runs.jsonl files.
        old_row = self._row("baseline", 0, cost=1.23)
        del old_row["metrics"]["est_cost_usd"]
        old_row["metrics"]["total_cost_usd"] = 1.23
        agg = analyze.aggregate([old_row])
        self.assertEqual(agg["arms"]["baseline"]["stats"]["est_cost_usd"]["median"], 1.23)

    def test_est_cost_usd_label_in_markdown(self):
        rows = [self._row("baseline", 0)]
        agg = analyze.aggregate(rows)
        md = analyze.format_markdown(agg)
        self.assertIn("est. cost (notional)", md)

    def test_turns_all_agents_label_in_markdown(self):
        rows = [self._row("baseline", 0)]
        agg = analyze.aggregate(rows)
        md = analyze.format_markdown(agg)
        self.assertIn("turns (all agents)", md)
        self.assertIn("main-agent turns", md)

    def test_assistant_turns_incl_subagents_is_aggregated(self):
        rows = [self._row("baseline", 0), self._row("baseline", 1)]
        rows[0]["metrics"]["assistant_turns_incl_subagents"] = 40
        rows[1]["metrics"]["assistant_turns_incl_subagents"] = 60
        agg = analyze.aggregate(rows)
        self.assertEqual(
            agg["arms"]["baseline"]["stats"]["assistant_turns_incl_subagents"]["median"], 50
        )

    def test_memory_file_reads_aggregated(self):
        rows = [self._row("baseline", 0), self._row("baseline", 1)]
        rows[0]["metrics"]["memory_file_reads"] = 4
        rows[1]["metrics"]["memory_file_reads"] = 8
        agg = analyze.aggregate(rows)
        self.assertEqual(agg["arms"]["baseline"]["stats"]["memory_file_reads"]["median"], 6)

    def test_tool_calls_field_reads_total_tool_calls(self):
        rows = [self._row("baseline", 0, tool_calls=17)]
        agg = analyze.aggregate(rows)
        self.assertEqual(agg["arms"]["baseline"]["stats"]["tool_calls"]["median"], 17)

    def test_tool_calls_falls_back_to_old_field_name(self):
        # Pre-fix rows only had the ambiguous `tool_calls` key in metrics.
        row = self._row("baseline", 0)
        del row["metrics"]["total_tool_calls"]
        row["metrics"]["tool_calls"] = 9
        agg = analyze.aggregate([row])
        self.assertEqual(agg["arms"]["baseline"]["stats"]["tool_calls"]["median"], 9)


class PyCompileTest(unittest.TestCase):
    def test_run_py_compiles(self):
        import py_compile
        py_compile.compile(os.path.join(HARNESS_DIR, "run.py"), doraise=True)

    def test_analyze_py_compiles(self):
        import py_compile
        py_compile.compile(os.path.join(HARNESS_DIR, "analyze.py"), doraise=True)


class FullRunPreflightBudgetGuardTest(unittest.TestCase):
    """cmd_full_run/cmd_preflight validate billing args before any I/O
    (subprocess, network, file writes), so calling them with
    --allow-api-billing and no caps must raise SystemExit immediately."""

    def _args(self, **overrides):
        base = dict(
            trials=1, arms=None, model="claude-sonnet-5", effort=None,
            budget_usd=None, total_budget_usd=None, timeout_min=45.0,
            parallel=1, seed=42, out=run.DEFAULT_OUT, resume=None,
            dry_run=False, selftest=False, preflight=False, only_prepare=False,
            allow_api_billing=True,
        )
        base.update(overrides)
        return argparse.Namespace(**base)

    def test_full_run_aborts_without_caps(self):
        with self.assertRaises(SystemExit):
            run.cmd_full_run(self._args(), [])

    def test_full_run_aborts_with_only_per_run_cap(self):
        with self.assertRaises(SystemExit):
            run.cmd_full_run(self._args(budget_usd=5.0), [])

    def test_preflight_aborts_without_caps(self):
        with self.assertRaises(SystemExit):
            run.cmd_preflight(self._args())

    def test_preflight_aborts_with_only_total_cap(self):
        with self.assertRaises(SystemExit):
            run.cmd_preflight(self._args(total_budget_usd=50.0))


class DryRunSmokeTest(unittest.TestCase):
    """Only runs if the fixture track's files already exist; never invokes
    `claude -p`. Skips (does not fail) when the fixture isn't ready yet."""

    def test_dry_run_if_fixture_ready(self):
        task_md = os.path.join(HARNESS_DIR, "task.md")
        fixture_dir = os.path.join(HARNESS_DIR, "fixture")
        if not os.path.exists(task_md) or not os.path.isdir(fixture_dir):
            self.skipTest("fixture track not ready (task.md/fixture/ missing)")
        # We deliberately do not invoke run.main(["--dry-run", ...]) here to
        # avoid mutating experiments/harness-ab/.work or results/ as a side
        # effect of the unit test suite; the harness README documents running
        # --dry-run manually. This test only proves the module wires up
        # correctly once the fixture exists.
        self.assertTrue(callable(run.cmd_dry_run))


class CmdReparseTest(unittest.TestCase):
    """--reparse against a small synthetic stamp dir (not a live claude -p
    invocation): builds a runs.jsonl with one stale row whose metrics are
    obviously wrong (no modelUsage capture, old-shape total_tokens), plus a
    saved transcript.jsonl + .serena/streams/*.jsonl on disk, then checks
    --reparse recomputes metrics/stream_metrics from the saved files, backs
    up the original, and preserves acceptance/wall_s/exit_code untouched."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="harness_reparse_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.stamp_dir = os.path.join(self.tmp, "20990101-000000")
        self.run_dir = os.path.join(self.stamp_dir, "runs", "v5-t0")
        os.makedirs(self.run_dir, exist_ok=True)

        transcript_events = [
            {"type": "result", "subtype": "success", "is_error": False,
             "num_turns": 5, "total_cost_usd": 1.5,
             "usage": {"input_tokens": 10, "output_tokens": 5,
                        "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
             "modelUsage": {"claude-sonnet-5": {
                 "inputTokens": 100, "outputTokens": 50,
                 "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0,
             }}},
        ]
        with open(os.path.join(self.run_dir, "transcript.jsonl"), "w") as f:
            for e in transcript_events:
                f.write(json.dumps(e) + "\n")

        work_dir = os.path.join(self.run_dir, "work")
        streams_dir = os.path.join(work_dir, ".serena", "streams")
        os.makedirs(streams_dir, exist_ok=True)
        with open(os.path.join(streams_dir, "sess.jsonl"), "w") as f:
            f.write(json.dumps({"type": "state", "from_s": "WF_CLASSIFY", "to_s": "WF_EXECUTE"}) + "\n")
            f.write(json.dumps({"type": "gated"}) + "\n")

        # Stale row: old-shape metrics (as if written before this fix), plus
        # acceptance/regression/wall_s that --reparse must NOT touch.
        stale_row = {
            "run_id": "v5-t0", "arm": "v5", "trial": 0,
            "exit_code": 0, "timed_out": False, "wall_s": 123.4,
            "metrics": {"total_tokens": 15, "hook_denials": 0},  # wrong: old bug
            "stream_metrics": {"stream_event_counts": {}, "final_workflow_state": None},
            "acceptance": {"total": 3, "passed": 3, "ok": True, "exit_code": 0},
            "regression": {"total": 2, "passed": 2, "ok": True, "exit_code": 0},
            "isolation": {"ok": True},
        }
        self.runs_jsonl = os.path.join(self.stamp_dir, "runs.jsonl")
        with open(self.runs_jsonl, "w") as f:
            f.write(json.dumps(stale_row) + "\n")

    def test_reparse_recomputes_metrics_and_backs_up_original(self):
        rc = run.cmd_reparse(self.stamp_dir)
        self.assertEqual(rc, 0)

        orig_path = self.runs_jsonl + ".orig"
        self.assertTrue(os.path.exists(orig_path))
        with open(orig_path) as f:
            orig_row = json.loads(f.readline())
        self.assertEqual(orig_row["metrics"]["total_tokens"], 15)  # untouched backup

        with open(self.runs_jsonl) as f:
            new_row = json.loads(f.readline())

        # metrics recomputed from the saved transcript: all_model_tokens
        # (100+50) beats the old buggy total_tokens=15.
        self.assertEqual(new_row["metrics"]["all_model_tokens"], 150)
        self.assertEqual(new_row["metrics"]["total_tokens"], 150)

        # stream_metrics recomputed from the saved work/.serena/streams.
        self.assertEqual(
            new_row["stream_metrics"]["stream_event_counts"].get("gated"), 1
        )
        self.assertEqual(
            new_row["stream_metrics"]["stream_event_counts"].get("state"), 1
        )

        # Recorded acceptance/regression/wall_s/exit_code are untouched.
        self.assertEqual(new_row["acceptance"]["passed"], 3)
        self.assertEqual(new_row["regression"]["passed"], 2)
        self.assertEqual(new_row["wall_s"], 123.4)
        self.assertEqual(new_row["exit_code"], 0)

    def test_reparse_twice_does_not_clobber_orig_backup(self):
        run.cmd_reparse(self.stamp_dir)
        orig_path = self.runs_jsonl + ".orig"
        with open(orig_path) as f:
            first_backup = f.read()
        # Run again; the .orig from the FIRST reparse must survive untouched.
        run.cmd_reparse(self.stamp_dir)
        with open(orig_path) as f:
            second_backup = f.read()
        self.assertEqual(first_backup, second_backup)


class CmdReparseBackfillsFailedTestsTest(unittest.TestCase):
    """--reparse must backfill `failed_tests` onto an existing (present,
    'total' key intact) acceptance/regression dict that predates the field,
    by re-scoring the saved work/ dir -- without touching the recorded
    passed/total/ok result."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="harness_reparse_backfill_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.stamp_dir = os.path.join(self.tmp, "20990101-000000")
        self.run_dir = os.path.join(self.stamp_dir, "runs", "v5-t0")
        os.makedirs(self.run_dir, exist_ok=True)

        with open(os.path.join(self.run_dir, "transcript.jsonl"), "w") as f:
            f.write(json.dumps({"type": "result", "subtype": "success", "num_turns": 1}) + "\n")

        work_dir = os.path.join(self.run_dir, "work")
        tests_dir = os.path.join(work_dir, "tests")
        os.makedirs(tests_dir)
        with open(os.path.join(tests_dir, "__init__.py"), "w") as f:
            f.write("")
        with open(os.path.join(tests_dir, "test_sample.py"), "w") as f:
            f.write(
                "import unittest\n"
                "class T(unittest.TestCase):\n"
                "    def test_fails(self):\n"
                "        self.fail('boom')\n"
            )

        # Old-shape row: acceptance/regression present with a real result
        # (passed/total/ok) but no failed_tests key at all (pre-fix stamp).
        stale_row = {
            "run_id": "v5-t0", "arm": "v5", "trial": 0,
            "exit_code": 0, "timed_out": False, "wall_s": 10.0,
            "metrics": {},
            "stream_metrics": {},
            "acceptance": {"total": 0, "passed": 0, "ok": True, "exit_code": 0},
            "regression": {"total": 5, "passed": 5, "ok": True, "exit_code": 0},
            "isolation": {"ok": True},
        }
        self.runs_jsonl = os.path.join(self.stamp_dir, "runs.jsonl")
        with open(self.runs_jsonl, "w") as f:
            f.write(json.dumps(stale_row) + "\n")

    def test_backfills_failed_tests_without_changing_recorded_result(self):
        rc = run.cmd_reparse(self.stamp_dir)
        self.assertEqual(rc, 0)

        with open(self.runs_jsonl) as f:
            new_row = json.loads(f.readline())

        # Recorded pass/total/ok result is untouched (still says 5/5 ok, the
        # ORIGINAL scoring outcome) even though re-scoring the work/ dir now
        # would show a failure -- reparse only backfills failed_tests, it
        # never overwrites a recorded result.
        self.assertEqual(new_row["regression"]["passed"], 5)
        self.assertEqual(new_row["regression"]["total"], 5)
        self.assertTrue(new_row["regression"]["ok"])
        self.assertIn("failed_tests", new_row["regression"])
        self.assertIn("failed_tests", new_row["acceptance"])


if __name__ == "__main__":
    unittest.main()
