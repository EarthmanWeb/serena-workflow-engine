"""Tests: spawned-agent exemption on PostToolUse hooks that inject workflow
directives or drive FSM state.

Subagents are told to bypass WF_INIT/the orchestrator's workflow entirely, yet
these PostToolUse hooks kept injecting ON STEP / CONTINUE (WF_*) / checkpoint /
docs-first / doc-claims text into their tool results — training subagents to
dismiss injected text, which then also trains them to dismiss legitimate
orchestrator steering. Mirrors the is_spawned_agent(...)/is_subagent_transcript
pattern already used by swe_post_orchestrator_drift.py (core.session).

Covers:
  post/swe_post_read_state       — docread still logged, NO additionalContext,
                                    NO readAdvance FSM transition.
  post/swe_post_edit_checkpoint  — output_empty(), no 'edit' stream event
                                    (a subagent's edits do not feed the
                                    orchestrator's checkpoint counter).
  post/swe_post_write_continue   — output_empty(), no continuation text.
  post/swe_post_todo_wm_sync     — output_empty(), no stream event, no WM sync.
  post/swe_post_search_docs_hint — output_empty(), no 'search' stream event.

post/swe_post_doc_claims is covered separately in test_doc_claims.py.

Stdlib unittest only. Deterministic + offline.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_hook, reset_caches  # noqa: E402

read_state_mod = import_hook("post/swe_post_read_state")
edit_checkpoint_mod = import_hook("post/swe_post_edit_checkpoint")
write_continue_mod = import_hook("post/swe_post_write_continue")
todo_sync_mod = import_hook("post/swe_post_todo_wm_sync")
search_hint_mod = import_hook("post/swe_post_search_docs_hint")

SESSION = "ab12cd34"
TRANSCRIPT = f"/x/{SESSION}-0000-0000-0000-000000000000.jsonl"


def _run_main(module, payload):
    orig = module.read_stdin_safe
    module.read_stdin_safe = lambda **kw: payload
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            with_exit = False
            try:
                module.main()
            except SystemExit:
                with_exit = True
        assert with_exit, "hook main() must sys.exit(0)"
    finally:
        module.read_stdin_safe = orig
    raw = buf.getvalue().strip()
    return json.loads(raw) if raw else {}


def _read_events(stream_path):
    if not os.path.exists(stream_path):
        return []
    events = []
    with open(stream_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events


class SpawnedAgentHookTestCase(unittest.TestCase):
    """Shared tmp-project scaffolding for spawned-agent exemption tests."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name
        self.stream_path = os.path.join(self.cwd, f"{SESSION}.jsonl")
        reset_caches()

    def tearDown(self):
        self.tmp.cleanup()


