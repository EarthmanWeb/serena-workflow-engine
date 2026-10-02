"""Tests for the SWE Working Memory MCP server (swe_hooks.mcp.wm_server).

Covers the PURE MCP protocol handlers (initialize / tools/list / tools/call
dispatch + response formatting), the module-level tool definitions and
constants, the _resolve_session_id resolver, and — driven through a tmpdir +
pinned project root — the filesystem tool implementations
(tool_swe_wm_read / _update_section / _update_status / _list) and the
_sync_section_to_state_file helper.

Stdlib unittest only. Deterministic + offline: no network, no Serena server,
no real git beyond a tmpdir .git.
"""
import importlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_core, reset_caches  # noqa: E402

wm = import_core("swe_hooks.mcp.wm_server")
config = import_core("swe_hooks.core.config")


# ──────────────────────────────────────────────────────────────────
# Module-level constants
# ──────────────────────────────────────────────────────────────────

class TestConstants(unittest.TestCase):
    def test_protocol_and_server_identity(self):
        self.assertEqual(wm.PROTOCOL_VERSION, "2024-11-05")
        self.assertEqual(wm.SERVER_NAME, "swe-wm")
        self.assertEqual(wm.SERVER_VERSION, "1.1.0")

    def test_protected_sections(self):
        # Daemon-managed sections the agent must never touch.
        self.assertEqual(wm.PROTECTED_SECTIONS, {"Workflow Context", "Transitions"})

    def test_allowed_sections_contains_expected(self):
        self.assertIn("Current Task", wm.ALLOWED_SECTIONS)
        self.assertIn("Progress", wm.ALLOWED_SECTIONS)
        self.assertIn("Files", wm.ALLOWED_SECTIONS)
        self.assertIn("Notes", wm.ALLOWED_SECTIONS)
        self.assertIn("Open Decisions", wm.ALLOWED_SECTIONS)
        # Protected sections must NOT appear in the agent-owned allowlist.
        for prot in wm.PROTECTED_SECTIONS:
            self.assertNotIn(prot, wm.ALLOWED_SECTIONS)

    def test_valid_statuses(self):
        self.assertEqual(
            wm.VALID_STATUSES,
            ["IN_PROGRESS", "BLOCKED", "COMPLETED", "VERIFY_COMPLETE", "FAILED"],
        )


# ──────────────────────────────────────────────────────────────────
# Tool definitions (JSON Schema)
# ──────────────────────────────────────────────────────────────────

class TestToolDefinitions(unittest.TestCase):
    def test_lists_the_six_wm_tools(self):
        names = {t["name"] for t in wm.TOOL_DEFINITIONS}
        self.assertEqual(
            names,
            {"swe_wm_read", "swe_wm_update", "swe_wm_update_section",
             "swe_wm_list", "swe_wm_update_status", "swe_wm_transition"},
        )

    def test_batch_update_schema(self):
        tool = next(t for t in wm.TOOL_DEFINITIONS if t["name"] == "swe_wm_update")
        props = tool["inputSchema"]["properties"]
        self.assertEqual(props["status"]["enum"], wm.VALID_STATUSES)
        items = props["sections"]["items"]
        self.assertEqual(items["properties"]["section"]["enum"], wm.ALLOWED_SECTIONS)
        self.assertEqual(items["required"], ["section", "content"])
        # Both top-level fields optional — status-only and sections-only calls are valid.
        self.assertEqual(tool["inputSchema"]["required"], [])

    def test_every_tool_def_has_required_keys(self):
        for tool in wm.TOOL_DEFINITIONS:
            self.assertIn("name", tool)
            self.assertIn("description", tool)
            self.assertIn("inputSchema", tool)
            self.assertIsInstance(tool["name"], str)
            self.assertIsInstance(tool["description"], str)
            schema = tool["inputSchema"]
            self.assertEqual(schema["type"], "object")
            self.assertIn("properties", schema)
            self.assertIn("required", schema)

    def test_update_section_enum_and_required(self):
        tool = next(t for t in wm.TOOL_DEFINITIONS if t["name"] == "swe_wm_update_section")
        props = tool["inputSchema"]["properties"]
        # The section enum is exactly the ALLOWED_SECTIONS list (same object).
        self.assertEqual(props["section"]["enum"], wm.ALLOWED_SECTIONS)
        self.assertEqual(tool["inputSchema"]["required"], ["section", "content"])
        self.assertFalse(props["append"]["default"])

    def test_update_status_enum_and_required(self):
        tool = next(t for t in wm.TOOL_DEFINITIONS if t["name"] == "swe_wm_update_status")
        props = tool["inputSchema"]["properties"]
        self.assertEqual(props["status"]["enum"], wm.VALID_STATUSES)
        self.assertEqual(tool["inputSchema"]["required"], ["status"])


# ──────────────────────────────────────────────────────────────────
# handle_initialize
# ──────────────────────────────────────────────────────────────────

class TestHandleInitialize(unittest.TestCase):
    def test_returns_expected_keys(self):
        result = wm.handle_initialize({})
        self.assertEqual(result["protocolVersion"], wm.PROTOCOL_VERSION)
        self.assertEqual(result["capabilities"], {"tools": {}})
        self.assertEqual(
            result["serverInfo"],
            {"name": wm.SERVER_NAME, "version": wm.SERVER_VERSION},
        )

    def test_ignores_params(self):
        # Any params object (or garbage) must yield the identical response.
        a = wm.handle_initialize({})
        b = wm.handle_initialize({"clientInfo": {"name": "x"}, "junk": 1})
        c = wm.handle_initialize(None)
        self.assertEqual(a, b)
        self.assertEqual(a, c)


# ──────────────────────────────────────────────────────────────────
# handle_tools_list
# ──────────────────────────────────────────────────────────────────

class TestHandleToolsList(unittest.TestCase):
    def test_returns_tool_definitions(self):
        result = wm.handle_tools_list({})
        self.assertEqual(result, {"tools": wm.TOOL_DEFINITIONS})
        # Same underlying object (no copy).
        self.assertIs(result["tools"], wm.TOOL_DEFINITIONS)

    def test_ignores_params(self):
        self.assertEqual(wm.handle_tools_list({}), wm.handle_tools_list({"x": 1}))


# ──────────────────────────────────────────────────────────────────
# handle_tools_call — dispatch + response formatting (via TOOL_REGISTRY)
# ──────────────────────────────────────────────────────────────────

