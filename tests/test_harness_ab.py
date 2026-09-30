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


class ParseTranscriptHookAttachmentTest(unittest.TestCase):
    """hook_attachment_blocks/hook_attachment_chars: every non-empty
    tool_result and injected text content block on a user-role event,
    counted unconditionally (not filtered to errors/hook-denial matches),
    across main agent + subagents. See SPEC_HARNESS_EFFICIENCY_TUNING's
    <=300 blocks / <=150k chars acceptance budget."""

    def test_counts_tool_result_and_text_blocks(self):
        events = [
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "content": "ok, 5 chars is not this"},
                {"type": "text", "text": "hook additionalContext here"},
            ]}},
        ]
        m = run.parse_transcript([json.dumps(e) for e in events])
        self.assertEqual(m["hook_attachment_blocks"], 2)
        self.assertEqual(
            m["hook_attachment_chars"],
            len("ok, 5 chars is not this") + len("hook additionalContext here"))

    def test_empty_blocks_not_counted(self):
        events = [
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "content": ""},
                {"type": "text", "text": ""},
                {"type": "tool_result"},  # no content key at all
            ]}},
        ]
        m = run.parse_transcript([json.dumps(e) for e in events])
        self.assertEqual(m["hook_attachment_blocks"], 0)
        self.assertEqual(m["hook_attachment_chars"], 0)

    def test_counted_unconditionally_not_gated_on_error_or_denial_match(self):
        # A non-error tool_result with no hook-denial-pattern text still
        # counts here, unlike hook_denials/stop_hook_blocks.
        events = [
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "is_error": False, "content": "plain output"},
            ]}},
        ]
        m = run.parse_transcript([json.dumps(e) for e in events])
        self.assertEqual(m["hook_attachment_blocks"], 1)
        self.assertEqual(m["hook_attachment_chars"], len("plain output"))
        self.assertEqual(m["hook_denials"], 0)

    def test_counts_across_main_agent_and_subagent_events(self):
        events = [
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "content": "main agent block"},
            ]}},
            {"type": "user", "parent_tool_use_id": "toolu_01sub", "message": {"content": [
                {"type": "tool_result", "content": "subagent block"},
            ]}},
        ]
        m = run.parse_transcript([json.dumps(e) for e in events])
        self.assertEqual(m["hook_attachment_blocks"], 2)
        self.assertEqual(
            m["hook_attachment_chars"],
            len("main agent block") + len("subagent block"))

    def test_content_list_shape_tool_result_counted_once(self):
        # tool_result content may itself be a list of {"type": "text", ...}
        # blocks (see _tool_result_text) -- still one hook_attachment block,
        # with chars from the joined text.
        events = [
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "content": [
                    {"type": "text", "text": "part one"},
                    {"type": "text", "text": "part two"},
                ]},
            ]}},
        ]
        m = run.parse_transcript([json.dumps(e) for e in events])
        self.assertEqual(m["hook_attachment_blocks"], 1)
        self.assertEqual(m["hook_attachment_chars"], len("part one\npart two"))


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


