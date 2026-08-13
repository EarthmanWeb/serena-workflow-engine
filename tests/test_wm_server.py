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
    def test_lists_the_five_wm_tools(self):
        names = {t["name"] for t in wm.TOOL_DEFINITIONS}
        self.assertEqual(
            names,
            {"swe_wm_read", "swe_wm_update", "swe_wm_update_section",
             "swe_wm_list", "swe_wm_update_status"},
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
        # If the result dict has an 'error' key, JSON is emitted even when a
        # summary is present (the summary branch requires NOT result.get('error')).
        wm.TOOL_REGISTRY = {
            "fake": lambda **kw: {"summary": "should be ignored", "error": "boom"}
        }
        result = wm.handle_tools_call({"name": "fake", "arguments": {}})
        self.assertNotIn("isError", result)
        parsed = json.loads(result["content"][0]["text"])
        self.assertEqual(parsed["error"], "boom")

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