class TestHandleToolsCall(unittest.TestCase):
    def setUp(self):
        self._saved_registry = wm.TOOL_REGISTRY

    def tearDown(self):
        wm.TOOL_REGISTRY = self._saved_registry

    def test_unknown_tool_returns_error(self):
        wm.TOOL_REGISTRY = {}
        result = wm.handle_tools_call({"name": "does_not_exist", "arguments": {}})
        self.assertTrue(result["isError"])
        self.assertEqual(result["content"][0]["type"], "text")
        self.assertIn("Unknown tool: does_not_exist", result["content"][0]["text"])

    def test_missing_name_treated_as_unknown(self):
        wm.TOOL_REGISTRY = {}
        result = wm.handle_tools_call({})
        self.assertTrue(result["isError"])
        self.assertIn("Unknown tool:", result["content"][0]["text"])

    def test_summary_result_formats_as_plain_summary_text(self):
        # A dict with a truthy 'summary' and no 'error' emits just the summary.
        wm.TOOL_REGISTRY = {
            "fake": lambda **kw: {"success": True, "summary": "done ok", "data": 42}
        }
        result = wm.handle_tools_call({"name": "fake", "arguments": {}})
        self.assertNotIn("isError", result)
        self.assertEqual(result["content"][0]["type"], "text")
        self.assertEqual(result["content"][0]["text"], "done ok")

    def test_no_summary_result_formats_as_json(self):
        # No 'summary' key -> full pretty JSON dump.
        payload = {"session_id": "abcd1234", "count": 3}
        wm.TOOL_REGISTRY = {"fake": lambda **kw: payload}
        result = wm.handle_tools_call({"name": "fake", "arguments": {}})
        self.assertNotIn("isError", result)
        self.assertEqual(json.loads(result["content"][0]["text"]), payload)
        # Pretty-printed (indent=2) means a newline in the serialized text.
        self.assertIn("\n", result["content"][0]["text"])

    def test_error_result_keeps_json_even_with_summary(self):
        # If the result dict has an 'error' key, the readable ❌ headline is
        # prepended but the JSON body (after the blank-line separator) is
        # UNCHANGED — the summary branch requires NOT result.get('error').
        wm.TOOL_REGISTRY = {
            "fake": lambda **kw: {"summary": "should be ignored", "error": "boom"}
        }
        result = wm.handle_tools_call({"name": "fake", "arguments": {}})
        self.assertNotIn("isError", result)
        text = result["content"][0]["text"]
        headline, _, json_body = text.partition("\n\n")
        self.assertTrue(headline.startswith("❌ WM[—] fake: boom"))
        parsed = json.loads(json_body)
        self.assertEqual(parsed["error"], "boom")
        self.assertEqual(parsed["summary"], "should be ignored")

    def test_error_headline_uses_result_session_id(self):
        wm.TOOL_REGISTRY = {
            "fake": lambda **kw: {"error": "sweep failed", "session_id": "b1c866da"}
        }
        result = wm.handle_tools_call({"name": "fake", "arguments": {}})
        text = result["content"][0]["text"]
        first_line = text.split("\n")[0]
        self.assertEqual(first_line, "❌ WM[b1c866da] fake: sweep failed")

    def test_error_headline_falls_back_to_argument_session_id(self):
        wm.TOOL_REGISTRY = {"fake": lambda **kw: {"error": "boom"}}
        result = wm.handle_tools_call(
            {"name": "fake", "arguments": {"session_id": "aaaaaaaa"}}
        )
        first_line = result["content"][0]["text"].split("\n")[0]
        self.assertEqual(first_line, "❌ WM[aaaaaaaa] fake: boom")

    def test_error_headline_includes_section_context(self):
        wm.TOOL_REGISTRY = {"fake": lambda **kw: {"error": "not allowed"}}
        result = wm.handle_tools_call(
            {
                "name": "fake",
                "arguments": {"session_id": "b1c866da", "section": "Notes"},
            }
        )
        first_line = result["content"][0]["text"].split("\n")[0]
        self.assertEqual(
            first_line, "❌ WM[b1c866da] fake (Notes): not allowed"
        )

    def test_error_headline_truncates_long_cause(self):
        long_cause = "x" * 300
        wm.TOOL_REGISTRY = {
            "fake": lambda **kw: {"error": long_cause, "session_id": "b1c866da"}
        }
        result = wm.handle_tools_call({"name": "fake", "arguments": {}})
        first_line = result["content"][0]["text"].split("\n")[0]
        self.assertLessEqual(len(first_line), 121)
        self.assertTrue(first_line.endswith("…"))

    def test_error_headline_body_json_unaffected_by_truncation(self):
        # Truncation only affects the headline; the JSON error string is full.
        long_cause = "y" * 300
        wm.TOOL_REGISTRY = {
            "fake": lambda **kw: {"error": long_cause, "session_id": "b1c866da"}
        }
        result = wm.handle_tools_call({"name": "fake", "arguments": {}})
        text = result["content"][0]["text"]
        _, _, json_body = text.partition("\n\n")
        parsed = json.loads(json_body)
        self.assertEqual(parsed["error"], long_cause)

    def test_non_dict_result_formats_as_json(self):
        wm.TOOL_REGISTRY = {"fake": lambda **kw: ["a", "b"]}
        result = wm.handle_tools_call({"name": "fake", "arguments": {}})
        self.assertEqual(json.loads(result["content"][0]["text"]), ["a", "b"])

    def test_arguments_are_forwarded_as_kwargs(self):
        captured = {}

        def _fake(**kw):
            captured.update(kw)
            return {"summary": "ok"}

        wm.TOOL_REGISTRY = {"fake": _fake}
        wm.handle_tools_call({"name": "fake", "arguments": {"section": "Notes", "x": 1}})
        self.assertEqual(captured, {"section": "Notes", "x": 1})

    def test_missing_arguments_defaults_to_empty_dict(self):
        called = {"n": 0}

        def _fake(**kw):
            called["n"] += 1
            self.assertEqual(kw, {})
            return {"summary": "ok"}

        wm.TOOL_REGISTRY = {"fake": _fake}
        wm.handle_tools_call({"name": "fake"})  # no 'arguments'
        self.assertEqual(called["n"], 1)

    def test_tool_exception_returns_error_response(self):
        def _boom(**kw):
            raise ValueError("kaboom")

        wm.TOOL_REGISTRY = {"fake": _boom}
        result = wm.handle_tools_call({"name": "fake", "arguments": {}})
        self.assertTrue(result["isError"])
        self.assertIn("Error: kaboom", result["content"][0]["text"])

    def test_bad_kwargs_signature_raises_and_is_caught(self):
        # Passing an argument the tool doesn't accept raises TypeError inside
        # tool_fn(**arguments); handler must catch it and return isError.
        wm.TOOL_REGISTRY = {"fake": lambda: {"summary": "ok"}}  # takes no kwargs
        result = wm.handle_tools_call({"name": "fake", "arguments": {"unexpected": 1}})
        self.assertTrue(result["isError"])
        self.assertIn("Error:", result["content"][0]["text"])


# ──────────────────────────────────────────────────────────────────
# HANDLERS registry
# ──────────────────────────────────────────────────────────────────

class TestHandlersRegistry(unittest.TestCase):
    def test_handlers_map(self):
        self.assertIs(wm.HANDLERS["initialize"], wm.handle_initialize)
        self.assertIs(wm.HANDLERS["tools/list"], wm.handle_tools_list)
        self.assertIs(wm.HANDLERS["tools/call"], wm.handle_tools_call)


# ──────────────────────────────────────────────────────────────────
# _resolve_session_id
# ──────────────────────────────────────────────────────────────────

class TestResolveSessionId(unittest.TestCase):
    def setUp(self):
        reset_caches()
        # Snapshot & clear the env vars the resolver reads.
        self._saved_env = {
            k: os.environ.get(k)
            for k in ("SWE_SESSION_ID", "CLAUDE_SESSION_ID")
        }
        for k in self._saved_env:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        reset_caches()

    def test_explicit_wins(self):
        os.environ["SWE_SESSION_ID"] = "envsessid"
        self.assertEqual(wm._resolve_session_id("explicit1"), "explicit1")

    def test_swe_session_id_env(self):
        os.environ["SWE_SESSION_ID"] = "abc12345"
        self.assertEqual(wm._resolve_session_id(), "abc12345")

    def test_claude_session_id_env_truncated_to_8(self):
        os.environ["CLAUDE_SESSION_ID"] = "0123456789abcdef"
        self.assertEqual(wm._resolve_session_id(), "01234567")

    def test_swe_env_takes_priority_over_claude_env(self):
        os.environ["SWE_SESSION_ID"] = "sweid001"
        os.environ["CLAUDE_SESSION_ID"] = "claudelongid"
        self.assertEqual(wm._resolve_session_id(), "sweid001")

    def test_no_most_recent_wm_guess(self):
        # No explicit id and no env → None, EVEN when WM files exist. Guessing
        # "the most recently modified WM" resolves to a DIFFERENT session
        # whenever two sessions share the project (observed live: swe_wm_read
        # answered for session b32e80e6 while 1fbbd3f6 was active — sweep
        # verification then ran against the wrong session's stream). The
        # session id is printed in every workflow hook message; callers pass
        # it explicitly.
        with tempfile.TemporaryDirectory() as tmp:
            mem = os.path.join(tmp, ".serena", "memories")
            os.makedirs(mem)
            older = os.path.join(mem, "WM_aaaaaaaa.md")
            newer = os.path.join(mem, "WM_bbbbbbbb.md")
            with open(older, "w") as f:
                f.write("# old\n")
            with open(newer, "w") as f:
                f.write("# new\n")
            os.utime(older, (1000, 1000))
            os.utime(newer, (2000, 2000))
            config._PROJECT_ROOT = tmp
            try:
                self.assertIsNone(wm._resolve_session_id())
            finally:
                config._PROJECT_ROOT = None

    def test_returns_none_when_no_wm_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".serena", "memories"))
            config._PROJECT_ROOT = tmp
            try:
                self.assertIsNone(wm._resolve_session_id())
            finally:
                config._PROJECT_ROOT = None