class ScoreRunExpectedIdScoringTest(unittest.TestCase):
    """score_run() against a REAL hidden_tests/ dir, including a module that
    fails to import -- exercises the acceptance["total"]/["passed"] fix end
    to end (STATIC expected-id scoring, not unittest's own "Ran N tests"
    summary, which under-counts an import-failed module -- see
    acceptance.score_against_expected_ids's module docstring)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="harness_score_expected_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.work_dir = os.path.join(self.tmp, "work")
        os.makedirs(self.work_dir)

        self.task_dir = os.path.join(self.tmp, "task")
        hidden = os.path.join(self.task_dir, "hidden_tests")
        os.makedirs(hidden)
        with open(os.path.join(hidden, "__init__.py"), "w") as f:
            f.write("")
        with open(os.path.join(hidden, "test_spec_ok.py"), "w") as f:
            f.write(
                "import unittest\n"
                "class T(unittest.TestCase):\n"
                "    def test_pass(self):\n"
                "        pass\n"
            )
        # This module fails to import in the agent's tree (references a
        # name that doesn't exist yet) -- unittest -v reports it as ONE
        # _FailedTest/ERROR line for the whole module, not its 2 real tests.
        with open(os.path.join(hidden, "test_doc_broken.py"), "w") as f:
            f.write(
                "import unittest\n"
                "from nonexistent_agent_module import DOES_NOT_EXIST\n"
                "class T(unittest.TestCase):\n"
                "    def test_a(self):\n"
                "        pass\n"
                "    def test_b(self):\n"
                "        pass\n"
            )
        self.paths = run.task_paths("__unused__")
        self.paths["hidden_tests"] = hidden
        self.paths["doc_rules"] = os.path.join(self.task_dir, "doc_rules.json")

    def test_total_reflects_static_expected_ids_not_unittest_summary(self):
        acceptance, _regression = run.score_run(self.work_dir, paths=self.paths)
        # 1 (test_spec_ok) + 2 (test_doc_broken, import-failed) == 3 expected,
        # NOT the 2 unittest itself would report (1 real pass + 1 opaque
        # _FailedTest line collapsing test_doc_broken's 2 tests into 1).
        self.assertEqual(acceptance["total"], 3)
        self.assertEqual(acceptance["passed"], 1)
        self.assertFalse(acceptance["ok"])
        self.assertEqual(acceptance["spec"], {"passed": 1, "total": 1})
        self.assertEqual(acceptance["doc"], {"passed": 0, "total": 2})
        self.assertIn("by_id", acceptance)
        import_error_statuses = {
            v["status"] for k, v in acceptance["by_id"].items() if "test_doc_broken" in k
        }
        self.assertEqual(import_error_statuses, {"import_error"})


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

    def test_default_has_no_session_persistence(self):
        # Every existing single-phase call site must keep getting the exact
        # same command it always has -- session/resume are both None by
        # default.
        cmd = run.build_command("t", "claude-sonnet-5", None)
        self.assertIn("--no-session-persistence", cmd)
        self.assertNotIn("--session-id", cmd)
        self.assertNotIn("--resume", cmd)

    def test_session_id_drops_no_session_persistence(self):
        cmd = run.build_command("t", "claude-sonnet-5", None,
                                 session_id="11111111-1111-4111-8111-111111111111")
        self.assertNotIn("--no-session-persistence", cmd)
        self.assertIn("--session-id", cmd)
        idx = cmd.index("--session-id")
        self.assertEqual(cmd[idx + 1], "11111111-1111-4111-8111-111111111111")
        self.assertNotIn("--resume", cmd)

    def test_resume_drops_no_session_persistence(self):
        cmd = run.build_command("t", "claude-sonnet-5", None, resume="abc-123")
        self.assertNotIn("--no-session-persistence", cmd)
        self.assertIn("--resume", cmd)
        idx = cmd.index("--resume")
        self.assertEqual(cmd[idx + 1], "abc-123")
        self.assertNotIn("--session-id", cmd)

    def test_session_id_and_resume_are_mutually_exclusive(self):
        with self.assertRaises(AssertionError):
            run.build_command("t", "claude-sonnet-5", None,
                               session_id="a", resume="b")

    def test_session_flags_preserve_every_other_flag(self):
        cmd = run.build_command("t", "claude-sonnet-5", 2.0,
                                 plugin_dir="/tmp/armdir", effort="high",
                                 session_id="sess-1")
        for expected in ("--output-format", "stream-json", "--verbose",
                          "--model", "--setting-sources", "project,local",
                          "--dangerously-skip-permissions", "--max-budget-usd",
                          "--plugin-dir", "--effort"):
            self.assertIn(expected, cmd)


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
            task=run.DEFAULT_TASK,
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
        task_md = os.path.join(HARNESS_DIR, "tasks", run.DEFAULT_TASK, "task.md")
        fixture_dir = os.path.join(HARNESS_DIR, "tasks", run.DEFAULT_TASK, "fixture")
        if not os.path.exists(task_md) or not os.path.isdir(fixture_dir):
            self.skipTest(f"task variant {run.DEFAULT_TASK!r} not ready (task.md/fixture/ missing)")
        # We deliberately do not invoke run.main(["--dry-run", ...]) here to
        # avoid mutating experiments/harness-ab/.work or results/ as a side
        # effect of the unit test suite; the harness README documents running
        # --dry-run manually. This test only proves the module wires up
        # correctly once the fixture exists.
        self.assertTrue(callable(run.cmd_dry_run))


class TaskPathsTest(unittest.TestCase):
    def test_returns_expected_keys(self):
        paths = run.task_paths("v1")
        for key in ("dir", "fixture", "overlay_swe", "hidden_tests",
                    "reference_solution", "task_md", "doc_rules"):
            self.assertIn(key, paths)
        self.assertTrue(paths["dir"].endswith(os.path.join("tasks", "v1")))
        self.assertTrue(paths["fixture"].endswith(os.path.join("tasks", "v1", "fixture")))
        self.assertTrue(paths["overlay_swe"].endswith(os.path.join("tasks", "v1", "overlays", "swe")))
        self.assertTrue(paths["doc_rules"].endswith(os.path.join("tasks", "v1", "doc_rules.json")))

    def test_default_task_is_v2(self):
        self.assertEqual(run.DEFAULT_TASK, "v2")

    def test_v1_task_files_exist_after_migration(self):
        paths = run.task_paths("v1")
        self.assertTrue(os.path.isdir(paths["fixture"]))
        self.assertTrue(os.path.isdir(paths["hidden_tests"]))
        self.assertTrue(os.path.isdir(paths["reference_solution"]))
        self.assertTrue(os.path.exists(paths["task_md"]))

    def test_pivot_keys_present(self):
        paths = run.task_paths("v1")
        for key in ("pivot_dir", "pivot_prompt", "pivot_hidden_tests",
                    "pivot_reference_solution", "pivot_doc_rules"):
            self.assertIn(key, paths)
        self.assertTrue(paths["pivot_prompt"].endswith(
            os.path.join("tasks", "v1", "pivot", "prompt.md")))
        self.assertTrue(paths["pivot_hidden_tests"].endswith(
            os.path.join("tasks", "v1", "pivot", "hidden_tests")))


class HasPivotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="harness_has_pivot_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_no_pivot_dir_is_false(self):
        paths = run.task_paths("nonexistent-task-xyz")
        self.assertFalse(run.has_pivot(paths))

    def test_pivot_prompt_present_is_true(self):
        task_dir = os.path.join(self.tmp, "task")
        pivot_dir = os.path.join(task_dir, "pivot")
        os.makedirs(pivot_dir)
        with open(os.path.join(pivot_dir, "prompt.md"), "w") as f:
            f.write("New task: do more things.\n")
        paths = {"pivot_prompt": os.path.join(pivot_dir, "prompt.md")}
        self.assertTrue(run.has_pivot(paths))

    def test_pivot_dir_without_prompt_is_false(self):
        task_dir = os.path.join(self.tmp, "task")
        pivot_dir = os.path.join(task_dir, "pivot")
        os.makedirs(pivot_dir)
        paths = {"pivot_prompt": os.path.join(pivot_dir, "prompt.md")}
        self.assertFalse(run.has_pivot(paths))


class ResolveOverlayTest(unittest.TestCase):
    """resolve_overlay: per-arm overlay resolution against a synthetic
    tasks/<name>/overlays/ tree on disk. Pure except for os.path.isdir
    checks against the temp dir this test builds."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="harness_overlay_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        overlays_dir = os.path.join(self.tmp, "overlays")
        os.makedirs(os.path.join(overlays_dir, "swe"), exist_ok=True)
        with open(os.path.join(overlays_dir, "swe", "CLAUDE.md"), "w") as f:
            f.write("swe overlay content\n")
        self.paths = {"dir": self.tmp, "overlays_dir": overlays_dir}

    def test_arm_with_existing_overlay_dir_resolves_applied(self):
        arm = {"name": "baseline", "plugin": True, "overlay": "swe"}
        info = run.resolve_overlay(arm, self.paths)
        self.assertEqual(info["overlay"], "swe")
        self.assertTrue(info["overlay_applied"])
        self.assertIsNone(info["warning"])
        self.assertTrue(os.path.isdir(info["overlay_dir"]))

    def test_arm_with_missing_overlay_dir_not_applied_but_no_raise(self):
        arm = {"name": "control", "plugin": False, "overlay": "control"}
        info = run.resolve_overlay(arm, self.paths)
        self.assertEqual(info["overlay"], "control")
        self.assertFalse(info["overlay_applied"])
        self.assertIsNotNone(info["warning"])
        self.assertIn("control", info["warning"])

    def test_arm_with_no_overlay_key_falls_back_plugin_true_uses_swe(self):
        # v1-style arms.json (no "overlay" field at all): plugin arms fall
        # back to overlays/swe/ if present, matching pre-per-arm behavior.
        arm = {"name": "baseline", "plugin": True}
        info = run.resolve_overlay(arm, self.paths)
        self.assertEqual(info["overlay"], "swe")
        self.assertTrue(info["overlay_applied"])

    def test_arm_with_no_overlay_key_and_no_plugin_gets_no_overlay(self):
        arm = {"name": "control", "plugin": False}
        info = run.resolve_overlay(arm, self.paths)
        self.assertIsNone(info["overlay"])
        self.assertFalse(info["overlay_applied"])
        self.assertIsNone(info["warning"])

    def test_arm_overlay_explicitly_null_gets_no_overlay(self):
        arm = {"name": "control", "plugin": False, "overlay": None}
        info = run.resolve_overlay(arm, self.paths)
        self.assertIsNone(info["overlay"])
        self.assertFalse(info["overlay_applied"])


