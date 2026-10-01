"""Tests for the prompt / stop / session hooks.

Targets:
  - prompt/swe_user_prompt_workflow : analyze_prompt() + pattern-list constants
    + regression guard for the prompt_lower fix in main().
  - stop/swe_stop_continue_working   : state-set + threshold constants, the three
    compiled regexes, and extract_last_assistant_text().
  - session/swe_session_end          : cleanup_sentinels() + mark_wm_abandoned().

Stdlib unittest only; deterministic and fully offline. All IO happens inside a
tempfile.TemporaryDirectory with explicit path params — no get_project_root
monkeypatching is needed here because every tested function takes its path
directly.
"""
import inspect
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_hook  # noqa: E402


# ---------------------------------------------------------------------------
# prompt/swe_user_prompt_workflow
# ---------------------------------------------------------------------------
class TestAnalyzePrompt(unittest.TestCase):
    mod = import_hook("prompt/swe_user_prompt_workflow")

    # --- continuation branch ---
    def test_continuation_affirmation_prefix(self):
        for p in ("yes", "okay", "sure, go ahead", "continue with this",
                  "sounds good", "please continue", "approved"):
            self.assertEqual(
                self.mod.analyze_prompt(p, "WF_EXECUTE"), "continuation", p)

    def test_continuation_latest_version_phrase(self):
        # The exact phrase called out in the task: matches the
        # "(you should|should be|latest version|already committed)" pattern.
        self.assertEqual(
            self.mod.analyze_prompt("okay, you should have the latest",
                                    "WF_EXECUTE"),
            "continuation",
        )

    def test_continuation_status_question(self):
        self.assertEqual(
            self.mod.analyze_prompt("is that fixed now?", "WF_VERIFY"),
            "continuation",
        )

    # --- addition branch ---
    def test_addition_also_prefix(self):
        self.assertEqual(
            self.mod.analyze_prompt("also remove the old file", "WF_EXECUTE"),
            "addition",
        )

    def test_addition_can_you_also(self):
        self.assertEqual(
            self.mod.analyze_prompt("can you also update the README",
                                    "WF_EXECUTE"),
            "addition",
        )

    def test_addition_remove_change_prefix(self):
        self.assertEqual(
            self.mod.analyze_prompt("change the timeout value", "WF_EXECUTE"),
            "addition",
        )

    # --- new_task branch (unambiguous openers, any state) ---
    def test_new_task_help_me_prefix(self):
        self.assertEqual(
            self.mod.analyze_prompt("help me build a parser", "WF_EXECUTE"),
            "new_task",
        )

    def test_new_task_explicit_new_task_prefix(self):
        self.assertEqual(
            self.mod.analyze_prompt("new task: set up CI", "WF_EXECUTE"),
            "new_task",
        )

    def test_new_task_unambiguous_openers_from_active_state(self):
        for p in ("switch to the district theme",
                  "let's work on the calendar", "i need you to onboard a repo"):
            self.assertEqual(
                self.mod.analyze_prompt(p, "WF_EXECUTE"), "new_task", p)

    # --- state-aware bare-verb split ---
    def test_bare_verb_is_new_task_when_no_active_task(self):
        # No task in flight (classify/init/done) -> a bare verb IS the task.
        for state in ("WF_CLASSIFY", "WF_INIT", "WF_DONE", None):
            for p in ("create a new feature", "build the login page",
                      "fix the bug", "refactor this module"):
                self.assertEqual(
                    self.mod.analyze_prompt(p, state), "new_task",
                    f"{p!r} @ {state}")

    def test_bare_verb_is_possible_pivot_mid_task(self):
        # Mid-task a bare verb is NOT force-classified -- the model decides.
        for p in ("create a new feature", "build the login page",
                  "fix the bug", "refactor this module",
                  "fix the login page instead"):
            self.assertEqual(
                self.mod.analyze_prompt(p, "WF_EXECUTE"), "possible_pivot", p)

    # --- unknown fallback ---
    def test_unknown_fallback(self):
        # A plain declarative statement matching none of the pattern lists.
        for p in ("the server returns a 500 on that endpoint",
                  "here is the stack trace from production"):
            self.assertEqual(
                self.mod.analyze_prompt(p, "WF_EXECUTE"), "unknown", p)

    def test_empty_prompt_is_unknown(self):
        self.assertEqual(self.mod.analyze_prompt("", "WF_EXECUTE"), "unknown")

    def test_whitespace_prompt_is_unknown(self):
        self.assertEqual(self.mod.analyze_prompt("   \n\t ", "WF_EXECUTE"),
                         "unknown")

    def test_case_insensitive(self):
        # Uppercased continuation still classifies as continuation.
        self.assertEqual(
            self.mod.analyze_prompt("YES", "WF_EXECUTE"), "continuation")
        # Uppercased bare verb with no active task still classifies as new_task.
        self.assertEqual(
            self.mod.analyze_prompt("CREATE a widget", "WF_CLASSIFY"),
            "new_task")
        # Uppercased unambiguous opener pivots regardless of case/state.
        self.assertEqual(
            self.mod.analyze_prompt("NEW TASK: ship it", "WF_EXECUTE"),
            "new_task")

    def test_precedence_continuation_before_addition(self):
        # "continue" (continuation) is checked before addition/new_task; a
        # prompt that could theoretically hit multiple lists resolves to the
        # first list checked. "continue with the addition" hits CONTINUATION.
        self.assertEqual(
            self.mod.analyze_prompt("continue with the plan", "WF_EXECUTE"),
            "continuation",
        )