# ──────────────────────────────────────────────────────────────────
# Filesystem tools — driven via tmpdir + pinned project root
# ──────────────────────────────────────────────────────────────────

class _FSBase(unittest.TestCase):
    """Base for tests that hit the filesystem.

    Pins config._PROJECT_ROOT to a tmpdir so every get_project_root() call
    (session.get_project_root delegates to config.get_project_root) resolves
    into the tmpdir. Also forces _is_stale_daemon False so write_state_file
    is never refused, and clears the session env vars so _resolve_session_id
    only uses the explicit id we pass.
    """

    SID = "abcd1234"

    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, ".git"))
        self.mem = os.path.join(self.root, ".serena", "memories")
        os.makedirs(self.mem)
        config._PROJECT_ROOT = self.root

        self._saved_stale = config._is_stale_daemon
        config._is_stale_daemon = lambda: False

        self._saved_env = {
            k: os.environ.get(k) for k in ("SWE_SESSION_ID", "CLAUDE_SESSION_ID")
        }
        for k in self._saved_env:
            os.environ.pop(k, None)

    def tearDown(self):
        config._is_stale_daemon = self._saved_stale
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        config._PROJECT_ROOT = None
        self.tmp.cleanup()
        reset_caches()

    def _wm_path(self, sid=None):
        return os.path.join(self.mem, f"WM_{sid or self.SID}.md")

    def _write_wm(self, body, sid=None):
        path = self._wm_path(sid)
        with open(path, "w") as f:
            f.write(body)
        return path

    def _state_path(self, sid=None):
        return os.path.join(
            self.root, ".serena", "swe-state", f"{sid or self.SID}.state"
        )

    def _write_state(self, data, sid=None):
        d = os.path.join(self.root, ".serena", "swe-state")
        os.makedirs(d, exist_ok=True)
        with open(self._state_path(sid), "w") as f:
            f.write(json.dumps(data))


class TestToolSweWmRead(_FSBase):
    def test_no_session_id_error(self):
        # No explicit id, no env, no WM files -> resolver yields None.
        result = wm.tool_swe_wm_read()
        self.assertIn("error", result)
        self.assertIn("No session_id", result["error"])

    def test_no_state_or_wm_error(self):
        # Valid session id but nothing on disk for it.
        result = wm.tool_swe_wm_read(session_id=self.SID)
        self.assertIn("error", result)
        self.assertIn(self.SID, result["error"])

    def test_state_file_authoritative(self):
        self._write_state({
            "current_state": "WF_EXECUTE",
            "prev_state": "WF_CLASSIFY",
            "task": "Fix the gate",
            "features": ["SWE"],
            "progress": ["did a thing"],
            "return": "WF_VERIFY",
        })
        self._write_wm("# WM\n\nsome content\n")
        result = wm.tool_swe_wm_read(session_id=self.SID)
        self.assertEqual(result["session_id"], self.SID)
        self.assertEqual(result["wm_filepath"], self._wm_path())
        self.assertEqual(result["content"], "# WM\n\nsome content\n")
        state = result["state"]
        self.assertEqual(state["current_state"], "WF_EXECUTE")
        self.assertEqual(state["prev_state"], "WF_CLASSIFY")
        self.assertEqual(state["session_id"], self.SID)
        self.assertEqual(state["task"], "Fix the gate")
        self.assertEqual(state["features"], ["SWE"])
        self.assertEqual(state["progress"], ["did a thing"])
        self.assertEqual(state["return_step"], "WF_VERIFY")

    def test_state_file_only_no_wm_markdown(self):
        # State file exists but no WM markdown -> content empty, wm_filepath "".
        self._write_state({"current_state": "WF_RESEARCH"})
        result = wm.tool_swe_wm_read(session_id=self.SID)
        self.assertEqual(result["content"], "")
        self.assertEqual(result["wm_filepath"], "")
        self.assertEqual(result["state"]["current_state"], "WF_RESEARCH")
        # Missing task/features/progress default sensibly.
        self.assertEqual(result["state"]["task"], "")
        self.assertEqual(result["state"]["features"], [])
        self.assertEqual(result["state"]["progress"], [])


class TestToolSweWmUpdateSection(_FSBase):
    def test_no_wm_file_error(self):
        result = wm.tool_swe_wm_update_section("Notes", "hi", session_id=self.SID)
        self.assertIn("error", result)
        self.assertIn("No WM file", result["error"])

    def test_protected_section_rejected(self):
        # Even with a WM file present, protected sections are refused.
        self._write_wm("# WM\n\n## Transitions\n\nx\n")
        result = wm.tool_swe_wm_update_section("Transitions", "hack", session_id=self.SID)
        self.assertIn("error", result)
        self.assertIn("daemon-managed", result["error"])

    def test_replace_existing_h2_section(self):
        self._write_wm(
            "# WM\n\n## Notes\n\nold note\n\n## Previous Task\n\nnothing\n"
        )
        result = wm.tool_swe_wm_update_section("Notes", "new note", session_id=self.SID)
        self.assertTrue(result["success"])
        self.assertEqual(result["action"], "replaced")
        self.assertEqual(result["section"], "Notes")
        self.assertIn(self.SID, result["summary"])
        with open(self._wm_path()) as f:
            content = f.read()
        self.assertIn("new note", content)
        self.assertNotIn("old note", content)
        # Previous Task section preserved.
        self.assertIn("## Previous Task", content)

    def test_append_to_existing_section(self):
        self._write_wm("# WM\n\n## Notes\n\nfirst\n\n## Previous Task\n\n-\n")
        result = wm.tool_swe_wm_update_section(
            "Notes", "second", session_id=self.SID, append=True
        )
        self.assertEqual(result["action"], "appended")
        with open(self._wm_path()) as f:
            content = f.read()
        self.assertIn("first", content)
        self.assertIn("second", content)
        # first must precede second (append, not replace).
        self.assertLess(content.index("first"), content.index("second"))

    def test_missing_section_inserted_before_previous_task(self):
        self._write_wm("# WM\n\n## Progress\n\n- [x] a\n\n## Previous Task\n\n-\n")
        result = wm.tool_swe_wm_update_section("Files", "file.py", session_id=self.SID)
        self.assertTrue(result["success"])
        with open(self._wm_path()) as f:
            content = f.read()
        self.assertIn("## Files", content)
        self.assertIn("file.py", content)
        # New section inserted before Previous Task.
        self.assertLess(content.index("## Files"), content.index("## Previous Task"))

    def test_missing_section_appended_at_end_when_no_marker(self):
        self._write_wm("# WM\n\n## Progress\n\n- [x] a\n")
        result = wm.tool_swe_wm_update_section("Files", "file.py", session_id=self.SID)
        self.assertTrue(result["success"])
        with open(self._wm_path()) as f:
            content = f.read()
        self.assertIn("## Files", content)
        self.assertTrue(content.rstrip().endswith("file.py"))

    def test_atomic_tmp_file_removed(self):
        self._write_wm("# WM\n\n## Notes\n\nx\n\n## Previous Task\n\n-\n")
        wm.tool_swe_wm_update_section("Notes", "y", session_id=self.SID)
        # os.replace should have consumed the .tmp file.
        self.assertFalse(os.path.exists(self._wm_path() + ".tmp"))

    def test_progress_section_synced_to_state_file(self):
        # A pre-existing state file plus a Progress update -> checked items land
        # in state['progress'] via _sync_section_to_state_file.
        self._write_state({"current_state": "WF_EXECUTE"})
        self._write_wm("# WM\n\n## Progress\n\nold\n\n## Previous Task\n\n-\n")
        wm.tool_swe_wm_update_section(
            "Progress", "- [x] done one\n- [ ] not yet\n- [x] done two",
            session_id=self.SID,
        )
        state = config.read_state_file(self.SID)
        self.assertEqual(state["progress"], ["done one", "done two"])