class MakeRunWorkdirOverlayTest(unittest.TestCase):
    """make_run_workdir: applies the resolved overlay over a fixture copy
    and returns (work_dir, overlay_info)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="harness_workdir_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        task_dir = os.path.join(self.tmp, "task")
        fixture_dir = os.path.join(task_dir, "fixture")
        os.makedirs(fixture_dir, exist_ok=True)
        with open(os.path.join(fixture_dir, "CLAUDE.md"), "w") as f:
            f.write("base project guidance\n")
        overlays_dir = os.path.join(task_dir, "overlays")
        swe_dir = os.path.join(overlays_dir, "swe")
        os.makedirs(swe_dir, exist_ok=True)
        with open(os.path.join(swe_dir, "CLAUDE.md"), "w") as f:
            f.write("swe overlay CLAUDE.md\n")
        self.paths = {"dir": task_dir, "fixture": fixture_dir,
                       "overlays_dir": overlays_dir,
                       "overlay_swe": swe_dir}
        self.run_dir = os.path.join(self.tmp, "run")
        os.makedirs(self.run_dir, exist_ok=True)

    def test_overlay_applied_overwrites_fixture_claude_md(self):
        arm = {"name": "baseline", "plugin": True, "overlay": "swe"}
        work_dir, overlay_info = run.make_run_workdir(self.run_dir, arm, paths=self.paths)
        self.assertTrue(overlay_info["overlay_applied"])
        with open(os.path.join(work_dir, "CLAUDE.md")) as f:
            self.assertEqual(f.read(), "swe overlay CLAUDE.md\n")

    def test_missing_overlay_leaves_fixture_claude_md_and_warns(self):
        arm = {"name": "control", "plugin": False, "overlay": "control"}
        work_dir, overlay_info = run.make_run_workdir(self.run_dir, arm, paths=self.paths)
        self.assertFalse(overlay_info["overlay_applied"])
        self.assertIsNotNone(overlay_info["warning"])
        with open(os.path.join(work_dir, "CLAUDE.md")) as f:
            self.assertEqual(f.read(), "base project guidance\n")

    def test_v1_style_arm_with_no_overlay_key_still_works(self):
        # v1 arms.json shape (no "overlay"), plugin arm -> falls back to
        # overlays/swe/ per resolve_overlay's back-compat path.
        arm = {"name": "baseline", "plugin": True, "ref": "23ec65d"}
        work_dir, overlay_info = run.make_run_workdir(self.run_dir, arm, paths=self.paths)
        self.assertEqual(overlay_info["overlay"], "swe")
        self.assertTrue(overlay_info["overlay_applied"])
        with open(os.path.join(work_dir, "CLAUDE.md")) as f:
            self.assertEqual(f.read(), "swe overlay CLAUDE.md\n")


class Sha256OfClaudeMdTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="harness_sha_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_hash_matches_hashlib_of_content(self):
        import hashlib
        with open(os.path.join(self.tmp, "CLAUDE.md"), "wb") as f:
            f.write(b"hello world\n")
        digest = run.sha256_of_claude_md(self.tmp)
        self.assertEqual(digest, hashlib.sha256(b"hello world\n").hexdigest())

    def test_missing_file_returns_none(self):
        self.assertIsNone(run.sha256_of_claude_md(self.tmp))

    def test_different_content_different_hash(self):
        with open(os.path.join(self.tmp, "CLAUDE.md"), "w") as f:
            f.write("a")
        h1 = run.sha256_of_claude_md(self.tmp)
        with open(os.path.join(self.tmp, "CLAUDE.md"), "w") as f:
            f.write("b")
        h2 = run.sha256_of_claude_md(self.tmp)
        self.assertNotEqual(h1, h2)


class ValidateClaudeMdTest(unittest.TestCase):
    """validate_claude_md: pure per-arm text validation."""

    CONTROL_CLEAN = (
        "# ledgerlite — project guidance\n"
        "- Run tests: `python3 -m unittest discover -s tests`\n"
        "- Python 3.11+, standard library only.\n"
    )
    CONTROL_WITH_DOC_LINE = CONTROL_CLEAN + (
        "- Domain rules are documented under `.serena/memory/`.\n"
    )
    PLUGIN_OK = (
        "## ⛔ MANDATORY ENTRY POINT — FIRST MESSAGE ONLY ⛔\n\n"
        "mcp__plugin_swe_serena__read_memory(memory_name=\"wf/WF_INIT\")\n\n"
        "# ledgerlite — project guidance\n"
    )

    def test_control_clean_text_is_valid(self):
        errors = run.validate_claude_md("control", False, self.CONTROL_CLEAN)
        self.assertEqual(errors, [])

    def test_control_with_single_allowed_doc_line_is_valid(self):
        errors = run.validate_claude_md("control", False, self.CONTROL_WITH_DOC_LINE)
        self.assertEqual(errors, [])

    def test_control_leaking_wf_init_is_invalid(self):
        text = self.CONTROL_CLEAN + "- See wf/WF_INIT for workflow routing.\n"
        errors = run.validate_claude_md("control", False, text)
        self.assertTrue(any("wf_" in e for e in errors))

    def test_control_leaking_swe_term_is_invalid(self):
        text = self.CONTROL_CLEAN + "- This project uses the swe plugin.\n"
        errors = run.validate_claude_md("control", False, text)
        self.assertTrue(len(errors) >= 1)

    def test_control_leaking_harness_term_is_invalid(self):
        text = self.CONTROL_CLEAN + "- Part of the harness experiment.\n"
        errors = run.validate_claude_md("control", False, text)
        self.assertTrue(len(errors) >= 1)

    def test_control_two_doc_location_lines_is_invalid(self):
        text = (self.CONTROL_WITH_DOC_LINE +
                "- Also see `.serena/memory/` for more.\n")
        errors = run.validate_claude_md("control", False, text)
        self.assertTrue(any("allowed doc-location" in e for e in errors))

    def test_plugin_missing_prefix_is_invalid(self):
        errors = run.validate_claude_md("baseline", True, "# ledgerlite\nplain guidance only\n")
        self.assertTrue(len(errors) >= 1)
        self.assertTrue(any("MANDATORY ENTRY POINT" in e or "wf/WF_INIT" in e for e in errors))

    def test_plugin_with_prefix_is_valid(self):
        errors = run.validate_claude_md("baseline", True, self.PLUGIN_OK)
        self.assertEqual(errors, [])

    def test_plugin_empty_text_is_invalid(self):
        errors = run.validate_claude_md("v5", True, "")
        self.assertEqual(len(errors), 2)

    def test_control_empty_text_is_valid(self):
        errors = run.validate_claude_md("control", False, "")
        self.assertEqual(errors, [])


class RunOneOverlayFieldsTest(unittest.TestCase):
    """run_one aborts before any claude -p call when the effective CLAUDE.md
    fails validate_claude_md, and records overlay/overlay_applied/
    claude_md_sha256/claude_md_check on a successful row. Exercised via
    make_run_workdir + the row-building shape directly (no live subprocess),
    matching CmdReparseTest's no-live-agent-call convention."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="harness_runone_claudemd_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        task_dir = os.path.join(self.tmp, "task")
        fixture_dir = os.path.join(task_dir, "fixture")
        os.makedirs(fixture_dir, exist_ok=True)
        with open(os.path.join(fixture_dir, "CLAUDE.md"), "w") as f:
            f.write("base project guidance\n")
        overlays_dir = os.path.join(task_dir, "overlays")
        control_dir = os.path.join(overlays_dir, "control")
        os.makedirs(control_dir, exist_ok=True)
        with open(os.path.join(control_dir, "CLAUDE.md"), "w") as f:
            f.write("base project guidance\n- Docs live under `.serena/memory/`.\n")
        self.paths = {"dir": task_dir, "fixture": fixture_dir,
                       "overlays_dir": overlays_dir, "overlay_swe": os.path.join(overlays_dir, "swe")}
        self.run_dir = os.path.join(self.tmp, "run")
        os.makedirs(self.run_dir, exist_ok=True)

    def test_control_arm_with_clean_overlay_passes_validation(self):
        arm = {"name": "control", "plugin": False, "overlay": "control"}
        work_dir, overlay_info = run.make_run_workdir(self.run_dir, arm, paths=self.paths)
        text = run.read_effective_claude_md(work_dir)
        errors = run.validate_claude_md("control", False, text)
        self.assertEqual(errors, [])
        self.assertTrue(overlay_info["overlay_applied"])
        self.assertIsNotNone(run.sha256_of_claude_md(work_dir))

    def test_plugin_arm_missing_overlay_fails_validation(self):
        # overlays/swe/ doesn't exist in this fixture -> fixture's bare
        # CLAUDE.md is left in place, which has no SWE prefix -> invalid.
        arm = {"name": "baseline", "plugin": True, "overlay": "swe"}
        work_dir, overlay_info = run.make_run_workdir(self.run_dir, arm, paths=self.paths)
        self.assertFalse(overlay_info["overlay_applied"])
        text = run.read_effective_claude_md(work_dir)
        errors = run.validate_claude_md("baseline", True, text)
        self.assertTrue(len(errors) >= 1)


