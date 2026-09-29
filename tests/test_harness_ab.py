"""Tests for experiments/harness-ab/{run.py,analyze.py} pure functions.

experiments/harness-ab is a hyphenated directory name, so run.py/analyze.py
are loaded via importlib.util.spec_from_file_location (see _hookutil.py's
load_script() strategy for hyphen-named scripts), not via normal import.
"""
import argparse
import importlib.util
import json
import os
import sys
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
                "modelUsage": {"claude-sonnet-5": {}, "claude-haiku": {}},
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
        self.assertEqual(m["total_tokens"], 180)
        self.assertEqual(m["distinct_models_used"], 2)
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
        self.assertEqual(m["total_tokens"], 5)


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


if __name__ == "__main__":
    unittest.main()