class TestResearchExitDirective(unittest.TestCase):
    """WF_RESEARCH needs_implementation exit: RESEARCH_IMPLEMENT_RE +
    research_exit_directive() content."""
    mod = import_hook("prompt/swe_user_prompt_workflow")

    def test_research_implement_re_matches_common_phrasings(self):
        for p in ("do everything", "implement it", "fix it", "okay, do it",
                  "go ahead", "add the missing tests", "apply the changes",
                  "make the changes", "please proceed", "build it",
                  "update the docs"):
            self.assertIsNotNone(
                self.mod.RESEARCH_IMPLEMENT_RE.search(p.lower()), p)

    def test_research_implement_re_does_not_match_question(self):
        for p in ("what does X do?", "how does this work?",
                  "can you explain the flow?"):
            self.assertIsNone(
                self.mod.RESEARCH_IMPLEMENT_RE.search(p.lower()), p)

    def test_directive_content(self):
        text = self.mod.research_exit_directive("abc12345", "WM_abc12345", "")
        self.assertIn("wf/WF_CLASSIFY", text)
        self.assertIn("swe_wm_transition", text)
        self.assertIn("needs_implementation", text)
        self.assertIn("abc12345", text)
        self.assertIn("set_state.py", text)

    def test_directive_interpolates_session_id_in_all_calls(self):
        text = self.mod.research_exit_directive("sess9999", None, "")
        # session_id appears in both the MCP tool call and the CLI fallback.
        self.assertGreaterEqual(text.count("sess9999"), 2)


class TestPromptPatternConstants(unittest.TestCase):
    mod = import_hook("prompt/swe_user_prompt_workflow")

    def test_pattern_lists_nonempty(self):
        self.assertTrue(self.mod.CONTINUATION_PATTERNS)
        self.assertTrue(self.mod.ADDITION_PATTERNS)
        self.assertTrue(self.mod.NEW_TASK_PATTERNS)
        self.assertGreater(len(self.mod.CONTINUATION_PATTERNS), 0)
        self.assertGreater(len(self.mod.ADDITION_PATTERNS), 0)
        self.assertGreater(len(self.mod.NEW_TASK_PATTERNS), 0)

    def test_pattern_lists_are_strings(self):
        for lst in (self.mod.CONTINUATION_PATTERNS,
                    self.mod.ADDITION_PATTERNS,
                    self.mod.NEW_TASK_PATTERNS):
            for pat in lst:
                self.assertIsInstance(pat, str)


class TestIsBackgroundNotification(unittest.TestCase):
    mod = import_hook("prompt/swe_user_prompt_workflow")

    def test_task_notification_tag_detected(self):
        self.assertTrue(self.mod.is_background_notification(
            "<task-notification>Agent finished</task-notification>"))

    def test_system_notification_prefix_detected(self):
        self.assertTrue(self.mod.is_background_notification(
            "[SYSTEM NOTIFICATION] background job complete"))

    def test_agent_finished_phrase_detected(self):
        self.assertTrue(self.mod.is_background_notification(
            'Agent "code-reviewer" finished: no issues found.'))

    def test_leading_whitespace_system_notification_detected(self):
        self.assertTrue(self.mod.is_background_notification(
            "   [SYSTEM NOTIFICATION] retry limit reached"))

    def test_genuine_user_prompt_not_detected(self):
        self.assertFalse(self.mod.is_background_notification("fix the login bug"))

    def test_empty_prompt_not_detected(self):
        self.assertFalse(self.mod.is_background_notification(""))
        self.assertFalse(self.mod.is_background_notification(None))

    def test_mention_of_agent_without_finished_not_detected(self):
        self.assertFalse(self.mod.is_background_notification(
            'Ask the "reviewer" agent to look at this'))