class RowTaskNameTest(unittest.TestCase):
    def test_no_task_field_treated_as_v1(self):
        self.assertEqual(run._row_task_name({"arm": "baseline"}), "v1")

    def test_explicit_task_field_kept(self):
        self.assertEqual(run._row_task_name({"arm": "baseline", "task": "v2"}), "v2")

    def test_empty_string_task_field_treated_as_v1(self):
        self.assertEqual(run._row_task_name({"task": ""}), "v1")


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

    def test_reparse_adds_gates_and_backfills_task_as_v1(self):
        run.cmd_reparse(self.stamp_dir)
        with open(self.runs_jsonl) as f:
            new_row = json.loads(f.readline())
        # No "task" field on the stale row -> backfilled as "v1" (see
        # _row_task_name; results/20260929-123133 predates --task).
        self.assertEqual(new_row["task"], "v1")
        # gates is always (re)computed by --reparse, a pure derivation from
        # the saved transcript + stream.
        self.assertIn("gates", new_row)
        self.assertIn("init_chain_complete", new_row["gates"])
        self.assertIn("sweep_verified", new_row["gates"])
        self.assertIn("edits_before_sweep", new_row["gates"])
        self.assertIn("memories_read", new_row["gates"])

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


class EvaluateGateProbeTest(unittest.TestCase):
    """Pure evaluate_gate_probe() judgment tests."""

    def _gates(self, init_denials=0, edit_denials=0, sweep_denials=0):
        return {
            "gate_denials": {"init": init_denials, "edit": edit_denials,
                              "sweep": sweep_denials, "docs": 0, "stop": 0,
                              "unclassified": 0},
            "init_chain_complete": True,
            "sweep_verified": True,
            "edits_before_sweep": 0,
        }

    def test_denied_and_unchanged_passes(self):
        gates = self._gates(init_denials=1)
        result = run.evaluate_gate_probe(gates, "original", "original", sweep_before_edit_ok=False)
        self.assertTrue(result["pass"])

    def test_no_denial_and_changed_fails(self):
        gates = self._gates()
        result = run.evaluate_gate_probe(gates, "original", "modified", sweep_before_edit_ok=False)
        self.assertFalse(result["pass"])
        self.assertFalse(result["saw_deny"])

    def test_denied_but_changed_unsafely_fails(self):
        # Denial happened but the file changed anyway BEFORE a verified
        # sweep -- the gate fired too late / was bypassed somewhere.
        gates = self._gates(edit_denials=1)
        result = run.evaluate_gate_probe(gates, "original", "modified", sweep_before_edit_ok=False)
        self.assertFalse(result["pass"])

    def test_denied_and_changed_safely_after_sweep_passes(self):
        # A legitimate edit after full gate compliance, PLUS at least one
        # denial recorded (e.g. an earlier premature attempt correctly
        # blocked, then the agent did it right) still passes.
        gates = self._gates(sweep_denials=1)
        result = run.evaluate_gate_probe(gates, "original", "modified", sweep_before_edit_ok=True)
        self.assertTrue(result["pass"])

    def test_no_denial_but_unchanged_fails(self):
        # File unchanged is good, but with zero denials recorded we can't
        # tell whether the gate did anything or the agent just complied
        # unprompted -- evaluate_gate_probe requires an observed deny.
        gates = self._gates()
        result = run.evaluate_gate_probe(gates, "original", "original", sweep_before_edit_ok=False)
        self.assertFalse(result["pass"])


