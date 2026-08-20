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

    # --- new_task branch ---
    def test_new_task_action_verb_prefix(self):
        for p in ("create a new feature", "build the login page",
                  "implement caching", "fix the bug", "refactor this module"):
            self.assertEqual(
                self.mod.analyze_prompt(p, "WF_EXECUTE"), "new_task", p)

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
        self.assertEqual(
            self.mod.analyze_prompt("CREATE a widget", "WF_EXECUTE"),
            "new_task")

    def test_precedence_continuation_before_addition(self):
        # "continue" (continuation) is checked before addition/new_task; a
        # prompt that could theoretically hit multiple lists resolves to the
        # first list checked. "continue with the addition" hits CONTINUATION.
        self.assertEqual(
            self.mod.analyze_prompt("continue with the plan", "WF_EXECUTE"),
            "continuation",
        )


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