class TestMainBackgroundNotificationShortCircuit(unittest.TestCase):
    """main() must emit no classification/transition noise for a background
    task/agent-completion notification — but ONLY when this session already
    has a state file / WM. A genuine FIRST prompt that happens to quote such
    text (no state file exists yet) must NOT be swallowed before WM/session
    setup ever runs — verified end-to-end via stdin."""
    mod = import_hook("prompt/swe_user_prompt_workflow")

    def setUp(self):
        from _hookutil import reset_caches
        self._reset_caches = reset_caches
        self._reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name
        os.makedirs(os.path.join(self.cwd, '.git'), exist_ok=True)
        os.makedirs(os.path.join(self.cwd, '.serena'), exist_ok=True)
        with open(os.path.join(self.cwd, '.serena', 'swe-setup-complete.json'), 'w') as f:
            json.dump({'complete': True}, f)
        self._orig_env = os.environ.get('CLAUDE_PROJECT_DIR')
        os.environ['CLAUDE_PROJECT_DIR'] = self.cwd

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop('CLAUDE_PROJECT_DIR', None)
        else:
            os.environ['CLAUDE_PROJECT_DIR'] = self._orig_env
        self.tmp.cleanup()
        self._reset_caches()

    def _run_main(self, prompt, session_id=None):
        import io
        from unittest import mock
        transcript = (f'/x/{session_id}-0000-0000-0000-000000000000.jsonl'
                      if session_id else '')
        payload = {"prompt": prompt, "cwd": self.cwd, "transcript_path": transcript}
        buf = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
             mock.patch.object(os, 'getcwd', return_value=self.cwd), \
             mock.patch("sys.stdout", buf):
            try:
                self.mod.main()
            except SystemExit:
                pass
        return buf.getvalue()

    def _write_state_file(self, session_id, state='WF_EXECUTE'):
        d = os.path.join(self.cwd, '.serena', 'swe-state')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f'{session_id}.state'), 'w') as f:
            json.dump({'current_state': state, 'session_id': session_id}, f)

    def test_existing_session_background_notification_emits_empty_context(self):
        session_id = 'deadbeef'
        self._write_state_file(session_id)
        out = self._run_main('Agent "researcher" finished: done.', session_id)
        result = json.loads(out)
        self.assertEqual(result, {})

    def test_existing_session_task_notification_tag_emits_empty_context(self):
        session_id = 'feedface'
        self._write_state_file(session_id)
        out = self._run_main(
            "<task-notification>build passed</task-notification>", session_id)
        result = json.loads(out)
        self.assertEqual(result, {})

    def test_first_prompt_matching_notification_pattern_is_not_swallowed(self):
        # No state file yet for this session — this IS the session's first
        # prompt. Even though its text matches the background-notification
        # pattern, it must be routed through normal WF_INIT handling, not
        # silently swallowed as {}.
        session_id = 'ab000001'
        out = self._run_main('Agent "researcher" finished: done.', session_id)
        result = json.loads(out)
        self.assertNotEqual(result, {})
        self.assertIn('hookSpecificOutput', result)

    def test_first_prompt_task_notification_tag_is_not_swallowed(self):
        session_id = 'ab000002'
        out = self._run_main(
            "<task-notification>build passed</task-notification>", session_id)
        result = json.loads(out)
        self.assertNotEqual(result, {})
        self.assertIn('hookSpecificOutput', result)

    def test_no_session_id_at_all_still_not_swallowed(self):
        # No transcript_path -> no session_id -> read_state_file() is never
        # even reachable the way an existing-session check would need it;
        # the short-circuit must not fire without a resolvable session.
        out = self._run_main('Agent "researcher" finished: done.')
        result = json.loads(out)
        self.assertNotEqual(result, {})