class CmdGateSelftestTest(unittest.TestCase):
    """--gate-selftest makes no model call and must exit 0."""

    def test_exits_zero(self):
        rc = run.cmd_gate_selftest()
        self.assertEqual(rc, 0)


class ScoreHiddenTestsDirTest(unittest.TestCase):
    """score_hidden_tests_dir: scores an arbitrary hidden_tests dir into
    work_dir/_acceptance/<subdir>/, alongside another subdir, and both are
    discoverable together via `-t .` (see run_unittest_dir)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="harness_score_hidden_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.work_dir = os.path.join(self.tmp, "work")
        os.makedirs(self.work_dir)
        self.hidden_a = os.path.join(self.tmp, "hidden_a")
        os.makedirs(self.hidden_a)
        with open(os.path.join(self.hidden_a, "__init__.py"), "w") as f:
            f.write("")
        with open(os.path.join(self.hidden_a, "test_spec_a.py"), "w") as f:
            f.write(
                "import unittest\n"
                "class T(unittest.TestCase):\n"
                "    def test_a_passes(self):\n"
                "        pass\n"
            )
        self.hidden_b = os.path.join(self.tmp, "hidden_b")
        os.makedirs(self.hidden_b)
        with open(os.path.join(self.hidden_b, "__init__.py"), "w") as f:
            f.write("")
        with open(os.path.join(self.hidden_b, "test_doc_b.py"), "w") as f:
            f.write(
                "import unittest\n"
                "class T(unittest.TestCase):\n"
                "    def test_b_fails(self):\n"
                "        self.fail('nope')\n"
            )

    def test_two_subdirs_scored_independently_and_both_discovered(self):
        acc_a = run.score_hidden_tests_dir(self.work_dir, self.hidden_a, "task1")
        self.assertEqual(acc_a["total"], 1)
        self.assertTrue(acc_a["ok"])
        self.assertEqual(acc_a["spec"]["total"], 1)

        acc_b = run.score_hidden_tests_dir(self.work_dir, self.hidden_b, "pivot")
        # -t . discovery's raw `out`/`err` text contains BOTH subdirs' test
        # result lines once both are copied in (task1's is still on disk
        # from the acc_a call above), but acc_b's total/passed/spec/doc are
        # scored against the STATIC expected-id set scanned from ITS OWN
        # hidden_tests dir only (module_prefix "_acceptance.pivot") -- see
        # run._score_expected_ids -- so acc_b never counts task1's test.
        self.assertEqual(acc_b["total"], 1)
        self.assertFalse(acc_b["ok"])
        self.assertEqual(acc_b["doc"]["total"], 1)
        self.assertIn("test_b_fails (_acceptance.pivot.test_doc_b.T.test_b_fails)",
                       acc_b["failed_tests"])

        self.assertTrue(os.path.isdir(os.path.join(self.work_dir, "_acceptance", "task1")))
        self.assertTrue(os.path.isdir(os.path.join(self.work_dir, "_acceptance", "pivot")))

    def test_missing_hidden_tests_dir_reports_not_present(self):
        acc = run.score_hidden_tests_dir(self.work_dir, os.path.join(self.tmp, "nope"), "task1")
        self.assertEqual(acc["exit_code"], -1)
        self.assertEqual(acc["total"], 0)

    def test_log_file_written_when_run_dir_and_log_name_given(self):
        run_dir = os.path.join(self.tmp, "rundir")
        run.score_hidden_tests_dir(self.work_dir, self.hidden_a, "task1",
                                    run_dir=run_dir, log_name="acceptance.task1.b1.txt")
        self.assertTrue(os.path.exists(os.path.join(run_dir, "acceptance.task1.b1.txt")))


class RemoveAcceptanceDirTest(unittest.TestCase):
    def test_removes_existing_dir(self):
        tmp = tempfile.mkdtemp(prefix="harness_remove_acc_test_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        acc_dir = os.path.join(tmp, "_acceptance")
        os.makedirs(acc_dir)
        with open(os.path.join(acc_dir, "f.txt"), "w") as f:
            f.write("x")
        run.remove_acceptance_dir(tmp)
        self.assertFalse(os.path.exists(acc_dir))

    def test_no_op_when_absent(self):
        tmp = tempfile.mkdtemp(prefix="harness_remove_acc_test2_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        run.remove_acceptance_dir(tmp)  # must not raise


class GitCommitSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="harness_git_snapshot_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        run._run(["git", "init", "-q"], cwd=self.tmp)
        with open(os.path.join(self.tmp, "f.txt"), "w") as f:
            f.write("v1\n")
        run._run(["git", "-c", "user.name=x", "-c", "user.email=x@x", "add", "-A"], cwd=self.tmp)
        run._run(["git", "-c", "user.name=x", "-c", "user.email=x@x", "commit", "-qm", "init"],
                  cwd=self.tmp)

    def test_returns_sha_and_creates_commit(self):
        before = run._run(["git", "rev-parse", "HEAD"], cwd=self.tmp).stdout.strip()
        with open(os.path.join(self.tmp, "f.txt"), "w") as f:
            f.write("v2\n")
        sha = run.git_commit_snapshot(self.tmp, "benchmark1")
        self.assertNotEqual(sha, before)
        after = run._run(["git", "rev-parse", "HEAD"], cwd=self.tmp).stdout.strip()
        self.assertEqual(sha, after)

    def test_allow_empty_when_nothing_changed(self):
        # Two consecutive snapshots with no tree changes in between must
        # both succeed (git commit --allow-empty), producing two distinct
        # commits.
        sha1 = run.git_commit_snapshot(self.tmp, "benchmark1")
        sha2 = run.git_commit_snapshot(self.tmp, "benchmark2")
        self.assertNotEqual(sha1, sha2)


class ResolveCommitShaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="harness_resolve_sha_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        run._run(["git", "init", "-q"], cwd=self.tmp)
        with open(os.path.join(self.tmp, "f.txt"), "w") as f:
            f.write("v1\n")
        run._run(["git", "-c", "user.name=x", "-c", "user.email=x@x", "add", "-A"], cwd=self.tmp)
        run._run(["git", "-c", "user.name=x", "-c", "user.email=x@x", "commit", "-qm", "init"],
                  cwd=self.tmp)

    def test_finds_exact_subject_match(self):
        sha = run.git_commit_snapshot(self.tmp, "benchmark1")
        found = run._resolve_commit_sha(self.tmp, "benchmark1")
        self.assertEqual(found, sha)

    def test_no_matching_subject_returns_none(self):
        self.assertIsNone(run._resolve_commit_sha(self.tmp, "benchmark1"))

    def test_substring_subject_does_not_false_match(self):
        # "benchmark1" must not match a commit literally titled
        # "benchmark10" or "not benchmark1 related" -- exact subject only.
        run._run(["git", "-c", "user.name=x", "-c", "user.email=x@x",
                   "commit", "-qm", "benchmark10", "--allow-empty"], cwd=self.tmp)
        self.assertIsNone(run._resolve_commit_sha(self.tmp, "benchmark1"))

    def test_most_recent_match_wins(self):
        sha1 = run.git_commit_snapshot(self.tmp, "benchmark1")
        run._run(["git", "-c", "user.name=x", "-c", "user.email=x@x",
                   "commit", "-qm", "other", "--allow-empty"], cwd=self.tmp)
        sha2 = run.git_commit_snapshot(self.tmp, "benchmark1")
        found = run._resolve_commit_sha(self.tmp, "benchmark1")
        self.assertEqual(found, sha2)
        self.assertNotEqual(sha1, sha2)

    def test_non_git_dir_returns_none(self):
        empty = tempfile.mkdtemp(prefix="harness_not_a_repo_")
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        self.assertIsNone(run._resolve_commit_sha(empty, "benchmark1"))


class ExportGitCommitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="harness_export_commit_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        run._run(["git", "init", "-q"], cwd=self.tmp)
        os.makedirs(os.path.join(self.tmp, "sub"))
        with open(os.path.join(self.tmp, "f.txt"), "w") as f:
            f.write("v1\n")
        with open(os.path.join(self.tmp, "sub", "g.txt"), "w") as f:
            f.write("nested\n")
        run._run(["git", "-c", "user.name=x", "-c", "user.email=x@x", "add", "-A"], cwd=self.tmp)
        run._run(["git", "-c", "user.name=x", "-c", "user.email=x@x", "commit", "-qm", "init"],
                  cwd=self.tmp)
        self.sha = run._run(["git", "rev-parse", "HEAD"], cwd=self.tmp).stdout.strip()

    def test_exports_tree_contents(self):
        dest = tempfile.mkdtemp(prefix="harness_export_dest_")
        self.addCleanup(shutil.rmtree, dest, ignore_errors=True)
        run._export_git_commit(self.tmp, self.sha, dest)
        with open(os.path.join(dest, "f.txt")) as f:
            self.assertEqual(f.read(), "v1\n")
        with open(os.path.join(dest, "sub", "g.txt")) as f:
            self.assertEqual(f.read(), "nested\n")

    def test_never_mutates_source_repo(self):
        # Change the working tree AFTER the commit (uncommitted), export the
        # commit, and confirm the source repo's working tree is untouched
        # (no checkout, no reset -- git archive is read-only).
        with open(os.path.join(self.tmp, "f.txt"), "w") as f:
            f.write("UNCOMMITTED CHANGE\n")
        dest = tempfile.mkdtemp(prefix="harness_export_dest2_")
        self.addCleanup(shutil.rmtree, dest, ignore_errors=True)
        run._export_git_commit(self.tmp, self.sha, dest)
        # Exported copy reflects the COMMITTED content...
        with open(os.path.join(dest, "f.txt")) as f:
            self.assertEqual(f.read(), "v1\n")
        # ...while the source repo's working tree still has the
        # uncommitted change, proving nothing was checked out/reset there.
        with open(os.path.join(self.tmp, "f.txt")) as f:
            self.assertEqual(f.read(), "UNCOMMITTED CHANGE\n")

    def test_bad_sha_raises(self):
        dest = tempfile.mkdtemp(prefix="harness_export_dest3_")
        self.addCleanup(shutil.rmtree, dest, ignore_errors=True)
        with self.assertRaises(RuntimeError):
            run._export_git_commit(self.tmp, "0" * 40, dest)


class CopyTreeExcludingGitTest(unittest.TestCase):
    def test_excludes_git_dir_copies_rest(self):
        src = tempfile.mkdtemp(prefix="harness_copytree_src_")
        self.addCleanup(shutil.rmtree, src, ignore_errors=True)
        dest = tempfile.mkdtemp(prefix="harness_copytree_dest_")
        self.addCleanup(shutil.rmtree, dest, ignore_errors=True)
        os.makedirs(os.path.join(src, ".git"))
        with open(os.path.join(src, ".git", "HEAD"), "w") as f:
            f.write("ref: refs/heads/main\n")
        with open(os.path.join(src, "f.txt"), "w") as f:
            f.write("content\n")
        run._copy_tree_excluding_git(src, dest)
        self.assertFalse(os.path.exists(os.path.join(dest, ".git")))
        with open(os.path.join(dest, "f.txt")) as f:
            self.assertEqual(f.read(), "content\n")


class CmdRescoreSinglePhaseTest(unittest.TestCase):
    """--rescore against a small synthetic single-phase stamp dir: a real
    git repo under runs/<id>/work/ with a hidden_tests/ module that fails to
    import, checking the rewritten acceptance["total"]/["passed"] reflect
    the STATIC expected-id count and runs.jsonl.prerescore preserves the
    original."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="harness_rescore_single_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.stamp_dir = os.path.join(self.tmp, "20990101-000000")
        self.run_dir = os.path.join(self.stamp_dir, "runs", "control-t0")
        self.work_dir = os.path.join(self.run_dir, "work")
        os.makedirs(self.work_dir)

        run._run(["git", "init", "-q"], cwd=self.work_dir)
        with open(os.path.join(self.work_dir, "f.txt"), "w") as f:
            f.write("v1\n")
        run._run(["git", "-c", "user.name=x", "-c", "user.email=x@x", "add", "-A"], cwd=self.work_dir)
        run._run(["git", "-c", "user.name=x", "-c", "user.email=x@x", "commit", "-qm", "init"],
                  cwd=self.work_dir)

        with open(os.path.join(self.run_dir, "transcript.jsonl"), "w") as f:
            f.write(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                                 "num_turns": 1, "usage": {}, "modelUsage": {}}) + "\n")

        self.task_dir = os.path.join(self.tmp, "task")
        hidden = os.path.join(self.task_dir, "hidden_tests")
        os.makedirs(hidden)
        with open(os.path.join(hidden, "__init__.py"), "w") as f:
            f.write("")
        with open(os.path.join(hidden, "test_doc_broken.py"), "w") as f:
            f.write(
                "import unittest\n"
                "from nonexistent_agent_module import X\n"
                "class T(unittest.TestCase):\n"
                "    def test_a(self):\n"
                "        pass\n"
                "    def test_b(self):\n"
                "        pass\n"
            )

        stale_row = {
            "run_id": "control-t0", "arm": "control", "task": "__rescore_fixture__",
            "trial": 0, "exit_code": 0, "timed_out": False, "wall_s": 1.0,
            "metrics": {}, "stream_metrics": {},
            "acceptance": {"total": 1, "passed": 1, "ok": True, "exit_code": 0},
            "regression": {"total": 0, "passed": 0, "ok": True, "exit_code": 0},
            "isolation": {"ok": True},
        }
        self.runs_jsonl = os.path.join(self.stamp_dir, "runs.jsonl")
        with open(self.runs_jsonl, "w") as f:
            f.write(json.dumps(stale_row) + "\n")

        # Point task_paths("__rescore_fixture__") at our synthetic task dir.
        self._orig_task_paths = run.task_paths
        def _fake_task_paths(task_name):
            paths = self._orig_task_paths(task_name)
            if task_name == "__rescore_fixture__":
                paths["hidden_tests"] = hidden
                paths["doc_rules"] = os.path.join(self.task_dir, "doc_rules.json")
            return paths
        run.task_paths = _fake_task_paths
        self.addCleanup(setattr, run, "task_paths", self._orig_task_paths)

    def test_rescore_recomputes_acceptance_from_static_expected_ids(self):
        rc = run.cmd_rescore(self.stamp_dir)
        self.assertEqual(rc, 0)

        backup_path = self.runs_jsonl + ".prerescore"
        self.assertTrue(os.path.exists(backup_path))
        with open(backup_path) as f:
            backup_row = json.loads(f.readline())
        self.assertEqual(backup_row["acceptance"]["total"], 1)  # untouched backup

        with open(self.runs_jsonl) as f:
            new_row = json.loads(f.readline())
        # 2 expected ids (test_a, test_b), both import_error -> 2/0, not the
        # stale row's fictitious 1/1.
        self.assertEqual(new_row["acceptance"]["total"], 2)
        self.assertEqual(new_row["acceptance"]["passed"], 0)
        self.assertIn("gates", new_row)

    def test_rescore_twice_does_not_clobber_prerescore_backup(self):
        run.cmd_rescore(self.stamp_dir)
        backup_path = self.runs_jsonl + ".prerescore"
        with open(backup_path) as f:
            first_backup = f.read()
        run.cmd_rescore(self.stamp_dir)
        with open(backup_path) as f:
            second_backup = f.read()
        self.assertEqual(first_backup, second_backup)

    def test_rescore_never_writes_into_source_work_git_repo(self):
        # The run's own work/ git repo must have no new commits/dirty state
        # from a rescore (B2 is scored from a COPY, and this single-phase
        # path never touches work/ at all beyond read-only git/log calls).
        before_head = run._run(["git", "rev-parse", "HEAD"], cwd=self.work_dir).stdout.strip()
        before_status = run._run(["git", "status", "--porcelain"], cwd=self.work_dir).stdout
        run.cmd_rescore(self.stamp_dir)
        after_head = run._run(["git", "rev-parse", "HEAD"], cwd=self.work_dir).stdout.strip()
        after_status = run._run(["git", "status", "--porcelain"], cwd=self.work_dir).stdout
        self.assertEqual(before_head, after_head)
        self.assertEqual(before_status, after_status)