class TestPostReadStateSpawnedAgentExempt(SpawnedAgentHookTestCase):
    def setUp(self):
        super().setUp()
        self._orig_stream_path = read_state_mod.get_stream_path
        read_state_mod.get_stream_path = lambda sid: self.stream_path

    def tearDown(self):
        read_state_mod.get_stream_path = self._orig_stream_path
        super().tearDown()

    def _payload(self, memory_name, agent_id="agent-xyz"):
        return {
            "tool_name": "mcp__plugin_swe_serena__read_memory",
            "tool_input": {"memory_name": memory_name},
            "tool_result": "",
            "transcript_path": TRANSCRIPT,
            "cwd": self.cwd,
            "agent_id": agent_id,
        }

    def test_wf_memory_read_produces_empty_output(self):
        result = _run_main(read_state_mod, self._payload("wf/WF_EXECUTE"))
        self.assertEqual(result, {})

    def test_wf_memory_read_logs_docread_event(self):
        _run_main(read_state_mod, self._payload("wf/WF_EXECUTE"))
        events = _read_events(self.stream_path)
        docreads = [e for e in events if e.get("type") == "docread"]
        self.assertEqual(len(docreads), 1)
        self.assertEqual(docreads[0].get("name"), "wf/WF_EXECUTE")

    def test_wf_memory_read_never_appends_state_transition_event(self):
        _run_main(read_state_mod, self._payload("wf/WF_EXECUTE"))
        events = _read_events(self.stream_path)
        state_events = [e for e in events if e.get("type") == "state"]
        self.assertEqual(state_events, [])

    def test_no_state_file_written_for_spawned_agent(self):
        # A real (non-exempt) forward read from WF_CLASSIFY->WF_ARCH_REVIEW
        # would write a state file; the spawned-agent path must never reach
        # StateManager at all.
        state_dir = os.path.join(self.cwd, ".serena", "streams")
        _run_main(read_state_mod, self._payload("wf/WF_ARCH_REVIEW"))
        state_file = os.path.join(state_dir, f".state_{SESSION}.json")
        self.assertFalse(os.path.exists(state_file))

    def test_non_wf_memory_read_also_empty_and_logged(self):
        result = _run_main(read_state_mod, self._payload("dom/DOM_TEST"))
        self.assertEqual(result, {})
        events = _read_events(self.stream_path)
        docreads = [e for e in events if e.get("type") == "docread"]
        self.assertEqual(len(docreads), 1)
        self.assertEqual(docreads[0].get("name"), "dom/DOM_TEST")

    def test_agentType_field_also_recognized(self):
        payload = self._payload("wf/WF_EXECUTE", agent_id=None)
        del payload["agent_id"]
        payload["agentType"] = "Explore"
        result = _run_main(read_state_mod, payload)
        self.assertEqual(result, {})

    def test_subagent_transcript_path_also_exempt_without_agent_id(self):
        payload = self._payload("wf/WF_EXECUTE", agent_id=None)
        del payload["agent_id"]
        payload["transcript_path"] = (
            f"/x/{SESSION}-0000-0000-0000-000000000000/subagents/"
            "agent-1.jsonl"
        )
        result = _run_main(read_state_mod, payload)
        self.assertEqual(result, {})

    def test_main_agent_unaffected_still_gets_on_step_text(self):
        # Control: without agent_id/subagent transcript, the ordinary
        # (non-exempt) path still emits its usual ON STEP text.
        payload = self._payload("wf/WF_EXECUTE", agent_id=None)
        del payload["agent_id"]
        result = _run_main(read_state_mod, payload)
        self.assertIn("hookSpecificOutput", result)
        context = result["hookSpecificOutput"].get("additionalContext", "")
        self.assertIn("WF_EXECUTE", context)


class TestPostEditCheckpointSpawnedAgentExempt(SpawnedAgentHookTestCase):
    def setUp(self):
        super().setUp()
        self._orig_stream_path = edit_checkpoint_mod.get_stream_path
        edit_checkpoint_mod.get_stream_path = lambda sid: self.stream_path

    def tearDown(self):
        edit_checkpoint_mod.get_stream_path = self._orig_stream_path
        super().tearDown()

    def _payload(self, agent_id="agent-xyz"):
        return {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/x/foo.py"},
            "transcript_path": TRANSCRIPT,
            "cwd": self.cwd,
            "agent_id": agent_id,
        }

    def test_empty_output(self):
        result = _run_main(edit_checkpoint_mod, self._payload())
        self.assertEqual(result, {})

    def test_no_edit_stream_event_appended(self):
        _run_main(edit_checkpoint_mod, self._payload())
        events = _read_events(self.stream_path)
        self.assertEqual([e for e in events if e.get("type") == "edit"], [])

    def test_main_agent_unaffected_still_counts_edit(self):
        payload = self._payload(agent_id=None)
        del payload["agent_id"]
        _run_main(edit_checkpoint_mod, payload)
        events = _read_events(self.stream_path)
        self.assertEqual(len([e for e in events if e.get("type") == "edit"]), 1)


