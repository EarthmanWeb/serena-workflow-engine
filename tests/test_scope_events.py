"""Tests for scope-guard event logging (agent_spawn/agent_ok/agent_fail/
scope_extend) — the remaining wiring on top of hooks/swe_hooks/core/
scope_guard.py's pure functions (constants + budget_for_model/parse_budget_tag/
parse_scope_extend/classify_kind are covered by test_scope_guard.py).

Covers:
  - post/swe_post_orchestrator_drift.py:
      extract_spawned_agent_id  — structured dict, free-form text ("agentId: X"),
                                   plain string, and no-id-found cases
      resolve_spawn_budget      — [swe-budget: N] tag override vs model-family default
      main() end-to-end via stdin:
        * spawned-agent branch logs agent_ok for a classify_kind()-recognized
          call, logs nothing for an unrecognized (read-only) tool
        * main-agent Agent/Task call logs agent_spawn from tool_response
        * main-agent SendMessage with [scope-extend] logs scope_extend and
          participates in NEITHER the drift streak NOR the delegation reset
  - post/swe_post_tool_failure.py:
      main() logs agent_fail for a spawned agent's failed classify_kind() call

Stdlib unittest only. Deterministic + offline; IO via tempfile, path resolution
via CLAUDE_PROJECT_DIR env var (mirrors test_hooks_post.py /
test_agent_model_and_drift.py conventions).
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
drift_hook = import_hook("post/swe_post_orchestrator_drift")
failure_hook = import_hook("post/swe_post_tool_failure")


def _read_events(stream_path):
    if not os.path.exists(stream_path):
        return []
    with open(stream_path) as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------------------
# drift_hook.extract_spawned_agent_id
# ---------------------------------------------------------------------------
class TestExtractSpawnedAgentId(unittest.TestCase):
    def test_structured_dict_agent_id_key(self):
        self.assertEqual(
            drift_hook.extract_spawned_agent_id({"agent_id": "a-123"}), "a-123")

    def test_structured_dict_agentid_key(self):
        self.assertEqual(
            drift_hook.extract_spawned_agent_id({"agentId": "a-456"}), "a-456")

    def test_documented_text_shape_with_agentid_in_text(self):
        # The documented PostToolUse payload for the Agent tool:
        # {"type": "text", "text": "<free-form result>"}
        resp = {"type": "text", "text": "Launched in background. agentId: worker-9f2"}
        self.assertEqual(drift_hook.extract_spawned_agent_id(resp), "worker-9f2")

    def test_text_shape_with_agent_id_underscore_form(self):
        resp = {"type": "text", "text": "spawned; agent_id=worker_7"}
        self.assertEqual(drift_hook.extract_spawned_agent_id(resp), "worker_7")

    def test_plain_string_response(self):
        self.assertEqual(
            drift_hook.extract_spawned_agent_id("Background agent started. agentId: xyz"),
            "xyz")

    def test_no_id_present_returns_empty(self):
        self.assertEqual(
            drift_hook.extract_spawned_agent_id({"type": "text", "text": "no id here"}),
            "")

    def test_none_returns_empty(self):
        self.assertEqual(drift_hook.extract_spawned_agent_id(None), "")

    def test_empty_dict_returns_empty(self):
        self.assertEqual(drift_hook.extract_spawned_agent_id({}), "")


# ---------------------------------------------------------------------------
# drift_hook.resolve_spawn_budget
# ---------------------------------------------------------------------------
class TestResolveSpawnBudget(unittest.TestCase):
    def test_budget_tag_overrides_model_default(self):
        tool_input = {"model": "haiku", "prompt": "do X [swe-budget: 99]"}
        self.assertEqual(drift_hook.resolve_spawn_budget(tool_input), 99)

    def test_no_tag_falls_back_to_model_family(self):
        tool_input = {"model": "sonnet", "prompt": "do X"}
        self.assertEqual(drift_hook.resolve_spawn_budget(tool_input), 60)

    def test_unrecognized_model_falls_back_to_default_budget(self):
        tool_input = {"model": "", "prompt": "do X"}
        self.assertEqual(drift_hook.resolve_spawn_budget(tool_input), 60)

    def test_opus_model_default(self):
        tool_input = {"model": "claude-opus-4", "prompt": "do X"}
        self.assertEqual(drift_hook.resolve_spawn_budget(tool_input), 120)


# ---------------------------------------------------------------------------
# drift_hook.main() end-to-end
# ---------------------------------------------------------------------------
class TestDriftHookMainScopeEvents(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.tmp.name, ".git"), exist_ok=True)
        self._orig_env = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = self.tmp.name

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = self._orig_env
        self.tmp.cleanup()
        reset_caches()

    def _run_main(self, payload):
        buf = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
             mock.patch("select.select", return_value=([sys.stdin], [], [])), \
             mock.patch("sys.stdout", buf):
            try:
                drift_hook.main()
            except SystemExit:
                pass
        return buf.getvalue()

    def _spawned_agent_payload(self, tool_name, tool_input, agent_id="sub-1",
                                session_id="abcd1234"):
        transcript = f"/x/{session_id}-0000-0000-0000-000000000000.jsonl"
        return {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "transcript_path": transcript,
            "agent_id": agent_id,
            "agent_type": "general-purpose",
        }

    # -- spawned-agent branch: agent_ok -----------------------------------

    def test_spawned_agent_edit_logs_agent_ok(self):
        session_id = "aaaa1111"
        payload = self._spawned_agent_payload(
            "Edit", {"file_path": "/x.py"}, agent_id="sub-1", session_id=session_id)
        self._run_main(payload)
        events = _read_events(stream.get_stream_path(session_id))
        ok_events = [e for e in events if e.get("type") == "agent_ok"]
        self.assertEqual(len(ok_events), 1)
        self.assertEqual(ok_events[0]["agent"], "sub-1")
        self.assertEqual(ok_events[0]["kind"], "edit")

    def test_spawned_agent_test_bash_logs_agent_ok_test_kind(self):
        session_id = "bbbb2222"
        payload = self._spawned_agent_payload(
            "Bash", {"command": "python3 -m unittest discover"},
            agent_id="sub-2", session_id=session_id)
        self._run_main(payload)
        events = _read_events(stream.get_stream_path(session_id))
        ok_events = [e for e in events if e.get("type") == "agent_ok"]
        self.assertEqual(len(ok_events), 1)
        self.assertEqual(ok_events[0]["kind"], "test")

    def test_spawned_agent_plain_bash_logs_agent_ok_bash_kind(self):
        session_id = "cccc3333"
        payload = self._spawned_agent_payload(
            "Bash", {"command": "ls -la"}, agent_id="sub-3", session_id=session_id)
        self._run_main(payload)
        events = _read_events(stream.get_stream_path(session_id))
        ok_events = [e for e in events if e.get("type") == "agent_ok"]
        self.assertEqual(len(ok_events), 1)
        self.assertEqual(ok_events[0]["kind"], "bash")

    def test_spawned_agent_read_only_tool_logs_no_agent_ok(self):
        session_id = "dddd4444"
        payload = self._spawned_agent_payload(
            "Read", {"file_path": "/x.py"}, agent_id="sub-4", session_id=session_id)
        self._run_main(payload)
        events = _read_events(stream.get_stream_path(session_id))
        self.assertEqual([e for e in events if e.get("type") == "agent_ok"], [])

    def test_spawned_agent_with_no_agent_id_logs_nothing(self):
        session_id = "eeee5555"
        payload = self._spawned_agent_payload(
            "Edit", {"file_path": "/x.py"}, agent_id="", session_id=session_id)
        self._run_main(payload)
        events = _read_events(stream.get_stream_path(session_id))
        self.assertEqual([e for e in events if e.get("type") == "agent_ok"], [])

    # -- main-agent Agent/Task spawn: agent_spawn --------------------------

    def test_main_agent_spawn_structured_response_logs_agent_spawn(self):
        session_id = "ffff6666"
        transcript = f"/x/{session_id}-0000-0000-0000-000000000000.jsonl"
        payload = {
            "tool_name": "Agent",
            "tool_input": {"model": "sonnet", "prompt": "do the thing",
                           "run_in_background": True},
            "tool_response": {"agent_id": "worker-42"},
            "transcript_path": transcript,
        }
        self._run_main(payload)
        events = _read_events(stream.get_stream_path(session_id))
        spawn_events = [e for e in events if e.get("type") == "agent_spawn"]
        self.assertEqual(len(spawn_events), 1)
        self.assertEqual(spawn_events[0]["agent"], "worker-42")
        self.assertEqual(spawn_events[0]["budget"], 60)  # sonnet default

    def test_main_agent_spawn_text_response_logs_agent_spawn(self):
        session_id = "11112222"
        transcript = f"/x/{session_id}-0000-0000-0000-000000000000.jsonl"
        payload = {
            "tool_name": "Agent",
            "tool_input": {"model": "haiku", "prompt": "quick check",
                           "run_in_background": True},
            "tool_response": {"type": "text",
                               "text": "Launched in background. agentId: worker-99"},
            "transcript_path": transcript,
        }
        self._run_main(payload)
        events = _read_events(stream.get_stream_path(session_id))
        spawn_events = [e for e in events if e.get("type") == "agent_spawn"]
        self.assertEqual(len(spawn_events), 1)
        self.assertEqual(spawn_events[0]["agent"], "worker-99")
        self.assertEqual(spawn_events[0]["budget"], 25)  # haiku default

    def test_main_agent_spawn_budget_tag_overrides_model_default(self):
        session_id = "33334444"
        transcript = f"/x/{session_id}-0000-0000-0000-000000000000.jsonl"
        payload = {
            "tool_name": "Task",
            "tool_input": {"model": "haiku", "prompt": "quick check [swe-budget: 500]",
                           "run_in_background": True},
            "tool_response": {"type": "text", "text": "agentId: worker-tag"},
            "transcript_path": transcript,
        }
        self._run_main(payload)
        events = _read_events(stream.get_stream_path(session_id))
        spawn_events = [e for e in events if e.get("type") == "agent_spawn"]
        self.assertEqual(len(spawn_events), 1)
        self.assertEqual(spawn_events[0]["budget"], 500)

    def test_main_agent_spawn_expect_red_prompt_logs_flag(self):
        session_id = "99990000"
        transcript = f"/x/{session_id}-0000-0000-0000-000000000000.jsonl"
        payload = {
            "tool_name": "Agent",
            "tool_input": {
                "model": "sonnet",
                "prompt": "Write a failing test first. [swe-expect-red]",
                "run_in_background": True,
            },
            "tool_response": {"agent_id": "worker-red"},
            "transcript_path": transcript,
        }
        self._run_main(payload)
        events = _read_events(stream.get_stream_path(session_id))
        spawn_events = [e for e in events if e.get("type") == "agent_spawn"]
        self.assertEqual(len(spawn_events), 1)
        self.assertEqual(spawn_events[0]["agent"], "worker-red")
        self.assertTrue(spawn_events[0].get("expect_red"))

    def test_main_agent_spawn_without_expect_red_omits_flag(self):
        session_id = "99991111"
        transcript = f"/x/{session_id}-0000-0000-0000-000000000000.jsonl"
        payload = {
            "tool_name": "Agent",
            "tool_input": {
                "model": "sonnet",
                "prompt": "Implement the checkout flow.",
                "run_in_background": True,
            },
            "tool_response": {"agent_id": "worker-plain"},
            "transcript_path": transcript,
        }
        self._run_main(payload)
        events = _read_events(stream.get_stream_path(session_id))
        spawn_events = [e for e in events if e.get("type") == "agent_spawn"]
        self.assertEqual(len(spawn_events), 1)
        self.assertNotIn("expect_red", spawn_events[0])

    def test_main_agent_spawn_no_id_extractable_logs_nothing(self):
        session_id = "55556666"
        transcript = f"/x/{session_id}-0000-0000-0000-000000000000.jsonl"
        payload = {
            "tool_name": "Agent",
            "tool_input": {"model": "sonnet", "prompt": "do the thing",
                           "run_in_background": True},
            "tool_response": {"type": "text", "text": "Task complete, no id here."},
            "transcript_path": transcript,
        }
        self._run_main(payload)
        events = _read_events(stream.get_stream_path(session_id))
        self.assertEqual([e for e in events if e.get("type") == "agent_spawn"], [])

    # -- main-agent SendMessage: scope_extend + no drift event -------------

    def test_send_message_with_scope_extend_logs_event(self):
        session_id = "77778888"
        transcript = f"/x/{session_id}-0000-0000-0000-000000000000.jsonl"
        payload = {
            "tool_name": "SendMessage",
            "tool_input": {"to": "worker-42",
                           "message": "keep going [scope-extend: 40]"},
            "transcript_path": transcript,
        }
        self._run_main(payload)
        events = _read_events(stream.get_stream_path(session_id))
        extend_events = [e for e in events if e.get("type") == "scope_extend"]
        self.assertEqual(len(extend_events), 1)
        self.assertEqual(extend_events[0]["agent"], "worker-42")
        self.assertEqual(extend_events[0]["budget_add"], 40)

    def test_send_message_bare_scope_extend_uses_default(self):
        session_id = "99990000"
        transcript = f"/x/{session_id}-0000-0000-0000-000000000000.jsonl"
        payload = {
            "tool_name": "SendMessage",
            "tool_input": {"to": "worker-1", "message": "[scope-extend]"},
            "transcript_path": transcript,
        }
        self._run_main(payload)
        events = _read_events(stream.get_stream_path(session_id))
        extend_events = [e for e in events if e.get("type") == "scope_extend"]
        self.assertEqual(len(extend_events), 1)
        self.assertEqual(extend_events[0]["budget_add"], 30)  # DEFAULT_EXTEND

    def test_send_message_without_tag_logs_no_scope_extend(self):
        session_id = "12121212"
        transcript = f"/x/{session_id}-0000-0000-0000-000000000000.jsonl"
        payload = {
            "tool_name": "SendMessage",
            "tool_input": {"to": "worker-1", "message": "just a status update"},
            "transcript_path": transcript,
        }
        self._run_main(payload)
        events = _read_events(stream.get_stream_path(session_id))
        self.assertEqual([e for e in events if e.get("type") == "scope_extend"], [])

    def test_send_message_never_logs_task_work_or_delegation(self):
        """SendMessage is neither task work nor a delegation for DRIFT
        counting — even when it carries a [scope-extend] tag, it must not
        touch the drift streak in either direction."""
        session_id = "34343434"
        transcript = f"/x/{session_id}-0000-0000-0000-000000000000.jsonl"
        payload = {
            "tool_name": "SendMessage",
            "tool_input": {"to": "worker-1", "message": "go on [scope-extend]"},
            "transcript_path": transcript,
        }
        self._run_main(payload)
        events = _read_events(stream.get_stream_path(session_id))
        self.assertEqual([e for e in events if e.get("type") == "task_work"], [])
        self.assertEqual([e for e in events if e.get("type") == "delegation"], [])


# ---------------------------------------------------------------------------
# failure_hook.main() — agent_fail
# ---------------------------------------------------------------------------
class TestToolFailureHookAgentFail(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.tmp.name, ".git"), exist_ok=True)
        self._orig_env = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = self.tmp.name

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = self._orig_env
        self.tmp.cleanup()
        reset_caches()

    def _run_main(self, payload):
        buf = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
             mock.patch("select.select", return_value=([sys.stdin], [], [])), \
             mock.patch("sys.stdout", buf):
            try:
                failure_hook.main()
            except SystemExit:
                pass
        return buf.getvalue()

    def test_spawned_agent_failed_edit_logs_agent_fail(self):
        session_id = "abcdef01"
        transcript = f"/x/{session_id}-0000-0000-0000-000000000000.jsonl"
        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/x.py"},
            "tool_error": "some failure",
            "transcript_path": transcript,
            "agent_id": "sub-fail-1",
            "agent_type": "general-purpose",
        }
        self._run_main(payload)
        events = _read_events(stream.get_stream_path(session_id))
        fail_events = [e for e in events if e.get("type") == "agent_fail"]
        self.assertEqual(len(fail_events), 1)
        self.assertEqual(fail_events[0]["agent"], "sub-fail-1")
        self.assertEqual(fail_events[0]["kind"], "edit")

    def test_spawned_agent_failed_test_bash_logs_agent_fail_test_kind(self):
        session_id = "abcdef02"
        transcript = f"/x/{session_id}-0000-0000-0000-000000000000.jsonl"
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest -x"},
            "tool_error": "1 failed",
            "transcript_path": transcript,
            "agent_id": "sub-fail-2",
            "agent_type": "general-purpose",
        }
        self._run_main(payload)
        events = _read_events(stream.get_stream_path(session_id))
        fail_events = [e for e in events if e.get("type") == "agent_fail"]
        self.assertEqual(len(fail_events), 1)
        self.assertEqual(fail_events[0]["kind"], "test")

    def test_spawned_agent_read_only_failure_logs_no_agent_fail(self):
        session_id = "abcdef03"
        transcript = f"/x/{session_id}-0000-0000-0000-000000000000.jsonl"
        payload = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/missing.py"},
            "tool_error": "file not found",
            "transcript_path": transcript,
            "agent_id": "sub-fail-3",
            "agent_type": "general-purpose",
        }
        self._run_main(payload)
        events = _read_events(stream.get_stream_path(session_id))
        self.assertEqual([e for e in events if e.get("type") == "agent_fail"], [])

    def test_main_agent_failure_logs_no_agent_fail(self):
        session_id = "abcdef04"
        transcript = f"/x/{session_id}-0000-0000-0000-000000000000.jsonl"
        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/x.py"},
            "tool_error": "some failure",
            "transcript_path": transcript,
        }
        self._run_main(payload)
        events = _read_events(stream.get_stream_path(session_id))
        self.assertEqual([e for e in events if e.get("type") == "agent_fail"], [])


if __name__ == "__main__":
    unittest.main()