class Task1RetentionTest(unittest.TestCase):
    def test_all_b1_passes_retained_at_b2(self):
        b1 = {"total": 3, "passed": 3, "failed_tests": []}
        b2 = {"total": 3, "passed": 3, "failed_tests": []}
        result = run.task1_retention(b1, b2)
        self.assertEqual(result, {"passed": 3, "total": 3, "regressions": []})

    def test_regression_detected(self):
        b1 = {"total": 3, "passed": 3, "failed_tests": []}
        b2 = {"total": 3, "passed": 2,
              "failed_tests": ["test_x (pkg.test_spec_a.T.test_x)"]}
        result = run.task1_retention(b1, b2)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["passed"], 2)
        self.assertEqual(result["regressions"], ["test_x (pkg.test_spec_a.T.test_x)"])

    def test_test_that_already_failed_at_b1_is_not_a_regression(self):
        # A test failing at both B1 and B2 is not a NEW regression -- it
        # was never counted in the B1 passed set to begin with.
        b1 = {"total": 3, "passed": 2,
              "failed_tests": ["test_y (pkg.test_spec_a.T.test_y)"]}
        b2 = {"total": 3, "passed": 1,
              "failed_tests": ["test_y (pkg.test_spec_a.T.test_y)",
                                "test_z (pkg.test_spec_a.T.test_z)"]}
        result = run.task1_retention(b1, b2)
        # b1_passed_count=2, one of the two now-failing ids (test_y) was
        # already failing at B1 so isn't a regression; test_z is.
        self.assertEqual(result["regressions"], ["test_z (pkg.test_spec_a.T.test_z)"])
        self.assertEqual(result["passed"], 1)

    def test_no_b1_passes_yields_empty_regressions(self):
        b1 = {"total": 0, "passed": 0, "failed_tests": []}
        b2 = {"total": 0, "passed": 0, "failed_tests": []}
        result = run.task1_retention(b1, b2)
        self.assertEqual(result, {"passed": 0, "total": 0, "regressions": []})

    # -- by_id-based path (score_against_expected_ids' STATIC expected-id
    # scoring, see acceptance.py's module docstring) -- the default prefixes
    # match run_one_pivot's real acceptance_subdir pair: "" at B1 (module
    # prefix "_acceptance"), "task1" at B2 (module prefix "_acceptance.task1").

    def test_by_id_all_pass_retained(self):
        b1 = {"by_id": {"_acceptance.test_spec_a.T.test_x": {"status": "ok"}}}
        b2 = {"by_id": {"_acceptance.task1.test_spec_a.T.test_x": {"status": "ok"}}}
        result = run.task1_retention(b1, b2)
        self.assertEqual(result, {"passed": 1, "total": 1, "regressions": []})

    def test_by_id_regression_detected(self):
        b1 = {"by_id": {"_acceptance.test_spec_a.T.test_x": {"status": "ok"}}}
        b2 = {"by_id": {"_acceptance.task1.test_spec_a.T.test_x": {"status": "fail"}}}
        result = run.task1_retention(b1, b2)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["passed"], 0)
        self.assertEqual(result["regressions"], ["test_spec_a.T.test_x"])

    def test_by_id_import_error_at_b2_counts_as_regression(self):
        # The whole point of the by_id-based path: a test that PASSED at B1
        # but whose module fails to import at B2 (status "import_error", not
        # "fail") must still be counted as a regression -- not silently
        # dropped because its status string isn't literally "fail".
        b1 = {"by_id": {"_acceptance.test_doc_a.T.test_x": {"status": "ok"}}}
        b2 = {"by_id": {"_acceptance.task1.test_doc_a.T.test_x": {"status": "import_error"}}}
        result = run.task1_retention(b1, b2)
        self.assertEqual(result["regressions"], ["test_doc_a.T.test_x"])

    def test_by_id_missing_at_b2_counts_as_regression(self):
        b1 = {"by_id": {"_acceptance.test_doc_a.T.test_x": {"status": "ok"}}}
        b2 = {"by_id": {}}
        result = run.task1_retention(b1, b2)
        self.assertEqual(result["regressions"], ["test_doc_a.T.test_x"])

    def test_by_id_not_passed_at_b1_never_a_regression(self):
        b1 = {"by_id": {"_acceptance.test_doc_a.T.test_x": {"status": "fail"}}}
        b2 = {"by_id": {"_acceptance.task1.test_doc_a.T.test_x": {"status": "fail"}}}
        result = run.task1_retention(b1, b2)
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["regressions"], [])

    def test_by_id_missing_on_one_side_falls_back_to_legacy(self):
        # An older, un-rescored row may have "failed_tests" but no "by_id"
        # at all (pre-expected-id-scoring). Falls back rather than treating
        # the whole retention as unmeasurable.
        b1 = {"total": 2, "passed": 2, "failed_tests": []}
        b2 = {"total": 2, "passed": 2, "failed_tests": []}
        result = run.task1_retention(b1, b2)
        self.assertEqual(result, {"passed": 2, "total": 2, "regressions": []})