class TestPostWriteContinueSpawnedAgentExempt(SpawnedAgentHookTestCase):
    def _payload(self, agent_id="agent-xyz"):
        return {
            "tool_name": "mcp__plugin_swe_serena__write_memory",
            "tool_input": {"memory_name": "dom/DOM_TEST"},
            "tool_result": "ok",
            "transcript_path": TRANSCRIPT,
            "cwd": self.cwd,
            "agent_id": agent_id,
        }

    def test_empty_output(self):
        result = _run_main(write_continue_mod, self._payload())
        self.assertEqual(result, {})

    def test_main_agent_unaffected_still_gets_context(self):
        payload = self._payload(agent_id=None)
        del payload["agent_id"]
        result = _run_main(write_continue_mod, payload)
        self.assertIn("hookSpecificOutput", result)
        self.assertIn(
            "Memory written",
            result["hookSpecificOutput"].get("additionalContext", ""))


class TestPostTodoWmSyncSpawnedAgentExempt(SpawnedAgentHookTestCase):
    def setUp(self):
        super().setUp()
        self._orig_stream_path = todo_sync_mod.get_stream_path
        todo_sync_mod.get_stream_path = lambda sid: self.stream_path
        from _hookutil import import_core
        self._config_mod = import_core("swe_hooks.core.config")
        self._orig_project_root = self._config_mod.get_project_root
        self._config_mod.get_project_root = lambda: self.cwd

    def tearDown(self):
        todo_sync_mod.get_stream_path = self._orig_stream_path
        self._config_mod.get_project_root = self._orig_project_root
        super().tearDown()

    def _payload(self, agent_id="agent-xyz"):
        return {
            "tool_name": "TodoWrite",
            "tool_input": {"todos": [{"content": "x", "status": "pending"}]},
            "transcript_path": TRANSCRIPT,
            "cwd": self.cwd,
            "agent_id": agent_id,
        }

    def _write_wm(self):
        mem = os.path.join(self.cwd, ".serena", "memories")
        os.makedirs(mem, exist_ok=True)
        wm_path = os.path.join(mem, f"WM_{SESSION}.md")
        with open(wm_path, "w") as f:
            f.write("# WM\n\n## Progress\n\n")
        return wm_path

    def test_empty_output(self):
        result = _run_main(todo_sync_mod, self._payload())
        self.assertEqual(result, {})

    def test_no_todo_stream_event_appended(self):
        _run_main(todo_sync_mod, self._payload())
        events = _read_events(self.stream_path)
        self.assertEqual([e for e in events if e.get("type") == "todo"], [])

    def test_wm_not_touched(self):
        wm_path = self._write_wm()
        with open(wm_path) as f:
            before = f.read()
        _run_main(todo_sync_mod, self._payload())
        with open(wm_path) as f:
            after = f.read()
        self.assertEqual(before, after)

    def test_main_agent_unaffected_still_syncs(self):
        wm_path = self._write_wm()
        payload = self._payload(agent_id=None)
        del payload["agent_id"]
        _run_main(todo_sync_mod, payload)
        with open(wm_path) as f:
            after = f.read()
        self.assertIn("[ ] x", after)


class TestPostSearchDocsHintSpawnedAgentExempt(SpawnedAgentHookTestCase):
    def setUp(self):
        super().setUp()
        self._orig_stream_path = search_hint_mod.get_stream_path
        search_hint_mod.get_stream_path = lambda sid: self.stream_path

    def tearDown(self):
        search_hint_mod.get_stream_path = self._orig_stream_path
        super().tearDown()

    def _payload(self, agent_id="agent-xyz"):
        return {
            "tool_name": "Grep",
            "tool_input": {"pattern": "foo"},
            "transcript_path": TRANSCRIPT,
            "cwd": self.cwd,
            "agent_id": agent_id,
        }

    def test_empty_output(self):
        result = _run_main(search_hint_mod, self._payload())
        self.assertEqual(result, {})

    def test_no_search_stream_event_appended(self):
        _run_main(search_hint_mod, self._payload())
        events = _read_events(self.stream_path)
        self.assertEqual([e for e in events if e.get("type") == "search"], [])

    def test_main_agent_unaffected_still_counts_search(self):
        payload = self._payload(agent_id=None)
        del payload["agent_id"]
        _run_main(search_hint_mod, payload)
        events = _read_events(self.stream_path)
        self.assertEqual(len([e for e in events if e.get("type") == "search"]), 1)


if __name__ == "__main__":
    unittest.main()