class TestPromptLowerRegression(unittest.TestCase):
    """Regression guard: main() must define prompt_lower before use.

    main() reads stdin, so we cannot easily invoke it. Instead we assert the
    fix is present in the source of main(): it now assigns
    `prompt_lower = prompt.lower()` (the real line is `.lower().strip()`,
    which contains this substring).
    """
    mod = import_hook("prompt/swe_user_prompt_workflow")

    def test_main_defines_prompt_lower(self):
        src = inspect.getsource(self.mod.main)
        self.assertIn("prompt_lower = prompt.lower()", src)

    def test_main_uses_prompt_lower(self):
        # Sanity: the variable is actually referenced after being defined.
        src = inspect.getsource(self.mod.main)
        self.assertGreaterEqual(src.count("prompt_lower"), 2)


# ---------------------------------------------------------------------------
# stop/swe_stop_continue_working
# ---------------------------------------------------------------------------
class TestStopConstants(unittest.TestCase):
    mod = import_hook("stop/swe_stop_continue_working")

    def test_incomplete_states_set(self):
        s = self.mod.INCOMPLETE_STATES
        self.assertIsInstance(s, set)
        for expected in ('WF_EXECUTE', 'WF_DEBUG_TDD', 'WF_ARCH_REVIEW',
                         'WF_CHECKPOINT'):
            self.assertIn(expected, s)

    def test_allow_stop_states_set(self):
        s = self.mod.ALLOW_STOP_STATES
        self.assertIsInstance(s, set)
        for expected in ('WF_DONE', 'WF_VERIFY', 'UNINITIALIZED', ''):
            self.assertIn(expected, s)

    def test_incomplete_and_allow_disjoint(self):
        # A state cannot be both blocked and allowed.
        self.assertEqual(
            self.mod.INCOMPLETE_STATES & self.mod.ALLOW_STOP_STATES, set())

    def test_max_stop_retries(self):
        self.assertEqual(self.mod.MAX_STOP_RETRIES, 3)


class TestStopRegexes(unittest.TestCase):
    mod = import_hook("stop/swe_stop_continue_working")

    # --- CONTINUE_PATTERNS ---
    def test_continue_patterns_match(self):
        for s in ("Shall I continue with the implementation?",
                  "Would you like me to proceed?",
                  "Should I go ahead and make the change?",
                  "I'm waiting for your response.",
                  "I need your approval before continuing."):
            self.assertIsNotNone(
                self.mod.CONTINUE_PATTERNS.search(s), s)

    def test_continue_patterns_no_match_plain_statement(self):
        for s in ("I updated the config file and the tests pass.",
                  "The build succeeded."):
            self.assertIsNone(self.mod.CONTINUE_PATTERNS.search(s), s)

    # --- OPTIONS_PATTERNS ---
    def test_options_patterns_match(self):
        for s in ("Which option do you prefer?",
                  "Which approach would you like?",
                  "We can choose between the two designs."):
            self.assertIsNotNone(self.mod.OPTIONS_PATTERNS.search(s), s)

    def test_options_patterns_no_match(self):
        self.assertIsNone(
            self.mod.OPTIONS_PATTERNS.search(
                "I chose the simpler design and implemented it."))

    # --- GENUINE_INPUT_PATTERNS ---
    def test_genuine_input_patterns_match(self):
        for s in ("Is it safe to delete the production table?",
                  "This is a breaking change — proceed?",
                  "What are the trade-offs here?",
                  "Which database should I use?",
                  "Are you sure you want to overwrite it?"):
            self.assertIsNotNone(
                self.mod.GENUINE_INPUT_PATTERNS.search(s), s)

    def test_genuine_input_patterns_no_match_plain_statement(self):
        self.assertIsNone(
            self.mod.GENUINE_INPUT_PATTERNS.search(
                "I finished writing the unit tests."))

    def test_regexes_are_case_insensitive(self):
        # All three were compiled with re.IGNORECASE.
        self.assertIsNotNone(
            self.mod.CONTINUE_PATTERNS.search("SHALL I CONTINUE?"))
        self.assertIsNotNone(
            self.mod.OPTIONS_PATTERNS.search("WHICH OPTION DO YOU want?"))
        self.assertIsNotNone(
            self.mod.GENUINE_INPUT_PATTERNS.search("BREAKING CHANGE ahead"))


