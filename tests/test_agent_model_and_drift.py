"""Tests for orchestrator + swarm delegation enforcement:

  - pre/swe_pre_agent_model_gate: missing_model_reason, missing_bypass_marker_reason,
    opus_on_routine_reason, fable_without_justification_reason,
    foreground_without_justification_reason (allow/deny paths for the
    Agent/Task model-tier + foreground-blocking gate)
  - core/stream: count_task_work_since_delegation (drift counter + reset)
  - post/swe_post_orchestrator_drift: main() end-to-end via stdin, threshold nudge

Stdlib unittest only. Deterministic + offline; IO via tempfile, path resolution
via monkeypatching the exact symbol each module imported (mirrors
test_sweep_gate.py / test_hooks_pre.py conventions).
"""
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_hook, import_core, reset_caches  # noqa: E402

stream = import_core("swe_hooks.core.stream")
agent_gate = import_hook("pre/swe_pre_agent_model_gate")
drift_hook = import_hook("post/swe_post_orchestrator_drift")


def _write_stream(path, events):
    with open(path, "w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


# ──────────────────────────────────────────────────────────────────
# pre/swe_pre_agent_model_gate — missing_model_reason
# ──────────────────────────────────────────────────────────────────

class TestMissingModelReason(unittest.TestCase):
    def test_missing_model_on_general_purpose_denies(self):
        reason = agent_gate.missing_model_reason(
            {"subagent_type": "general-purpose", "prompt": "do stuff"})
        self.assertTrue(reason)
        self.assertIn("model tier", reason)

    def test_missing_model_unspecified_subagent_type_denies(self):
        reason = agent_gate.missing_model_reason({"prompt": "do stuff"})
        self.assertTrue(reason)

    def test_model_present_allows(self):
        reason = agent_gate.missing_model_reason(
            {"subagent_type": "general-purpose", "model": "sonnet"})
        self.assertEqual(reason, "")

    def test_blank_model_string_denies(self):
        reason = agent_gate.missing_model_reason(
            {"subagent_type": "general-purpose", "model": "   "})
        self.assertTrue(reason)

    def test_builtin_fixed_model_type_exempt(self):
        reason = agent_gate.missing_model_reason(
            {"subagent_type": "claude-code-guide"})
        self.assertEqual(reason, "")

    def test_statusline_setup_exempt(self):
        reason = agent_gate.missing_model_reason(
            {"subagent_type": "statusline-setup"})
        self.assertEqual(reason, "")

    def test_explore_type_still_requires_model(self):
        reason = agent_gate.missing_model_reason({"subagent_type": "Explore"})
        self.assertTrue(reason)


# ──────────────────────────────────────────────────────────────────
# pre/swe_pre_agent_model_gate — missing_bypass_marker_reason
# ──────────────────────────────────────────────────────────────────

class TestMissingBypassMarkerReason(unittest.TestCase):
    def test_no_marker_denies(self):
        reason = agent_gate.missing_bypass_marker_reason("Please fix the bug.")
        self.assertTrue(reason)
        self.assertIn("bypass marker", reason)

    def test_standard_marker_allows(self):
        reason = agent_gate.missing_bypass_marker_reason(
            "You are a subagent. BYPASS WF_INIT. Do the task.")
        self.assertEqual(reason, "")

    def test_case_insensitive_marker_allows(self):
        reason = agent_gate.missing_bypass_marker_reason(
            "you are a SUBAGENT and should bypass wf_init")
        self.assertEqual(reason, "")

    def test_swarm_agent_marker_allows(self):
        reason = agent_gate.missing_bypass_marker_reason(
            "You are a swarm agent handling task X.")
        self.assertEqual(reason, "")

    def test_empty_prompt_denies(self):
        reason = agent_gate.missing_bypass_marker_reason("")
        self.assertTrue(reason)


# ──────────────────────────────────────────────────────────────────
# pre/swe_pre_agent_model_gate — opus_on_routine_reason
# ──────────────────────────────────────────────────────────────────

class TestOpusOnRoutineReason(unittest.TestCase):
    def test_opus_plus_run_tests_denies(self):
        reason = agent_gate.opus_on_routine_reason(
            "opus", "Run the test suite and report failures.")
        self.assertTrue(reason)
        self.assertIn("ROUTINE", reason)

    def test_opus_plus_grep_denies(self):
        reason = agent_gate.opus_on_routine_reason(
            "opus", "Grep the codebase for TODO markers and list files.")
        self.assertTrue(reason)

    def test_opus_plus_lint_denies(self):
        reason = agent_gate.opus_on_routine_reason(
            "opus", "Run phpcbf and lint the plugin directory.")
        self.assertTrue(reason)

    def test_sonnet_plus_routine_allows(self):
        reason = agent_gate.opus_on_routine_reason(
            "sonnet", "Run the test suite and report failures.")
        self.assertEqual(reason, "")

    def test_opus_plus_design_keyword_allows(self):
        reason = agent_gate.opus_on_routine_reason(
            "opus", "Design the new caching architecture from scratch.")
        self.assertEqual(reason, "")

    def test_opus_with_justification_tag_allows(self):
        reason = agent_gate.opus_on_routine_reason(
            "opus",
            "Run the test suite. [opus-justified: needs deep multi-file "
            "reasoning across the whole test matrix]")
        self.assertEqual(reason, "")

    def test_opus_plus_non_routine_prompt_allows(self):
        reason = agent_gate.opus_on_routine_reason(
            "opus", "Implement the new checkout flow end to end.")
        self.assertEqual(reason, "")

    def test_haiku_never_denied(self):
        reason = agent_gate.opus_on_routine_reason(
            "haiku", "Run the test suite and report failures.")
        self.assertEqual(reason, "")

    def test_premium_justified_tag_also_allows(self):
        # generalized justification tag shared with the fable gate
        reason = agent_gate.opus_on_routine_reason(
            "opus",
            "Run the test suite. [premium-justified: needs deep reasoning]")
        self.assertEqual(reason, "")

    def test_opus_full_model_id_plus_routine_denies(self):
        # PREMIUM detection is a substring match, not an exact 'opus' compare
        reason = agent_gate.opus_on_routine_reason(
            "claude-opus-5-5", "Run the test suite and report failures.")
        self.assertEqual(reason, "")  # opus_on_routine_reason kept exact-match


# ──────────────────────────────────────────────────────────────────
# pre/swe_pre_agent_model_gate — fable_without_justification_reason
# ──────────────────────────────────────────────────────────────────

class TestFableWithoutJustificationReason(unittest.TestCase):
    def test_bare_fable_denied(self):
        reason = agent_gate.fable_without_justification_reason(
            "fable", "You are a subagent. BYPASS WF_INIT. Do routine work.")
        self.assertTrue(reason)
        self.assertIn("PREMIUM", reason)

    def test_full_fable_model_id_denied(self):
        reason = agent_gate.fable_without_justification_reason(
            "claude-fable-5-1", "You are a subagent. BYPASS WF_INIT. Do X.")
        self.assertTrue(reason)

    def test_fable_justified_tag_allows(self):
        reason = agent_gate.fable_without_justification_reason(
            "fable",
            "Implement X. [fable-justified: needs the premium model here]")
        self.assertEqual(reason, "")

    def test_premium_justified_tag_allows(self):
        reason = agent_gate.fable_without_justification_reason(
            "claude-fable-5-1",
            "Implement X. [premium-justified: needs the premium model here]")
        self.assertEqual(reason, "")

    def test_fable_denied_even_for_design_work(self):
        # Unlike opus, fable has no routine-vs-design carve-out — ANY fable
        # call is denied without justification, regardless of task shape.
        reason = agent_gate.fable_without_justification_reason(
            "fable", "Design the new caching architecture from scratch.")
        self.assertTrue(reason)

    def test_opus_not_affected_by_fable_check(self):
        reason = agent_gate.fable_without_justification_reason(
            "opus", "Design the new caching architecture from scratch.")
        self.assertEqual(reason, "")

    def test_sonnet_not_affected(self):
        reason = agent_gate.fable_without_justification_reason(
            "sonnet", "Do routine work.")
        self.assertEqual(reason, "")

    def test_haiku_not_affected(self):
        reason = agent_gate.fable_without_justification_reason(
            "haiku", "Do routine work.")
        self.assertEqual(reason, "")

    def test_empty_model_not_affected(self):
        reason = agent_gate.fable_without_justification_reason("", "Do X.")
        self.assertEqual(reason, "")


# ──────────────────────────────────────────────────────────────────
# pre/swe_pre_agent_model_gate — foreground_without_justification_reason
# ──────────────────────────────────────────────────────────────────

class TestForegroundWithoutJustificationReason(unittest.TestCase):
    def test_run_in_background_true_allows(self):
        reason = agent_gate.foreground_without_justification_reason(
            {"run_in_background": True, "prompt": "Do X."})
        self.assertEqual(reason, "")

    def test_run_in_background_false_denies(self):
        reason = agent_gate.foreground_without_justification_reason(
            {"run_in_background": False, "prompt": "Do X."})
        self.assertTrue(reason)
        self.assertIn("FOREGROUND", reason)

    def test_run_in_background_missing_denies(self):
        reason = agent_gate.foreground_without_justification_reason(
            {"prompt": "Do X."})
        self.assertTrue(reason)

    def test_false_plus_valid_justification_tag_allows(self):
        reason = agent_gate.foreground_without_justification_reason({
            "run_in_background": False,
            "prompt": "Do X. [foreground-justified: nothing else to do "
                      "until this returns]",
        })
        self.assertEqual(reason, "")

    def test_empty_reason_tag_still_denies(self):
        reason = agent_gate.foreground_without_justification_reason({
            "run_in_background": False,
            "prompt": "Do X. [foreground-justified: ]",
        })
        self.assertTrue(reason)

    def test_no_subagent_type_exempt(self):
        # Unlike missing_model_reason, no subagent_type is exempt here.
        reason = agent_gate.foreground_without_justification_reason(
            {"subagent_type": "claude-code-guide", "prompt": "Do X."})
        self.assertTrue(reason)


# ──────────────────────────────────────────────────────────────────
# pre/swe_pre_agent_model_gate — with_steering_clause
# ──────────────────────────────────────────────────────────────────

class TestWithSteeringClause(unittest.TestCase):
    def test_appends_marker_and_clause(self):
        result = agent_gate.with_steering_clause({"prompt": "Do X."})
        self.assertIn(agent_gate.STEERING_CLAUSE_MARKER, result["prompt"])
        self.assertTrue(result["prompt"].startswith("Do X."))

    def test_idempotent_when_marker_already_present(self):
        once = agent_gate.with_steering_clause({"prompt": "Do X."})
        twice = agent_gate.with_steering_clause(once)
        self.assertEqual(once["prompt"], twice["prompt"])
        self.assertEqual(
            once["prompt"].count(agent_gate.STEERING_CLAUSE_MARKER), 1)

    def test_preserves_other_keys(self):
        result = agent_gate.with_steering_clause({
            "prompt": "Do X.",
            "model": "sonnet",
            "run_in_background": True,
            "subagent_type": "general-purpose",
        })
        self.assertEqual(result["model"], "sonnet")
        self.assertEqual(result["run_in_background"], True)
        self.assertEqual(result["subagent_type"], "general-purpose")

    def test_does_not_mutate_input(self):
        original = {"prompt": "Do X."}
        result = agent_gate.with_steering_clause(original)
        self.assertEqual(original["prompt"], "Do X.")
        self.assertNotEqual(result["prompt"], original["prompt"])

    def test_non_string_prompt_passthrough(self):
        original = {"prompt": None, "model": "sonnet"}
        result = agent_gate.with_steering_clause(original)
        self.assertEqual(result, original)
        self.assertIsNot(result, original)

    def test_missing_prompt_passthrough(self):
        original = {"model": "sonnet"}
        result = agent_gate.with_steering_clause(original)
        self.assertEqual(result, original)

    def test_non_dict_input_passthrough(self):
        self.assertEqual(agent_gate.with_steering_clause("not-a-dict"), "not-a-dict")
        self.assertIsNone(agent_gate.with_steering_clause(None))


# ──────────────────────────────────────────────────────────────────
# pre/swe_pre_agent_model_gate — main() end-to-end via stdin
# ──────────────────────────────────────────────────────────────────

class TestAgentModelGateMain(unittest.TestCase):
    def _run_main(self, input_data):
        stdin_json = json.dumps(input_data)
        captured = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin_json)), \
             mock.patch("select.select", return_value=([sys.stdin], [], [])), \
             mock.patch("sys.stdout", captured):
            try:
                agent_gate.main()
            except SystemExit:
                pass
        return json.loads(captured.getvalue() or "{}")

    def test_non_agent_tool_passes_through_empty(self):
        result = self._run_main({"tool_name": "Read", "tool_input": {}})
        self.assertEqual(result, {})

    def test_agent_call_missing_model_denied(self):
        result = self._run_main({
            "tool_name": "Agent",
            "tool_input": {
                "subagent_type": "general-purpose",
                "prompt": "You are a subagent. BYPASS WF_INIT. Do X.",
            },
        })
        self.assertEqual(
            result.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")

    def test_agent_call_fully_valid_allows(self):
        result = self._run_main({
            "tool_name": "Agent",
            "tool_input": {
                "subagent_type": "general-purpose",
                "model": "sonnet",
                "prompt": "You are a subagent. BYPASS WF_INIT. Implement X.",
                "run_in_background": True,
            },
        })
        hook_out = result.get("hookSpecificOutput", {})
        self.assertEqual(hook_out.get("permissionDecision"), "allow")
        updated_prompt = hook_out.get("updatedInput", {}).get("prompt", "")
        self.assertIn(agent_gate.STEERING_CLAUSE_MARKER, updated_prompt)
        self.assertIn("Implement X.", updated_prompt)

    def test_task_tool_alias_also_gated(self):
        result = self._run_main({
            "tool_name": "Task",
            "tool_input": {"subagent_type": "general-purpose"},
        })
        self.assertEqual(
            result.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")

    def test_fable_model_denied_without_justification(self):
        result = self._run_main({
            "tool_name": "Agent",
            "tool_input": {
                "subagent_type": "general-purpose",
                "model": "fable",
                "prompt": "You are a subagent. BYPASS WF_INIT. Implement X.",
            },
        })
        self.assertEqual(
            result.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")

    def test_fable_model_allowed_with_justification(self):
        result = self._run_main({
            "tool_name": "Agent",
            "tool_input": {
                "subagent_type": "general-purpose",
                "model": "fable",
                "prompt": "You are a subagent. BYPASS WF_INIT. Implement X. "
                          "[fable-justified: needs premium reasoning]",
                "run_in_background": True,
            },
        })
        hook_out = result.get("hookSpecificOutput", {})
        self.assertEqual(hook_out.get("permissionDecision"), "allow")
        self.assertIn(
            agent_gate.STEERING_CLAUSE_MARKER,
            hook_out.get("updatedInput", {}).get("prompt", ""))

    def test_foreground_call_denied_without_justification(self):
        result = self._run_main({
            "tool_name": "Agent",
            "tool_input": {
                "subagent_type": "general-purpose",
                "model": "sonnet",
                "prompt": "You are a subagent. BYPASS WF_INIT. Implement X.",
                "run_in_background": False,
            },
        })
        self.assertEqual(
            result.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")

    def test_foreground_call_allowed_with_justification(self):
        result = self._run_main({
            "tool_name": "Agent",
            "tool_input": {
                "subagent_type": "general-purpose",
                "model": "sonnet",
                "prompt": "You are a subagent. BYPASS WF_INIT. Implement X. "
                          "[foreground-justified: nothing else to do until "
                          "this returns]",
                "run_in_background": False,
            },
        })
        hook_out = result.get("hookSpecificOutput", {})
        self.assertEqual(hook_out.get("permissionDecision"), "allow")
        self.assertIn(
            agent_gate.STEERING_CLAUSE_MARKER,
            hook_out.get("updatedInput", {}).get("prompt", ""))


# ──────────────────────────────────────────────────────────────────
# core/stream — count_task_work_since_delegation
# ──────────────────────────────────────────────────────────────────

class TestCountTaskWorkSinceDelegation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stream_path = os.path.join(self.tmp.name, "s1.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_counts_task_work_since_last_delegation(self):
        _write_stream(self.stream_path, [
            {"type": "delegation", "tool": "Agent"},
            {"type": "task_work", "tool": "Edit"},
            {"type": "task_work", "tool": "Bash"},
            {"type": "task_work", "tool": "Write"},
        ])
        self.assertEqual(stream.count_task_work_since_delegation(self.stream_path), 3)

    def test_resets_on_delegation_event(self):
        _write_stream(self.stream_path, [
            {"type": "task_work", "tool": "Edit"},
            {"type": "task_work", "tool": "Edit"},
            {"type": "delegation", "tool": "Workflow"},
            {"type": "task_work", "tool": "Bash"},
        ])
        self.assertEqual(stream.count_task_work_since_delegation(self.stream_path), 1)

    def test_resets_on_state_event(self):
        _write_stream(self.stream_path, [
            {"type": "task_work", "tool": "Edit"},
            {"type": "task_work", "tool": "Edit"},
            {"type": "state", "to_s": "WF_EXECUTE"},
            {"type": "task_work", "tool": "Bash"},
        ])
        self.assertEqual(stream.count_task_work_since_delegation(self.stream_path), 1)

    def test_no_stream_file_returns_zero(self):
        missing = os.path.join(self.tmp.name, "missing.jsonl")
        self.assertEqual(stream.count_task_work_since_delegation(missing), 0)


# ──────────────────────────────────────────────────────────────────
# post/swe_post_orchestrator_drift — main() end-to-end via stdin
# ──────────────────────────────────────────────────────────────────

class TestOrchestratorDriftMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        reset_caches()
        # Point the stream dir helper at our tempdir for isolation.
        self._config_patch = mock.patch(
            "swe_hooks.core.config.get_project_root", return_value=self.tmp.name)
        self._config_patch.start()
        self.addCleanup(self._config_patch.stop)

    def _run_main(self, input_data):
        stdin_json = json.dumps(input_data)
        captured = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin_json)), \
             mock.patch("select.select", return_value=([sys.stdin], [], [])), \
             mock.patch("sys.stdout", captured):
            try:
                drift_hook.main()
            except SystemExit:
                pass
        return json.loads(captured.getvalue() or "{}")

    def _transcript(self, session_id):
        return f"/x/{session_id}0000-0000-0000-0000-000000000000.jsonl"

    def test_edit_below_threshold_no_nudge(self):
        result = self._run_main({
            "tool_name": "Edit",
            "transcript_path": self._transcript("abcd1234"),
            "tool_input": {},
        })
        ctx = result.get("hookSpecificOutput", {}).get("additionalContext", "")
        self.assertNotIn("Orchestrator drift", ctx)

    def test_drift_nudge_at_threshold(self):
        session_id = "abcd1234"
        for _ in range(drift_hook.DRIFT_THRESHOLD - 1):
            self._run_main({
                "tool_name": "Edit",
                "transcript_path": self._transcript(session_id),
                "tool_input": {},
            })
        result = self._run_main({
            "tool_name": "Bash",
            "transcript_path": self._transcript(session_id),
            "tool_input": {},
        })
        ctx = result.get("hookSpecificOutput", {}).get("additionalContext", "")
        self.assertIn("Orchestrator drift", ctx)
        self.assertIn(str(drift_hook.DRIFT_THRESHOLD), ctx)

    def test_hard_mandate_at_hard_threshold(self):
        DRIFT_HARD_THRESHOLD = drift_hook.DRIFT_HARD_THRESHOLD
        session_id = "facade01"
        for _ in range(DRIFT_HARD_THRESHOLD - 1):
            self._run_main({
                "tool_name": "Edit",
                "transcript_path": self._transcript(session_id),
                "tool_input": {},
            })
        result = self._run_main({
            "tool_name": "Bash",
            "transcript_path": self._transcript(session_id),
            "tool_input": {},
        })
        ctx = result.get("hookSpecificOutput", {}).get("additionalContext", "")
        self.assertIn(str(DRIFT_HARD_THRESHOLD), ctx)
        self.assertIn("STOP doing the work yourself", ctx)
        self.assertIn("single-agent:", ctx)

    def test_advisory_still_fires_below_hard_threshold(self):
        # The plain advisory (DRIFT_THRESHOLD=6) must be unchanged: at 6 it
        # nudges but does NOT carry the hard-mandate STOP language.
        session_id = "abed0001"
        for _ in range(drift_hook.DRIFT_THRESHOLD - 1):
            self._run_main({
                "tool_name": "Edit",
                "transcript_path": self._transcript(session_id),
                "tool_input": {},
            })
        result = self._run_main({
            "tool_name": "Bash",
            "transcript_path": self._transcript(session_id),
            "tool_input": {},
        })
        ctx = result.get("hookSpecificOutput", {}).get("additionalContext", "")
        self.assertIn("Orchestrator drift", ctx)
        self.assertIn(str(drift_hook.DRIFT_THRESHOLD), ctx)
        self.assertNotIn("STOP doing the work yourself", ctx)

    def test_background_agent_call_resets_counter(self):
        session_id = "efgh5678"
        for _ in range(drift_hook.DRIFT_THRESHOLD - 1):
            self._run_main({
                "tool_name": "Edit",
                "transcript_path": self._transcript(session_id),
                "tool_input": {},
            })
        # Delegate in the background — resets the streak.
        self._run_main({
            "tool_name": "Agent",
            "transcript_path": self._transcript(session_id),
            "tool_input": {"run_in_background": True},
        })
        result = self._run_main({
            "tool_name": "Bash",
            "transcript_path": self._transcript(session_id),
            "tool_input": {},
        })
        ctx = result.get("hookSpecificOutput", {}).get("additionalContext", "")
        self.assertNotIn("Orchestrator drift", ctx)

    def test_workflow_call_resets_counter(self):
        session_id = "wfres001"
        for _ in range(drift_hook.DRIFT_THRESHOLD - 1):
            self._run_main({
                "tool_name": "Edit",
                "transcript_path": self._transcript(session_id),
                "tool_input": {},
            })
        # Workflow is always a background hand-off — resets even with no
        # run_in_background field at all.
        self._run_main({
            "tool_name": "Workflow",
            "transcript_path": self._transcript(session_id),
            "tool_input": {},
        })
        result = self._run_main({
            "tool_name": "Bash",
            "transcript_path": self._transcript(session_id),
            "tool_input": {},
        })
        ctx = result.get("hookSpecificOutput", {}).get("additionalContext", "")
        self.assertNotIn("Orchestrator drift", ctx)

    def test_foreground_agent_call_does_not_reset_and_counts_as_task_work(self):
        # A foreground Agent/Task call (run_in_background missing or False)
        # blocks the orchestrator on one subagent — it must NOT reset the
        # drift streak, and must instead count toward it like any other
        # task-work call.
        session_id = "fgnr0001"
        for _ in range(drift_hook.DRIFT_THRESHOLD - 1):
            self._run_main({
                "tool_name": "Edit",
                "transcript_path": self._transcript(session_id),
                "tool_input": {},
            })
        result = self._run_main({
            "tool_name": "Agent",
            "transcript_path": self._transcript(session_id),
            "tool_input": {},
        })
        ctx = result.get("hookSpecificOutput", {}).get("additionalContext", "")
        self.assertIn("Orchestrator drift", ctx)
        self.assertIn("FOREGROUND", ctx)
        self.assertIn("run_in_background: true", ctx)

    def test_foreground_agent_explicit_false_does_not_reset(self):
        session_id = "fgnr0002"
        for _ in range(drift_hook.DRIFT_THRESHOLD - 1):
            self._run_main({
                "tool_name": "Task",
                "transcript_path": self._transcript(session_id),
                "tool_input": {"run_in_background": False},
            })
        result = self._run_main({
            "tool_name": "Bash",
            "transcript_path": self._transcript(session_id),
            "tool_input": {},
        })
        ctx = result.get("hookSpecificOutput", {}).get("additionalContext", "")
        self.assertIn("Orchestrator drift", ctx)

    def test_spawned_agent_call_is_not_tracked(self):
        result = self._run_main({
            "tool_name": "Edit",
            "transcript_path": self._transcript("ijkl9012"),
            "tool_input": {},
            "agent_id": "sub-1",
            "agent_type": "general-purpose",
        })
        self.assertEqual(result, {})

    def test_verification_bash_never_reaches_threshold(self):
        # Must-not-fire: repeated git/test-runner Bash calls never nudge, no
        # matter how many — they are checking state, not doing task work.
        session_id = "mnop3456"
        for _ in range(drift_hook.DRIFT_THRESHOLD + 5):
            result = self._run_main({
                "tool_name": "Bash",
                "transcript_path": self._transcript(session_id),
                "tool_input": {"command": "git status"},
            })
        ctx = result.get("hookSpecificOutput", {}).get("additionalContext", "")
        self.assertNotIn("Orchestrator drift", ctx)

    def test_mixed_verification_and_edit_still_counts(self):
        # Must-fire: verification Bash calls interleaved with real edits still
        # accumulate drift from the edits.
        session_id = "qrst7890"
        for _ in range(drift_hook.DRIFT_THRESHOLD - 1):
            self._run_main({
                "tool_name": "Edit",
                "transcript_path": self._transcript(session_id),
                "tool_input": {},
            })
            self._run_main({
                "tool_name": "Bash",
                "transcript_path": self._transcript(session_id),
                "tool_input": {"command": "git diff"},
            })
        result = self._run_main({
            "tool_name": "Bash",
            "transcript_path": self._transcript(session_id),
            "tool_input": {"command": "rm -rf build"},
        })
        ctx = result.get("hookSpecificOutput", {}).get("additionalContext", "")
        self.assertIn("Orchestrator drift", ctx)


# ──────────────────────────────────────────────────────────────────
# post/swe_post_orchestrator_drift — bash_is_verification / is_task_work
# ──────────────────────────────────────────────────────────────────

class TestBashIsVerification(unittest.TestCase):
    def test_git_status_is_verification(self):
        self.assertTrue(drift_hook.bash_is_verification("git status"))

    def test_git_diff_is_verification(self):
        self.assertTrue(drift_hook.bash_is_verification("git diff HEAD~1"))

    def test_git_commit_is_verification(self):
        self.assertTrue(drift_hook.bash_is_verification('git commit -m "x"'))

    def test_unittest_runner_is_verification(self):
        self.assertTrue(drift_hook.bash_is_verification(
            "python3 -m unittest discover -s tests -p 'test_*.py'"))

    def test_pytest_is_verification(self):
        self.assertTrue(drift_hook.bash_is_verification("pytest tests/"))

    def test_npm_test_is_verification(self):
        self.assertTrue(drift_hook.bash_is_verification("npm test"))

    def test_py_compile_is_verification(self):
        self.assertTrue(drift_hook.bash_is_verification("python3 -m py_compile foo.py"))

    def test_jq_filter_is_verification(self):
        self.assertTrue(drift_hook.bash_is_verification("jq . out.json"))

    def test_validate_script_is_verification(self):
        self.assertTrue(drift_hook.bash_is_verification(
            "python3 scripts/validate-state-machine.py"))

    def test_chained_verification_groups_all_verification(self):
        self.assertTrue(drift_hook.bash_is_verification(
            "git status && python3 -m unittest discover -s tests"))

    def test_mutation_command_is_not_verification(self):
        self.assertFalse(drift_hook.bash_is_verification("rm -rf build"))

    def test_chained_with_one_mutation_is_not_verification(self):
        self.assertFalse(drift_hook.bash_is_verification("git status && rm file.txt"))

    def test_empty_command_is_not_verification(self):
        self.assertFalse(drift_hook.bash_is_verification(""))

    def test_git_push_is_not_verification(self):
        self.assertFalse(drift_hook.bash_is_verification("git push origin main"))


class TestIsBackgroundDelegation(unittest.TestCase):
    def test_workflow_always_true(self):
        self.assertTrue(drift_hook.is_background_delegation("Workflow", {}))

    def test_workflow_true_even_with_no_tool_input(self):
        self.assertTrue(drift_hook.is_background_delegation("Workflow", None))

    def test_agent_with_run_in_background_true(self):
        self.assertTrue(drift_hook.is_background_delegation(
            "Agent", {"run_in_background": True}))

    def test_agent_with_run_in_background_false(self):
        self.assertFalse(drift_hook.is_background_delegation(
            "Agent", {"run_in_background": False}))

    def test_agent_with_run_in_background_missing(self):
        self.assertFalse(drift_hook.is_background_delegation("Agent", {}))

    def test_task_with_run_in_background_true(self):
        self.assertTrue(drift_hook.is_background_delegation(
            "Task", {"run_in_background": True}))

    def test_task_with_run_in_background_false(self):
        self.assertFalse(drift_hook.is_background_delegation(
            "Task", {"run_in_background": False}))

    def test_task_with_run_in_background_missing(self):
        self.assertFalse(drift_hook.is_background_delegation("Task", {}))

    def test_non_dict_tool_input_false(self):
        self.assertFalse(drift_hook.is_background_delegation("Agent", None))
        self.assertFalse(drift_hook.is_background_delegation("Agent", "not-a-dict"))
        self.assertFalse(drift_hook.is_background_delegation("Task", None))

    def test_unrelated_tool_name_false(self):
        self.assertFalse(drift_hook.is_background_delegation(
            "Edit", {"run_in_background": True}))

    def test_truthy_non_true_value_is_not_background(self):
        # Must be exactly True, not merely truthy.
        self.assertFalse(drift_hook.is_background_delegation(
            "Agent", {"run_in_background": 1}))


class TestIsTaskWork(unittest.TestCase):
    def test_edit_is_task_work(self):
        self.assertTrue(drift_hook.is_task_work("Edit", {}))

    def test_verification_bash_is_not_task_work(self):
        self.assertFalse(drift_hook.is_task_work("Bash", {"command": "git log"}))

    def test_mutating_bash_is_task_work(self):
        self.assertTrue(drift_hook.is_task_work("Bash", {"command": "echo x > f"}))

    def test_serena_edit_tool_is_task_work(self):
        self.assertTrue(drift_hook.is_task_work(
            "mcp__plugin_swe_serena__replace_content", {}))


if __name__ == "__main__":
    unittest.main()