class TestArchReviewSkipGate(_FSBase):
    """_check_arch_review_skip / tool_swe_wm_update_section wiring:
    `arch_review_skipped: true` is rejected for a multi-ticket Current Task
    that lacks `parallel_agents: true` (USER-APPROVED RULE, mirrors the
    state_manager transition gate)."""

    def test_rejected_when_current_task_in_same_call_is_multi_ticket(self):
        self._write_wm("# WM\n\n## Current Task\n\nold task\n\n## Previous Task\n\n-\n")
        result = wm.tool_swe_wm_update_section(
            "Current Task",
            "Fix SPS-855 and SPS-856\narch_review_skipped: true",
            session_id=self.SID,
        )
        self.assertIn("error", result)
        self.assertIn("separate tickets/jobs", result["error"])
        self.assertIn("WF_ARCH_REVIEW", result["error"])

    def test_allowed_when_parallel_agents_flag_present_in_same_content(self):
        self._write_wm("# WM\n\n## Current Task\n\nold task\n\n## Previous Task\n\n-\n")
        result = wm.tool_swe_wm_update_section(
            "Current Task",
            "Fix SPS-855 and SPS-856\narch_review_skipped: true\nparallel_agents: true",
            session_id=self.SID,
        )
        self.assertTrue(result.get("success"), result)

    def test_allowed_for_single_ticket_task(self):
        self._write_wm("# WM\n\n## Current Task\n\nold task\n\n## Previous Task\n\n-\n")
        result = wm.tool_swe_wm_update_section(
            "Current Task",
            "Fix SPS-855 only\narch_review_skipped: true",
            session_id=self.SID,
        )
        self.assertTrue(result.get("success"), result)

    def test_rejected_using_existing_wm_current_task_when_writing_other_section(self):
        # arch_review_skipped written into e.g. Notes; multi-ticket evidence
        # lives in the WM file's existing Current Task section on disk.
        self._write_wm(
            "# WM\n\n## Current Task\n\nFix SPS-855 and SPS-856\n\n"
            "## Notes\n\nold\n\n## Previous Task\n\n-\n"
        )
        result = wm.tool_swe_wm_update_section(
            "Notes", "arch_review_skipped: true - minor patch", session_id=self.SID
        )
        self.assertIn("error", result)
        self.assertIn("separate tickets/jobs", result["error"])

    def test_allowed_using_existing_wm_parallel_agents_flag(self):
        self._write_wm(
            "# WM\n\n## Current Task\n\nFix SPS-855 and SPS-856\n\n"
            "parallel_agents: true\n\n## Notes\n\nold\n\n## Previous Task\n\n-\n"
        )
        result = wm.tool_swe_wm_update_section(
            "Notes", "arch_review_skipped: true - split across agents", session_id=self.SID
        )
        self.assertTrue(result.get("success"), result)

    def test_no_arch_review_skipped_token_passes_even_if_multi_ticket(self):
        # The gate only fires when the write actually claims the skip.
        self._write_wm("# WM\n\n## Current Task\n\nold\n\n## Previous Task\n\n-\n")
        result = wm.tool_swe_wm_update_section(
            "Current Task", "Fix SPS-855 and SPS-856", session_id=self.SID
        )
        self.assertTrue(result.get("success"), result)

    def test_batched_update_rejects_arch_review_skip_citing_sibling_current_task(self):
        self._write_wm("# WM\n\n## Current Task\n\nold\n\n## Previous Task\n\n-\n")
        result = wm.tool_swe_wm_update(
            session_id=self.SID,
            sections=[
                {"section": "Current Task", "content": "Fix SPS-855 and SPS-856"},
                {"section": "Notes", "content": "arch_review_skipped: true"},
            ],
        )
        self.assertIn("error", result)
        self.assertIn("separate tickets/jobs", result["error"])


class TestToolSweWmUpdateStatus(_FSBase):
    def test_invalid_status_rejected(self):
        self._write_wm("# WM\n\n## Current Task\n\n**[IN_PROGRESS]**: work\n")
        result = wm.tool_swe_wm_update_status("NOPE", session_id=self.SID)
        self.assertIn("error", result)
        self.assertIn("Invalid status", result["error"])

    def test_no_wm_file_error(self):
        result = wm.tool_swe_wm_update_status("COMPLETED", session_id=self.SID)
        self.assertIn("error", result)
        self.assertIn("No WM file", result["error"])

    def test_replaces_existing_status_tag(self):
        self._write_wm("# WM\n\n## Current Task\n\n**[IN_PROGRESS]**: build it\n")
        result = wm.tool_swe_wm_update_status("COMPLETED", session_id=self.SID)
        self.assertTrue(result["success"])
        self.assertEqual(result["old_status"], "IN_PROGRESS")
        self.assertEqual(result["new_status"], "COMPLETED")
        with open(self._wm_path()) as f:
            content = f.read()
        self.assertIn("**[COMPLETED]**:", content)
        self.assertNotIn("**[IN_PROGRESS]**", content)
        # The task text after the tag is preserved.
        self.assertIn("build it", content)

    def test_injects_status_when_no_existing_tag(self):
        self._write_wm("# WM\n\n## Current Task\n\nbuild it, no tag yet\n")
        result = wm.tool_swe_wm_update_status("BLOCKED", session_id=self.SID)
        self.assertTrue(result["success"])
        self.assertIsNone(result["old_status"])
        self.assertEqual(result["new_status"], "BLOCKED")
        with open(self._wm_path()) as f:
            content = f.read()
        self.assertIn("**[BLOCKED]**:", content)

    def test_atomic_tmp_file_removed(self):
        self._write_wm("# WM\n\n## Current Task\n\n**[IN_PROGRESS]**: x\n")
        wm.tool_swe_wm_update_status("FAILED", session_id=self.SID)
        self.assertFalse(os.path.exists(self._wm_path() + ".tmp"))