class TestExtractLastAssistantText(unittest.TestCase):
    mod = import_hook("stop/swe_stop_continue_working")

    def _write_transcript(self, path, entries):
        with open(path, 'w', encoding='utf-8') as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    def test_returns_last_assistant_text(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "transcript.jsonl")
            entries = [
                {"type": "user",
                 "message": {"content": [{"type": "text", "text": "hi"}]}},
                {"type": "assistant",
                 "message": {"content": [{"type": "text",
                                          "text": "first assistant"}]}},
                {"type": "user",
                 "message": {"content": [{"type": "text", "text": "more"}]}},
                {"type": "assistant",
                 "message": {"content": [{"type": "text",
                                          "text": "LAST assistant reply"}]}},
            ]
            self._write_transcript(path, entries)
            self.assertEqual(
                self.mod.extract_last_assistant_text(path),
                "LAST assistant reply",
            )

    def test_ignores_non_text_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "transcript.jsonl")
            entries = [
                {"type": "assistant",
                 "message": {"content": [
                     {"type": "tool_use", "name": "Bash"},
                     {"type": "text", "text": "the answer"},
                 ]}},
            ]
            self._write_transcript(path, entries)
            self.assertEqual(
                self.mod.extract_last_assistant_text(path), "the answer")

    def test_missing_file_returns_empty(self):
        self.assertEqual(
            self.mod.extract_last_assistant_text(
                "/nonexistent/path/to/transcript.jsonl"),
            "",
        )

    def test_empty_path_returns_empty(self):
        self.assertEqual(self.mod.extract_last_assistant_text(""), "")

    def test_blank_and_malformed_lines_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "transcript.jsonl")
            with open(path, 'w', encoding='utf-8') as f:
                f.write("\n")                       # blank line
                f.write("{ not valid json\n")       # malformed
                f.write(json.dumps({
                    "type": "assistant",
                    "message": {"content": [
                        {"type": "text", "text": "survived"}]}}) + "\n")
                f.write("   \n")                     # whitespace-only
            self.assertEqual(
                self.mod.extract_last_assistant_text(path), "survived")

    def test_no_assistant_messages_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "transcript.jsonl")
            self._write_transcript(path, [
                {"type": "user",
                 "message": {"content": [{"type": "text", "text": "hi"}]}},
            ])
            self.assertEqual(self.mod.extract_last_assistant_text(path), "")