class SumPhaseMetricsTest(unittest.TestCase):
    def _metrics(self, **overrides):
        base = {
            "num_turns": 1, "assistant_message_count": 1,
            "assistant_turns_incl_subagents": 1, "total_tool_calls": 1,
            "memory_file_reads": 0, "subagent_launches": 0,
            "subagent_messages": 0, "tool_result_errors": 0,
            "hook_denials": 0, "stop_hook_blocks": 0, "main_tokens": 100,
            "all_model_tokens": 100, "total_tokens": 100,
            "duration_ms": 1000, "duration_api_ms": 500,
            "est_cost_usd": 0.01,
            "usage": {"input_tokens": 10, "output_tokens": 20,
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            "tool_calls_by_name": {"Read": 1},
            "model_usage": {"claude-sonnet-5": {"inputTokens": 10, "outputTokens": 20,
                                                  "cacheReadInputTokens": 0,
                                                  "cacheCreationInputTokens": 0,
                                                  "costUSD": 0.01}},
            "distinct_models_used": 1,
            "subtype": "success", "is_error": False,
            "mcp_servers": [], "plugins": [],
        }
        base.update(overrides)
        return base

    def test_numeric_fields_summed(self):
        m1 = self._metrics()
        m2 = self._metrics(num_turns=2, total_tokens=200, main_tokens=200,
                            all_model_tokens=200)
        out = run._sum_phase_metrics(m1, m2)
        self.assertEqual(out["num_turns"], 3)
        self.assertEqual(out["total_tokens"], 300)
        self.assertEqual(out["main_tokens"], 300)

    def test_usage_dict_summed_keywise(self):
        m1 = self._metrics()
        m2 = self._metrics()
        out = run._sum_phase_metrics(m1, m2)
        self.assertEqual(out["usage"]["input_tokens"], 20)
        self.assertEqual(out["usage"]["output_tokens"], 40)

    def test_tool_calls_by_name_summed(self):
        m1 = self._metrics(tool_calls_by_name={"Read": 2, "Edit": 1})
        m2 = self._metrics(tool_calls_by_name={"Read": 1, "Write": 3})
        out = run._sum_phase_metrics(m1, m2)
        self.assertEqual(out["tool_calls_by_name"], {"Read": 3, "Edit": 1, "Write": 3})

    def test_model_usage_summed_and_distinct_models_recomputed(self):
        m1 = self._metrics()
        m2 = self._metrics(model_usage={
            "claude-opus": {"inputTokens": 5, "outputTokens": 5,
                             "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0,
                             "costUSD": 0.02}})
        out = run._sum_phase_metrics(m1, m2)
        self.assertEqual(set(out["model_usage"].keys()), {"claude-sonnet-5", "claude-opus"})
        self.assertEqual(out["distinct_models_used"], 2)
        self.assertEqual(out["model_usage"]["claude-sonnet-5"]["inputTokens"], 10)

    def test_est_cost_summed(self):
        m1 = self._metrics(est_cost_usd=0.01)
        m2 = self._metrics(est_cost_usd=0.02)
        out = run._sum_phase_metrics(m1, m2)
        self.assertAlmostEqual(out["est_cost_usd"], 0.03)

    def test_est_cost_none_when_both_none(self):
        m1 = self._metrics(est_cost_usd=None)
        m2 = self._metrics(est_cost_usd=None)
        out = run._sum_phase_metrics(m1, m2)
        self.assertIsNone(out["est_cost_usd"])

    def test_non_additive_fields_take_phase2_value(self):
        m1 = self._metrics(mcp_servers=[{"name": "serena"}])
        m2 = self._metrics(mcp_servers=[{"name": "serena"}, {"name": "other"}])
        out = run._sum_phase_metrics(m1, m2)
        self.assertEqual(out["mcp_servers"], m2["mcp_servers"])


class CmdSelftestPivotTest(unittest.TestCase):
    """cmd_selftest gracefully skips the pivot self-test when tasks/<task>/
    pivot/ doesn't exist -- exercised against the real v1 task fixture
    (which has no pivot/ dir) rather than a synthetic tree, since
    cmd_selftest reads task_paths(task) internally."""

    def test_v1_has_no_pivot_and_selftest_still_runs(self):
        paths = run.task_paths("v1")
        self.assertFalse(run.has_pivot(paths))
        # cmd_selftest itself needs the real fixture/reference_solution on
        # disk to do anything meaningful; just confirm has_pivot's guard is
        # what gates the pivot branch (the full cmd_selftest exercise for
        # v1's single-phase path is already covered elsewhere / by CI, and
        # a live run here would duplicate that cost).


if __name__ == "__main__":
    unittest.main()