class TestToolSweWmList(_FSBase):
    def test_empty_when_no_wm_files(self):
        result = wm.tool_swe_wm_list()
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["wm_files"], [])

    def test_lists_and_sorts_newest_first(self):
        older = self._write_wm("# old\n", sid="aaaaaaaa")
        newer = self._write_wm("# new\n", sid="bbbbbbbb")
        os.utime(older, (1000, 1000))
        os.utime(newer, (2000, 2000))
        result = wm.tool_swe_wm_list()
        self.assertEqual(result["count"], 2)
        # Newest first.
        self.assertEqual(result["wm_files"][0]["session_id"], "bbbbbbbb")
        self.assertEqual(result["wm_files"][1]["session_id"], "aaaaaaaa")
        first = result["wm_files"][0]
        self.assertEqual(first["filename"], "WM_bbbbbbbb.md")
        self.assertEqual(first["filepath"], newer)
        # modified is a formatted 'YYYY-MM-DD HH:MM' string.
        self.assertRegex(first["modified"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")


# ──────────────────────────────────────────────────────────────────
# _sync_section_to_state_file — direct unit tests
# ──────────────────────────────────────────────────────────────────

class TestSyncSectionToStateFile(_FSBase):
    def test_no_state_file_is_noop(self):
        # No state file -> read_state_file None -> early return, no crash.
        wm._sync_section_to_state_file(self.SID, "Progress", "- [x] a")
        self.assertIsNone(config.read_state_file(self.SID))

    def test_current_task_prefers_explicit_task_line(self):
        self._write_state({"current_state": "WF_EXECUTE"})
        content = (
            "- **Feature(s)**: FORMS\n"
            "- **Complexity**: minor\n"
            "- **Task**: Actually do the thing\n"
        )
        wm._sync_section_to_state_file(self.SID, "Current Task", content)
        state = config.read_state_file(self.SID)
        self.assertEqual(state["task"], "Actually do the thing")

    def test_current_task_skips_metadata_bullets(self):
        # No explicit **Task**: line -> first non-metadata, non-heading line wins.
        self._write_state({"current_state": "WF_EXECUTE"})
        content = (
            "- **Feature(s)**: FORMS\n"
            "- **Complexity**: minor\n"
            "Fix the deadlock in the gate\n"
        )
        wm._sync_section_to_state_file(self.SID, "Current Task", content)
        state = config.read_state_file(self.SID)
        self.assertEqual(state["task"], "Fix the deadlock in the gate")

    def test_current_task_no_meaningful_line_leaves_task_unchanged(self):
        # Only metadata bullets -> no task_summary -> existing task preserved.
        self._write_state({"current_state": "WF_EXECUTE", "task": "original"})
        content = "- **Feature(s)**: FORMS\n- **Status**: open\n"
        wm._sync_section_to_state_file(self.SID, "Current Task", content)
        state = config.read_state_file(self.SID)
        self.assertEqual(state["task"], "original")

    def test_affected_features_extracted(self):
        self._write_state({"current_state": "WF_EXECUTE"})
        content = "- **Primary**: FORMS\n- **Secondary**: AUTH\n"
        wm._sync_section_to_state_file(self.SID, "Affected Features", content)
        state = config.read_state_file(self.SID)
        self.assertEqual(state["features"], ["FORMS", "AUTH"])

    def test_progress_checked_items_extracted(self):
        self._write_state({"current_state": "WF_EXECUTE"})
        content = "- [x] one\n- [ ] two\n- [x] three\n"
        wm._sync_section_to_state_file(self.SID, "Progress", content)
        state = config.read_state_file(self.SID)
        self.assertEqual(state["progress"], ["one", "three"])

    def test_progress_no_checked_items_leaves_state_unchanged(self):
        self._write_state({"current_state": "WF_EXECUTE", "progress": ["kept"]})
        wm._sync_section_to_state_file(self.SID, "Progress", "- [ ] a\n- [ ] b")
        state = config.read_state_file(self.SID)
        self.assertEqual(state["progress"], ["kept"])


if __name__ == "__main__":
    unittest.main()


class TestToolSweWmUpdate(_FSBase):
    """Batched update: status + ordered sections in one call."""

    WM_BODY = (
        "# Working Memory: Session abcd1234\n\n"
        "## Current Task\n**[IN_PROGRESS]**: initial\n\n"
        "## Progress\n- [ ] start\n\n"
        "## Workflow Context\n**Current State**: WF_EXECUTE\n"
    )

    def test_no_session_id_error(self):
        result = wm.tool_swe_wm_update(sections=[{"section": "Progress", "content": "x"}])
        self.assertIn("error", result)

    def test_nothing_to_do_error(self):
        self._write_wm(self.WM_BODY)
        result = wm.tool_swe_wm_update(session_id=self.SID)
        self.assertIn("error", result)
        self.assertIn("Nothing to do", result["error"])

    def test_status_and_sections_applied_in_one_call(self):
        self._write_wm(self.WM_BODY)
        self._write_state({"current_state": "WF_EXECUTE", "prev_state": "WF_CLASSIFY"})
        result = wm.tool_swe_wm_update(
            session_id=self.SID,
            status="COMPLETED",
            sections=[
                {"section": "Progress", "content": "- [x] done"},
                {"section": "Notes", "content": "- a note", "append": True},
            ],
        )
        self.assertTrue(result.get("success"))
        self.assertEqual(len(result["applied"]), 3)
        self.assertIn("Progress replaced", result["applied"])
        self.assertIn("Notes appended", result["applied"])
        self.assertEqual(result["state"]["current_state"], "WF_EXECUTE")
        self.assertIn("; ", result["summary"])  # single-line combined summary
        with open(self._wm_path()) as f:
            body = f.read()
        self.assertIn("**[COMPLETED]**:", body)
        self.assertIn("- [x] done", body)
        self.assertIn("- a note", body)

    def test_sections_only_call_is_valid(self):
        self._write_wm(self.WM_BODY)
        result = wm.tool_swe_wm_update(
            session_id=self.SID,
            sections=[{"section": "Files", "content": "- file.py"}],
        )
        self.assertTrue(result.get("success"))
        self.assertEqual(result["applied"], ["Files replaced"])

    def test_stops_at_first_error_and_reports_applied(self):
        self._write_wm(self.WM_BODY)
        result = wm.tool_swe_wm_update(
            session_id=self.SID,
            sections=[
                {"section": "Progress", "content": "- [x] one"},
                {"section": "Workflow Context", "content": "hax"},
                {"section": "Notes", "content": "never applied"},
            ],
        )
        self.assertIn("error", result)
        self.assertIn("Workflow Context", result["error"])
        self.assertEqual(result["applied"], ["Progress replaced"])
        with open(self._wm_path()) as f:
            body = f.read()
        self.assertIn("- [x] one", body)
        self.assertNotIn("never applied", body)

    def test_malformed_section_spec_error(self):
        self._write_wm(self.WM_BODY)
        result = wm.tool_swe_wm_update(
            session_id=self.SID, sections=[{"content": "no section key"}]
        )
        self.assertIn("error", result)
        self.assertIn("sections[0]", result["error"])

    def test_registered_in_tool_registry(self):
        self.assertIn("swe_wm_update", wm.TOOL_REGISTRY)
        self.assertIs(wm.TOOL_REGISTRY["swe_wm_update"], wm.tool_swe_wm_update)


# ──────────────────────────────────────────────────────────────────
# End-to-end ❌ headline — real TOOL_REGISTRY through handle_tools_call
# ──────────────────────────────────────────────────────────────────

class TestErrorHeadlineEndToEnd(_FSBase):
    """Representative error cases through the REAL registry (not a fake),
    proving the ❌ WM[<session>] headline renders as line 1 of tools/call
    output for every swe-wm tool that can fail, with the JSON body intact
    after the blank-line separator.
    """

    def _first_line_and_body(self, result):
        text = result["content"][0]["text"]
        headline, _, json_body = text.partition("\n\n")
        return headline, json.loads(json_body)

    def test_sweep_verification_failure(self):
        self._write_wm(
            "# WM\n\n## Current Task\n\n**[IN_PROGRESS]**:\n\n"
            "## Affected Features\n\nold\n\n## Previous Task\n\n-\n"
        )
        stream_path = wm.get_stream_path(self.SID)
        # Surface a docpending link from the primary feature (never read),
        # then attempt an Affected Features write that lists no memories at
        # all read for it — reproduces the "Sweep verification FAILED" error.
        wm.append_event(
            stream_path, 'docpending',
            new=['ref/REF_RELATED'], source='feature/feature_swe',
        )
        content = (
            "- **Primary**: SWE - fix the thing\n"
            "- **Memories loaded**: feature/feature_swe\n"
        )
        result = wm.handle_tools_call({
            "name": "swe_wm_update_section",
            "arguments": {
                "session_id": self.SID,
                "section": "Affected Features",
                "content": content,
            },
        })
        headline, body = self._first_line_and_body(result)
        self.assertTrue(
            headline.startswith(f"❌ WM[{self.SID}] swe_wm_update_section (Affected Features): "),
            headline,
        )
        self.assertIn("Sweep verification FAILED", headline)
        self.assertIn("Sweep verification FAILED", body["error"])
        self.assertLessEqual(len(headline), 121)

    def test_bad_status_rejected(self):
        self._write_wm("# WM\n\n## Current Task\n\n**[IN_PROGRESS]**:\n")
        result = wm.handle_tools_call({
            "name": "swe_wm_update_status",
            "arguments": {"session_id": self.SID, "status": "NOT_A_REAL_STATUS"},
        })
        headline, body = self._first_line_and_body(result)
        self.assertTrue(
            headline.startswith(
                f"❌ WM[{self.SID}] swe_wm_update_status "
                "(NOT_A_REAL_STATUS): Invalid status "
            ),
            headline,
        )
        self.assertIn("Invalid status", body["error"])

    def test_missing_wm_file(self):
        # No WM written for this session at all.
        result = wm.handle_tools_call({
            "name": "swe_wm_update_section",
            "arguments": {
                "session_id": self.SID,
                "section": "Notes",
                "content": "hi",
            },
        })
        headline, body = self._first_line_and_body(result)
        self.assertEqual(
            headline,
            f"❌ WM[{self.SID}] swe_wm_update_section (Notes): "
            f"No WM file found for session {self.SID}",
        )
        self.assertIn("No WM file", body["error"])

    def test_protected_section_rejected(self):
        self._write_wm("# WM\n\n## Transitions\n\nx\n")
        result = wm.handle_tools_call({
            "name": "swe_wm_update_section",
            "arguments": {
                "session_id": self.SID,
                "section": "Transitions",
                "content": "hack",
            },
        })
        headline, body = self._first_line_and_body(result)
        self.assertTrue(
            headline.startswith(
                f"❌ WM[{self.SID}] swe_wm_update_section (Transitions): "
            ),
            headline,
        )
        self.assertIn("daemon-managed", headline)
        self.assertIn("daemon-managed", body["error"])

    def test_no_session_id_available(self):
        # No explicit id, no env, no WM -> resolver yields None inside the tool.
        result = wm.handle_tools_call({
            "name": "swe_wm_read", "arguments": {},
        })
        headline, body = self._first_line_and_body(result)
        # The real "no session_id" error message is long — the headline
        # truncates it with an ellipsis to stay under the ~120-char budget.
        self.assertTrue(
            headline.startswith("❌ WM[—] swe_wm_read: No session_id "
                                 "provided and no SWE_SESSION_ID env var set"),
            headline,
        )
        self.assertTrue(headline.endswith("…"))
        self.assertLessEqual(len(headline), 121)
        self.assertIn("No session_id", body["error"])


# ──────────────────────────────────────────────────────────────────
# D2 sweep idempotence — session-wide docread ledger through the real tool
# ──────────────────────────────────────────────────────────────────

class TestSweepSessionWindowWiring(_FSBase):
    """D2: the loaded-list verification window is the WHOLE session stream.
    A reclassify after WF_DONE stamps a new task boundary, but prior-turn
    docreads still satisfy the follow-up task's Affected Features write —
    zero re-reads required. (Docpending accounting keeps its since-sweep
    window; only the loaded-list ledger is session-wide.)
    """

    WM_BODY = (
        "# WM\n\n## Current Task\n\n**[IN_PROGRESS]**: x\n\n"
        "## Affected Features\n\n(tbd)\n\n## Previous Task\n\n-\n"
    )

    def test_prior_task_reads_satisfy_follow_up_sweep(self):
        self._write_wm(self.WM_BODY)
        path = wm.get_stream_path(self.SID)
        wm.append_event(path, "session_start", s=self.SID)
        wm.append_event(path, "docread", name="feature/FEATURE_X")
        # Reclassify after WF_DONE: new task boundary, ZERO re-reads after.
        wm.append_event(path, "state", from_s="WF_DONE", to_s="WF_CLASSIFY",
                        s=self.SID)
        result = wm.tool_swe_wm_update_section(
            "Affected Features",
            "- **Memories loaded**: feature/FEATURE_X",
            session_id=self.SID)
        self.assertTrue(result.get("success"), result)
        self.assertTrue(os.path.exists(
            wm.get_feature_sentinel_path(self.SID, "sweep")))

    def test_never_read_name_still_rejected_with_session_wording(self):
        self._write_wm(self.WM_BODY)
        path = wm.get_stream_path(self.SID)
        wm.append_event(path, "session_start", s=self.SID)
        wm.append_event(path, "docread", name="feature/FEATURE_X")
        result = wm.tool_swe_wm_update_section(
            "Affected Features",
            "- **Memories loaded**: feature/FEATURE_X, dom/DOM_NEVER_READ",
            session_id=self.SID)
        self.assertIn("error", result)
        self.assertIn("never read this session", result["error"])
        self.assertIn("Prior-turn reads count; do not re-read",
                      result["error"])


# ──────────────────────────────────────────────────────────────────
# Change Set H — obligation-digest disposition parsing + sweep wiring
# ──────────────────────────────────────────────────────────────────

class TestParseRulesPlanned(unittest.TestCase):
    def test_absent_line_returns_empty(self):
        self.assertEqual(wm._parse_rules_planned("no line here"), set())

    def test_comma_separated_names(self):
        content = "- **Rules planned**: dom/DOM_X, ref/REF_Y\n"
        self.assertEqual(wm._parse_rules_planned(content),
                         {"dom/dom_x", "ref/ref_y"})

    def test_multiple_lines_all_honored(self):
        content = ("- **Rules planned**: dom/DOM_X\n"
                   "- **Rules planned**: ref/REF_Y\n")
        self.assertEqual(wm._parse_rules_planned(content),
                         {"dom/dom_x", "ref/ref_y"})


class TestParseRulesRuledOut(unittest.TestCase):
    def test_absent_line_returns_empty(self):
        self.assertEqual(wm._parse_ruled_out("no line here"), {})

    def test_em_dash_reason_captured(self):
        content = "- **Rules ruled out**: ref/REF_X — not applicable\n"
        self.assertEqual(wm._parse_ruled_out(content),
                         {"ref/ref_x": "not applicable"})

    def test_multiple_entries_comma_separated(self):
        content = ("- **Rules ruled out**: ref/REF_X — not applicable, "
                   "dom/DOM_Y — superseded\n")
        result = wm._parse_ruled_out(content)
        self.assertEqual(result["ref/ref_x"], "not applicable")
        self.assertEqual(result["dom/dom_y"], "superseded")

    def test_bare_name_no_reason_has_empty_reason(self):
        content = "- **Rules ruled out**: ref/REF_X\n"
        self.assertEqual(wm._parse_ruled_out(content), {"ref/ref_x": ""})

    def test_multiple_lines_all_honored(self):
        content = ("- **Rules ruled out**: ref/REF_X — reason one\n"
                   "- **Rules ruled out**: dom/DOM_Y — reason two\n")
        result = wm._parse_ruled_out(content)
        self.assertEqual(set(result.keys()), {"ref/ref_x", "dom/dom_y"})
        self.assertTrue(all(result.values()))

    def test_multiple_entries_semicolon_separated(self):
        # ';' must be accepted as an entry separator alongside ',' — a
        # single '**Rules ruled out**:' line with two em-dash-reasoned
        # entries joined by ';' must parse as two distinct entries.
        content = ("- **Rules ruled out**: ref/REF_A — reason one; "
                   "ref/REF_B — reason two\n")
        result = wm._parse_ruled_out(content)
        self.assertEqual(set(result.keys()), {"ref/ref_a", "ref/ref_b"})
        self.assertEqual(result["ref/ref_a"], "reason one")
        self.assertEqual(result["ref/ref_b"], "reason two")


class TestCitedMemNames(unittest.TestCase):
    def test_citations_inside_checklist_captured(self):
        content = ("## Compliance Checklist\n"
                   "- [ ] mem:dom/dom_x done\n"
                   "- [ ] mem:ref/ref_y\n")
        self.assertEqual(wm._cited_mem_names(content),
                         {"dom/dom_x", "ref/ref_y"})

    def test_citations_outside_checklist_ignored(self):
        content = "## Notes\nmem:dom/dom_x mentioned here, not in checklist\n"
        self.assertEqual(wm._cited_mem_names(content), set())

    def test_no_checklist_section_returns_empty(self):
        self.assertEqual(wm._cited_mem_names("no checklist here"), set())


class TestCheckMemorySweepDispositions(unittest.TestCase):
    """_check_memory_sweep: Rules planned / Rules ruled out dispositions."""

    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        self.session = "dispotest"
        self.stream_path = os.path.join(self.tmp.name, f"{self.session}.jsonl")
        self._orig_stream_path = wm.get_stream_path
        self._orig_sentinel = wm.get_feature_sentinel_path
        self._orig_root = config._PROJECT_ROOT
        wm.get_stream_path = lambda sid: os.path.join(self.tmp.name, f"{sid}.jsonl")
        wm.get_feature_sentinel_path = (
            lambda sid, gate: os.path.join(self.tmp.name, f".{gate}_feature_{sid}"))
        # No WM file on disk for these tests unless explicitly created —
        # find_working_memory_for_session then returns None and the citation
        # lookup falls back to other_sections / current content only.
        config._PROJECT_ROOT = self.tmp.name

    def tearDown(self):
        wm.get_stream_path = self._orig_stream_path
        wm.get_feature_sentinel_path = self._orig_sentinel
        config._PROJECT_ROOT = self._orig_root
        self.tmp.cleanup()
        reset_caches()

    def _write_stream(self, events):
        with open(self.stream_path, "w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")

    def _sentinel(self):
        return os.path.join(self.tmp.name, f".sweep_feature_{self.session}")

    def test_planned_cited_in_same_content_passes_and_creates_sentinel(self):
        self._write_stream([
            {"type": "docread", "name": "feature/FEATURE_X"},
            {"type": "docpending", "new": ["dom/dom_planned"]},
        ])
        content = (
            "- **Memories loaded**: feature/FEATURE_X\n"
            "- **Rules planned**: dom/DOM_PLANNED\n"
            "## Compliance Checklist\n"
            "- [ ] mem:dom/dom_planned addressed\n"
        )
        err = wm._check_memory_sweep(self.session, content)
        self.assertIsNone(err)
        self.assertTrue(os.path.exists(self._sentinel()))
        with open(self._sentinel()) as f:
            self.assertEqual(json.load(f)["planned"], ["dom/dom_planned"])

    def test_planned_uncited_rejected(self):
        self._write_stream([
            {"type": "docread", "name": "feature/FEATURE_X"},
        ])
        content = (
            "- **Memories loaded**: feature/FEATURE_X\n"
            "- **Rules planned**: dom/DOM_PLANNED\n"
        )
        err = wm._check_memory_sweep(self.session, content)
        self.assertIsNotNone(err)
        self.assertIn("dom/dom_planned", err)
        self.assertIn("Compliance Checklist", err)
        self.assertFalse(os.path.exists(self._sentinel()))

    def test_planned_cited_in_other_sections_passes(self):
        self._write_stream([
            {"type": "docread", "name": "feature/FEATURE_X"},
        ])
        content = (
            "- **Memories loaded**: feature/FEATURE_X\n"
            "- **Rules planned**: dom/DOM_PLANNED\n"
        )
        other_sections = [{
            "section": "Notes",
            "content": "## Compliance Checklist\n- [ ] mem:dom/dom_planned\n",
        }]
        err = wm._check_memory_sweep(self.session, content, other_sections=other_sections)
        self.assertIsNone(err)
        self.assertTrue(os.path.exists(self._sentinel()))

    def test_ruled_out_with_reason_passes(self):
        self._write_stream([
            {"type": "docread", "name": "feature/FEATURE_X"},
        ])
        content = (
            "- **Memories loaded**: feature/FEATURE_X\n"
            "- **Rules ruled out**: ref/REF_X — not applicable to this task\n"
        )
        err = wm._check_memory_sweep(self.session, content)
        self.assertIsNone(err)
        with open(self._sentinel()) as f:
            self.assertEqual(json.load(f)["ruled_out"], ["ref/ref_x"])

    def test_ruled_out_without_reason_rejected(self):
        self._write_stream([
            {"type": "docread", "name": "feature/FEATURE_X"},
        ])
        content = (
            "- **Memories loaded**: feature/FEATURE_X\n"
            "- **Rules ruled out**: ref/REF_X\n"
        )
        err = wm._check_memory_sweep(self.session, content)
        self.assertIsNotNone(err)
        self.assertIn("ref/ref_x", err)
        self.assertFalse(os.path.exists(self._sentinel()))

    def test_docpending_satisfied_by_planned(self):
        self._write_stream([
            {"type": "docread", "name": "feature/FEATURE_X"},
            {"type": "docpending", "new": ["dom/dom_planned"],
             "src": "feature/feature_paused"},
        ])
        content = (
            "- **Primary**: X - working feature\n"
            "- **Memories loaded**: feature/FEATURE_X\n"
            "- **Rules planned**: dom/DOM_PLANNED\n"
            "## Compliance Checklist\n- [ ] mem:dom/dom_planned\n"
        )
        err = wm._check_memory_sweep(self.session, content)
        self.assertIsNone(err)

    def test_docpending_satisfied_by_ruled_out(self):
        self._write_stream([
            {"type": "docread", "name": "feature/FEATURE_X"},
            {"type": "docpending", "new": ["ref/ref_cold"],
             "src": "feature/feature_paused"},
        ])
        content = (
            "- **Primary**: X - working feature\n"
            "- **Memories loaded**: feature/FEATURE_X\n"
            "- **Rules ruled out**: ref/REF_COLD — not relevant here\n"
        )
        err = wm._check_memory_sweep(self.session, content)
        self.assertIsNone(err)

    def test_absent_new_lines_behavior_unchanged(self):
        # No 'Rules planned'/'Rules ruled out' lines at all — identical to
        # pre-Change-Set-H behavior (full backward compatibility).
        self._write_stream([
            {"type": "docread", "name": "feature/FEATURE_X"},
        ])
        content = "- **Memories loaded**: feature/FEATURE_X\n"
        err = wm._check_memory_sweep(self.session, content)
        self.assertIsNone(err)
        with open(self._sentinel()) as f:
            sentinel = json.load(f)
        self.assertEqual(sentinel["planned"], [])
        self.assertEqual(sentinel["ruled_out"], [])

    def test_planned_cited_in_headingless_sibling_compliance_spec_passes(self):
        # Real shape sent by swe_wm_update: a sibling section spec whose
        # `section` IS "Compliance Checklist" but whose `content` has no
        # '## Compliance Checklist' heading of its own (the heading is
        # implied by the section name). The citation inside it must still
        # count via `_mem_citations` (not just `_cited_mem_names`, which
        # requires a heading to find the body).
        self._write_stream([
            {"type": "docread", "name": "feature/FEATURE_X"},
        ])
        content = (
            "- **Memories loaded**: feature/FEATURE_X\n"
            "- **Rules planned**: ref/REF_P\n"
        )
        other_sections = [{
            "section": "Compliance Checklist",
            "content": "- [ ] x (mem:ref/REF_P)\n",
        }]
        err = wm._check_memory_sweep(self.session, content, other_sections=other_sections)
        self.assertIsNone(err)
        with open(self._sentinel()) as f:
            self.assertEqual(json.load(f)["planned"], ["ref/ref_p"])

    def test_headingless_sibling_spec_of_different_section_not_credited(self):
        # A heading-less sibling spec for a DIFFERENT section (e.g. "Context")
        # must NOT be scanned for bare `mem:<name>` citations — only a spec
        # whose `section` is literally "Compliance Checklist" gets that
        # treatment; any other section still requires an actual
        # '## Compliance Checklist' heading inside its own content.
        self._write_stream([
            {"type": "docread", "name": "feature/FEATURE_X"},
        ])
        content = (
            "- **Memories loaded**: feature/FEATURE_X\n"
            "- **Rules planned**: ref/REF_P\n"
        )
        other_sections = [{
            "section": "Context",
            "content": "mem:ref/REF_P mentioned here, no checklist heading\n",
        }]
        err = wm._check_memory_sweep(self.session, content, other_sections=other_sections)
        self.assertIsNotNone(err)
        self.assertIn("ref/ref_p", err)
        self.assertFalse(os.path.exists(self._sentinel()))

    def test_two_primary_docpending_links_ruled_out_semicolon_separated_passes(self):
        # Two primary-surfaced docpending links, both ruled out on one line
        # joined by ';', each with its own em-dash reason.
        self._write_stream([
            {"type": "docread", "name": "feature/FEATURE_X"},
            {"type": "docpending", "new": ["ref/ref_a", "ref/ref_b"],
             "src": "feature/feature_x"},
        ])
        content = (
            "- **Primary**: X - the working feature\n"
            "- **Memories loaded**: feature/FEATURE_X\n"
            "- **Rules ruled out**: ref/REF_A — reason one; "
            "ref/REF_B — reason two\n"
        )
        err = wm._check_memory_sweep(self.session, content)
        self.assertIsNone(err)
        with open(self._sentinel()) as f:
            self.assertEqual(
                set(json.load(f)["ruled_out"]), {"ref/ref_a", "ref/ref_b"})

    def test_primary_link_rejection_error_lists_parsed_ruled_out(self):
        # The primary-link rejection error must append a "Parsed as ruled
        # out: ..." trailer naming what was actually parsed, so the agent
        # can see why a name it thought it ruled out is still outstanding.
        self._write_stream([
            {"type": "docread", "name": "feature/FEATURE_X"},
            {"type": "docpending", "new": ["dom/dom_hub_child", "ref/ref_a"],
             "src": "feature/feature_x"},
        ])
        content = (
            "- **Primary**: X - the working feature\n"
            "- **Memories loaded**: feature/FEATURE_X\n"
            "- **Rules ruled out**: ref/REF_A — reason one\n"
        )
        err = wm._check_memory_sweep(self.session, content)
        self.assertIsNotNone(err)
        self.assertIn("Parsed as ruled out:", err)
        self.assertIn("ref/ref_a", err)


class TestUpdateSectionOtherSectionsWiring(_FSBase):
    """tool_swe_wm_update threads sibling section specs through to the sweep
    check as `other_sections`, so a Compliance Checklist written in the SAME
    batched call satisfies a Rules-planned citation before anything lands
    on disk."""

    WM_BODY = (
        "# WM\n\n## Current Task\n\n**[IN_PROGRESS]**: x\n\n"
        "## Affected Features\n\n(tbd)\n\n## Previous Task\n\n-\n"
    )

    def test_checklist_in_sibling_section_same_call_satisfies_citation(self):
        self._write_wm(self.WM_BODY)
        path = wm.get_stream_path(self.SID)
        wm.append_event(path, "docread", name="feature/FEATURE_X")
        result = wm.tool_swe_wm_update(
            session_id=self.SID,
            sections=[
                {"section": "Notes",
                 "content": "## Compliance Checklist\n- [ ] mem:dom/dom_planned\n"},
                {"section": "Affected Features",
                 "content": ("- **Memories loaded**: feature/FEATURE_X\n"
                             "- **Rules planned**: dom/DOM_PLANNED\n")},
            ])
        self.assertTrue(result.get("success"), result)
        self.assertTrue(os.path.exists(
            wm.get_feature_sentinel_path(self.SID, "sweep")))

    def test_checklist_missing_everywhere_rejected(self):
        self._write_wm(self.WM_BODY)
        path = wm.get_stream_path(self.SID)
        wm.append_event(path, "docread", name="feature/FEATURE_X")
        result = wm.tool_swe_wm_update(
            session_id=self.SID,
            sections=[
                {"section": "Affected Features",
                 "content": ("- **Memories loaded**: feature/FEATURE_X\n"
                             "- **Rules planned**: dom/DOM_PLANNED\n")},
            ])
        self.assertIn("error", result)
        self.assertIn("dom/dom_planned", result["error"])


class TestToolSweWmTransition(_FSBase):
    """swe_wm_transition — the ONLY MCP way to change Current State."""

    WM_BODY = (
        "# Working Memory: Session abcd1234\n\n"
        "## Current Task\n**[IN_PROGRESS]**: research\n\n"
        "## Workflow Context\n**Current State**: WF_RESEARCH\n"
    )

    def test_no_session_id_error(self):
        result = wm.tool_swe_wm_transition(target_state="WF_CLASSIFY", reason="done")
        self.assertIn("error", result)
        self.assertIn("No session_id", result["error"])

    def test_empty_reason_rejected(self):
        self._write_wm(self.WM_BODY)
        result = wm.tool_swe_wm_transition(target_state="WF_CLASSIFY", reason="",
                                            session_id=self.SID)
        self.assertIn("error", result)
        self.assertIn("reason", result["error"])

    def test_whitespace_only_reason_rejected(self):
        self._write_wm(self.WM_BODY)
        result = wm.tool_swe_wm_transition(target_state="WF_CLASSIFY", reason="   ",
                                            session_id=self.SID)
        self.assertIn("error", result)
        self.assertIn("reason", result["error"])

    def test_subflow_target_rejected(self):
        self._write_wm(self.WM_BODY)
        result = wm.tool_swe_wm_transition(target_state="WF_INIT", reason="oops",
                                            session_id=self.SID)
        self.assertFalse(result.get("success", False))
        self.assertIn("subflow", result["error"])

    def test_unknown_target_rejected(self):
        self._write_wm(self.WM_BODY)
        result = wm.tool_swe_wm_transition(target_state="WF_NOT_REAL", reason="oops",
                                            session_id=self.SID)
        self.assertFalse(result.get("success", False))
        self.assertIn("Unknown state", result["error"])

    def test_declared_transition_succeeds_and_returns_new_state(self):
        self._write_wm(self.WM_BODY)
        self._write_state({"current_state": "WF_RESEARCH", "prev_state": "WF_CLASSIFY"})
        result = wm.tool_swe_wm_transition(
            target_state="WF_CLASSIFY", reason="needs_implementation",
            session_id=self.SID)
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result["previous_state"], "WF_RESEARCH")
        self.assertEqual(result["new_state"], "WF_CLASSIFY")
        self.assertEqual(result["reason"], "needs_implementation")
        self.assertIn("summary", result)
        state = config.read_state_file(self.SID)
        self.assertEqual(state["current_state"], "WF_CLASSIFY")

    def test_invalid_transition_rejected_without_force(self):
        self._write_wm(self.WM_BODY)
        self._write_state({"current_state": "WF_RESEARCH", "prev_state": "WF_CLASSIFY"})
        result = wm.tool_swe_wm_transition(
            target_state="WF_EXECUTE", reason="skip ahead", session_id=self.SID)
        self.assertFalse(result.get("success", False))

    def test_invalid_transition_accepted_with_force(self):
        self._write_wm(self.WM_BODY)
        self._write_state({"current_state": "WF_RESEARCH", "prev_state": "WF_CLASSIFY"})
        result = wm.tool_swe_wm_transition(
            target_state="WF_EXECUTE", reason="skip ahead", session_id=self.SID,
            force=True)
        self.assertTrue(result.get("success"), result)
        self.assertTrue(result["forced"])
        self.assertEqual(result["new_state"], "WF_EXECUTE")

    def test_registered_in_tool_definitions_and_registry(self):
        names = {t["name"] for t in wm.TOOL_DEFINITIONS}
        self.assertIn("swe_wm_transition", names)
        self.assertIn("swe_wm_transition", wm.TOOL_REGISTRY)
        self.assertIs(wm.TOOL_REGISTRY["swe_wm_transition"], wm.tool_swe_wm_transition)