# ---------------------------------------------------------------------------
# stop/swe_stop_continue_working — main() early-exit allow-stop guards
# ---------------------------------------------------------------------------
class TestContinueWorkingEarlyAllowGuards(unittest.TestCase):
    """stop_hook_active / user_spoke_mid_turn / ends_with_question must allow
    the stop BEFORE any of the INCOMPLETE_STATES blocking logic fires."""

    mod = import_hook("stop/swe_stop_continue_working")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.transcript_path = os.path.join(self.tmp.name, "session.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def _write_transcript(self, entries):
        with open(self.transcript_path, 'w', encoding='utf-8') as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    def _run_main(self, payload_extra, state="WF_EXECUTE", mid_turn=False):
        from unittest import mock
        import io
        import sys
        from contextlib import redirect_stdout

        payload = {
            "transcript_path": self.transcript_path,
            "cwd": self.tmp.name,
            "stop_reason": "end_turn",
        }
        payload.update(payload_extra)

        class _StubState:
            def __init__(self, *a, **kw):
                pass

            def get_current_state(self):
                return state

        buf = io.StringIO()
        with mock.patch.object(self.mod, "read_stdin_safe", return_value=payload), \
             mock.patch.object(self.mod, "StateManager", _StubState), \
             mock.patch.object(self.mod, "user_spoke_mid_turn", return_value=mid_turn), \
             mock.patch.object(self.mod, "_persist_state_on_stop", return_value=None), \
             redirect_stdout(buf):
            try:
                self.mod.main()
            except SystemExit:
                pass
        return buf.getvalue()

    def test_stop_hook_active_allows_stop_even_in_incomplete_state(self):
        # Without the guard, WF_EXECUTE + a "shall I continue?" reply blocks.
        self._write_transcript([
            {"type": "assistant",
             "message": {"content": [{"type": "text", "text": "Shall I continue?"}]}},
        ])
        out = self._run_main({"stop_hook_active": True}, state="WF_EXECUTE")
        self.assertEqual(out.strip(), "{}")

    def test_mid_turn_allows_stop_even_in_incomplete_state(self):
        self._write_transcript([
            {"type": "assistant",
             "message": {"content": [{"type": "text", "text": "Shall I continue?"}]}},
        ])
        out = self._run_main({"stop_hook_active": False}, state="WF_EXECUTE", mid_turn=True)
        self.assertEqual(out.strip(), "{}")

    def test_question_ending_allows_stop_even_in_incomplete_state(self):
        self._write_transcript([
            {"type": "assistant",
             "message": {"content": [
                 {"type": "text", "text": "Which migration should run first?"}]}},
        ])
        out = self._run_main({"stop_hook_active": False}, state="WF_EXECUTE", mid_turn=False)
        self.assertEqual(out.strip(), "{}")

    def test_no_guard_triggered_still_blocks_confirmation_pattern(self):
        # Control: with none of the three guards true, the pre-existing
        # confirmation-pattern block still fires for WF_EXECUTE. Must NOT end
        # in a question mark (ends_with_question guard) and must NOT match
        # GENUINE_INPUT_PATTERNS (e.g. "proceed", "delete") or the stop is
        # correctly allowed through by pre-existing logic, not this guard.
        self._write_transcript([
            {"type": "assistant",
             "message": {"content": [
                 {"type": "text", "text": "Waiting for your response before I continue."}]}},
        ])
        out = self._run_main({"stop_hook_active": False}, state="WF_EXECUTE", mid_turn=False)
        self.assertIn('"decision": "block"', out)


# ---------------------------------------------------------------------------
# session/swe_session_end
# ---------------------------------------------------------------------------
class TestCleanupSentinels(unittest.TestCase):
    mod = import_hook("session/swe_session_end")

    def test_removes_session_sentinels_keeps_others(self):
        sid = "sess123"
        with tempfile.TemporaryDirectory() as td:
            init_f = os.path.join(td, f".init_{sid}")
            test_f = os.path.join(td, f".test_feature_{sid}")
            # Unrelated files that must survive.
            other_session = os.path.join(td, ".init_otherSession")
            unrelated = os.path.join(td, "stream_sess123.jsonl")
            for p in (init_f, test_f, other_session, unrelated):
                with open(p, 'w') as f:
                    f.write("x")

            self.mod.cleanup_sentinels(td, sid)

            self.assertFalse(os.path.exists(init_f))
            self.assertFalse(os.path.exists(test_f))
            self.assertTrue(os.path.exists(other_session))
            self.assertTrue(os.path.exists(unrelated))

    def test_missing_sentinels_no_error(self):
        with tempfile.TemporaryDirectory() as td:
            # No sentinel files present — should be a silent no-op.
            self.mod.cleanup_sentinels(td, "nope")  # must not raise


class TestMarkWmAbandoned(unittest.TestCase):
    mod = import_hook("session/swe_session_end")

    def _wm_path(self, root, sid):
        return os.path.join(root, ".serena", "memories", f"WM_{sid}.md")

    def _make_wm(self, root, sid, content):
        path = self._wm_path(root, sid)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(content)
        return path

    def _read(self, path):
        with open(path) as f:
            return f.read()

    def test_marks_in_progress_when_not_done(self):
        sid = "abc"
        with tempfile.TemporaryDirectory() as td:
            path = self._make_wm(
                td, sid, "## Current Task [IN_PROGRESS]\nDo the thing\n")
            self.mod.mark_wm_abandoned(td, sid, "WF_EXECUTE")
            content = self._read(path)
            self.assertIn("[ABANDONED]", content)
            self.assertNotIn("[IN_PROGRESS]", content)

    def test_annotates_current_task_when_no_in_progress_marker(self):
        sid = "def"
        with tempfile.TemporaryDirectory() as td:
            path = self._make_wm(td, sid, "## Current Task\nSomething\n")
            self.mod.mark_wm_abandoned(td, sid, "WF_VERIFY")
            content = self._read(path)
            self.assertIn("Session ended without reaching WF_DONE", content)
            self.assertIn("Final state: WF_VERIFY", content)

    def test_wf_done_does_not_mark(self):
        sid = "ghi"
        with tempfile.TemporaryDirectory() as td:
            original = "## Current Task [IN_PROGRESS]\nDone work\n"
            path = self._make_wm(td, sid, original)
            self.mod.mark_wm_abandoned(td, sid, "WF_DONE")
            content = self._read(path)
            self.assertEqual(content, original)
            self.assertNotIn("[ABANDONED]", content)

    def test_missing_wm_file_no_error(self):
        with tempfile.TemporaryDirectory() as td:
            # No WM file exists — silent no-op, no exception.
            self.mod.mark_wm_abandoned(td, "missing", "WF_EXECUTE")

    def test_already_abandoned_not_double_marked(self):
        sid = "jkl"
        with tempfile.TemporaryDirectory() as td:
            content0 = "## Current Task [ABANDONED]\nstuff\n"
            path = self._make_wm(td, sid, content0)
            self.mod.mark_wm_abandoned(td, sid, "WF_EXECUTE")
            # Unchanged — the guard skips already-marked files.
            self.assertEqual(self._read(path), content0)

    def test_already_completed_not_marked(self):
        sid = "mno"
        with tempfile.TemporaryDirectory() as td:
            content0 = "## Current Task [COMPLETED]\nfinished\n"
            path = self._make_wm(td, sid, content0)
            self.mod.mark_wm_abandoned(td, sid, "WF_EXECUTE")
            self.assertEqual(self._read(path), content0)


class TestDeployIntentInjection(unittest.TestCase):
    mod = import_hook("prompt/swe_user_prompt_workflow")

    def test_deploy_prompt_gets_pre_deploy_note(self):
        note = self.mod.deploy_note_for("deploy the theme to production")
        self.assertIn("PRE-DEPLOY GATE", note)

    def test_push_it_live_gets_note(self):
        self.assertIn("PRE-DEPLOY GATE", self.mod.deploy_note_for("ok push it live"))

    def test_ship_it_gets_note(self):
        self.assertIn("PRE-DEPLOY GATE", self.mod.deploy_note_for("ship it"))

    def test_plain_prompt_gets_empty(self):
        self.assertEqual(self.mod.deploy_note_for("update the docs for the CRM"), "")

    def test_pushed_past_tense_not_matched(self):
        # "pushed the commit yesterday" is narration, not a deploy ask
        self.assertEqual(self.mod.deploy_note_for("I pushed the commit yesterday"), "")

    def test_empty_prompt_gets_empty(self):
        self.assertEqual(self.mod.deploy_note_for(""), "")
        self.assertEqual(self.mod.deploy_note_for(None), "")


class TestSessionStartForensics(unittest.TestCase):
    """session_boot lands BEFORE the self-update, selfupdate logs its outcome —
    a boot marker with no following selfupdate event = update killed mid-run."""

    mod = import_hook("session/swe_session_start")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stream = os.path.join(self.tmp.name, 'sess.jsonl')

    def tearDown(self):
        self.tmp.cleanup()

    def _events(self):
        with open(self.stream) as f:
            return [json.loads(line) for line in f]

    def test_log_boot_appends_marker_with_source(self):
        self.mod._log_boot(self.stream, 'abcd1234', 'resume')
        e = self._events()
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0]['type'], 'session_boot')
        self.assertEqual(e[0]['src'], 'resume')

    def test_self_update_success_logged(self):
        orig = self.mod._self_update
        self.mod._self_update = lambda: (True, '1.0.0', '1.0.1')
        try:
            result = self.mod._run_self_update_logged(self.stream)
        finally:
            self.mod._self_update = orig
        self.assertEqual(result, (True, '1.0.0', '1.0.1'))
        e = self._events()[0]
        self.assertEqual((e['type'], e['ok'], e['old'], e['new']),
                         ('selfupdate', True, '1.0.0', '1.0.1'))

    def test_self_update_failure_logged_not_raised(self):
        orig = self.mod._self_update
        def boom():
            raise RuntimeError('pull failed')
        self.mod._self_update = boom
        try:
            result = self.mod._run_self_update_logged(self.stream)
        finally:
            self.mod._self_update = orig
        self.assertEqual(result, (False, None, None))
        e = self._events()[0]
        self.assertEqual((e['type'], e['ok']), ('selfupdate', False))
        self.assertIn('pull failed', e['err'])


class TestMarketplaceSelfUpdateDirtyClone(unittest.TestCase):
    """REGRESSION: the marketplace clone is a managed mirror that accumulates
    local file drift at runtime. The old `git pull --ff-only` ABORTED on a dirty
    clone ('local changes would be overwritten'), so every self-update silently
    failed and the plugin stayed pinned at the old version. The update must now
    fetch + hard-reset to origin/main, advancing even when the clone is dirty."""

    import subprocess as _subprocess
    import shutil as _shutil

    mod = import_hook("session/swe_session_start")

    def _git(self, cwd, *args):
        self._subprocess.run(['git', *args], cwd=cwd, check=True,
                             capture_output=True, text=True)

    def setUp(self):
        if self._shutil.which('git') is None:
            self.skipTest('git not available')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = self.tmp.name

        # A bare "origin" that the marketplace clone tracks.
        self.origin = os.path.join(root, 'origin.git')
        os.makedirs(self.origin)
        self._git(self.origin, 'init', '--bare', '-b', 'main')

        # A seed working tree → v1.0.0, pushed to origin.
        seed = os.path.join(root, 'seed')
        os.makedirs(os.path.join(seed, '.claude-plugin'))
        self._git(seed, 'init', '-b', 'main')
        self._git(seed, 'config', 'user.email', 't@t')
        self._git(seed, 'config', 'user.name', 't')
        self._write_version(seed, '1.0.0')
        with open(os.path.join(seed, 'hooks_file.py'), 'w') as f:
            f.write("# original\n")
        self._git(seed, 'add', '-A')
        self._git(seed, 'commit', '-m', 'v1.0.0')
        self._git(seed, 'remote', 'add', 'origin', self.origin)
        self._git(seed, 'push', '-u', 'origin', 'main')

        # The marketplace CACHE layout: .../cache/<Market>/<plugin>/<version>/
        cache = os.path.join(root, '.claude', 'plugins', 'cache')
        self.plugin_root = os.path.join(cache, 'MyMarket', 'myplugin', '1.0.0')
        os.makedirs(os.path.dirname(self.plugin_root))
        self._git(root, 'clone', seed, self.plugin_root)  # temp; replaced below
        self._shutil.rmtree(self.plugin_root)

        # The real marketplace CLONE that Claude Code maintains.
        self.clone = os.path.join(root, '.claude', 'plugins',
                                  'marketplaces', 'MyMarket')
        os.makedirs(os.path.dirname(self.clone))
        self._git(root, 'clone', self.origin, self.clone)
        self._git(self.clone, 'config', 'user.email', 't@t')
        self._git(self.clone, 'config', 'user.name', 't')
        # Cache version dir mirrors the clone at v1.0.0.
        self._shutil.copytree(self.clone, self.plugin_root,
                              ignore=self._shutil.ignore_patterns('.git'))

        # Advance origin to v1.0.1 (a new release to pull).
        self._write_version(seed, '1.0.1')
        with open(os.path.join(seed, 'hooks_file.py'), 'w') as f:
            f.write("# upstream v1.0.1 change\n")
        self._git(seed, 'commit', '-am', 'v1.0.1')
        self._git(seed, 'push', 'origin', 'main')

        # DIRTY the clone — exactly the failure mode (runtime-touched hook file).
        with open(os.path.join(self.clone, 'hooks_file.py'), 'w') as f:
            f.write("# LOCAL DRIFT that would block ff-only pull\n")

    def _write_version(self, tree, version):
        pj = os.path.join(tree, '.claude-plugin', 'plugin.json')
        os.makedirs(os.path.dirname(pj), exist_ok=True)
        with open(pj, 'w') as f:
            json.dump({'name': 'myplugin', 'version': version}, f)

    def test_dirty_clone_still_updates_to_new_version(self):
        updated, old, new = self.mod._self_update_marketplace(self.plugin_root)
        self.assertEqual((old, new), ('1.0.0', '1.0.1'))
        self.assertTrue(updated)
        # New versioned cache dir was created from the reset clone.
        new_cache = os.path.join(os.path.dirname(self.plugin_root), '1.0.1')
        self.assertTrue(os.path.isdir(new_cache))
        # The clone was hard-reset: local drift is gone, upstream content present.
        with open(os.path.join(self.clone, 'hooks_file.py')) as f:
            self.assertEqual(f.read(), "# upstream v1.0.1 change\n")

    def test_clone_already_current_is_noop(self):
        # Reset origin expectation: when clone already matches origin's version,
        # no new cache dir is made and updated is False.
        self._git(self.clone, 'fetch', 'origin', 'main', '--quiet')
        self._git(self.clone, 'reset', '--hard', 'origin/main')
        # Cache already at latest → bump the cache plugin.json to the new version
        self._write_version(self.plugin_root, '1.0.1')
        updated, old, new = self.mod._self_update_marketplace(self.plugin_root)
        self.assertFalse(updated)
        self.assertEqual((old, new), ('1.0.1', '1.0.1'))


if __name__ == "__main__":
    unittest.main()
