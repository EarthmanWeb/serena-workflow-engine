"""Tests for hooks/pre/* pure functions and module constants.

Targets:
  - pre/swe_pre_edit_validate: _is_bypass_write_attempt, _is_raw_memory_write,
    _block_message; constants EDIT_ALLOWED, WARN_STATES.
  - pre/swe_pre_tool_init_gate: _extract_session_id, _is_bypass_write_attempt,
    check_working_memory_exists, check_lite_mode, inject_metadata; constants
    INIT_ALLOWED_MEMORIES, SKIP_STREAM_TOOLS; main()-level spawned-agent
    exemption (no init denial/directive text, bypass-write guard and
    _swe_metadata injection still apply).
  - pre/swe_pre_bash_test_gate: get_test_sentinel_path, load_bash_policy;
    constant TEST_COMMAND_PATTERNS; main()-level spawned-agent exemption from
    the FEATURE_TESTS test gate.

ALREADY-TESTED elsewhere (skipped here): is_test_command, check_bash_policy,
is_working_memory_write.

Deterministic + offline: no network, no real Serena, no real git. IO goes
through tempfile.TemporaryDirectory. Functions that resolve paths via
get_project_root()/get_stream_dir() are exercised by monkeypatching the exact
symbol the module imported and restoring it in tearDown.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_hook, import_core, reset_caches  # noqa: E402

edit_mod = import_hook("pre/swe_pre_edit_validate")
init_mod = import_hook("pre/swe_pre_tool_init_gate")
bash_mod = import_hook("pre/swe_pre_bash_test_gate")


# ---------------------------------------------------------------------------
# swe_pre_edit_validate
# ---------------------------------------------------------------------------
class TestEditValidateConstants(unittest.TestCase):
    def test_edit_allowed_is_set_with_expected_states(self):
        self.assertIsInstance(edit_mod.EDIT_ALLOWED, set)
        for st in ('WF_EXECUTE', 'WF_DEBUG_TDD', 'WF_CHECKPOINT',
                   'WF_INITIAL_SETUP', 'WF_ONBOARD', 'WF_VERIFY'):
            self.assertIn(st, edit_mod.EDIT_ALLOWED)
        # Classification/routing state is NOT an edit state.
        self.assertNotIn('WF_CLASSIFY', edit_mod.EDIT_ALLOWED)

    def test_warn_states_is_set_with_expected_states(self):
        self.assertIsInstance(edit_mod.WARN_STATES, set)
        self.assertEqual(edit_mod.WARN_STATES, {'WF_ARCH_REVIEW', 'WF_RESEARCH'})

    def test_edit_allowed_and_warn_states_disjoint(self):
        self.assertEqual(edit_mod.EDIT_ALLOWED & edit_mod.WARN_STATES, set())


class TestEditIsBypassWriteAttempt(unittest.TestCase):
    def test_edit_setting_bypass_true_in_setup_file_is_blocked(self):
        data = {
            'tool_name': 'Edit',
            'tool_input': {
                'file_path': '/proj/.serena/swe-setup-complete.json',
                'new_string': '{"complete": true, "bypass": true}',
            },
        }
        self.assertTrue(edit_mod._is_bypass_write_attempt(data))

    def test_write_setting_bypass_true_via_content_is_blocked(self):
        data = {
            'tool_name': 'Write',
            'tool_input': {
                'file_path': '/x/.serena/swe-setup-complete.json',
                'content': '{"bypass": true}',
            },
        }
        self.assertTrue(edit_mod._is_bypass_write_attempt(data))

    def test_quote_and_space_insensitive_match(self):
        # single-quotes and extra spaces are normalized away
        data = {
            'tool_input': {
                'file_path': 'swe-setup-complete.json',
                'new_string': "{ 'bypass' :  true }",
            },
        }
        self.assertTrue(edit_mod._is_bypass_write_attempt(data))

    def test_memory_name_target_also_checked(self):
        data = {
            'tool_input': {
                'memory_name': 'config/swe-setup-complete',
                'content': '{"bypass":true}',
            },
        }
        self.assertTrue(edit_mod._is_bypass_write_attempt(data))

    def test_bypass_false_is_not_blocked(self):
        data = {
            'tool_input': {
                'file_path': 'swe-setup-complete.json',
                'content': '{"bypass": false}',
            },
        }
        self.assertFalse(edit_mod._is_bypass_write_attempt(data))

    def test_bypass_in_other_file_is_not_blocked(self):
        # target does not mention swe-setup-complete -> returns before content check
        data = {
            'tool_input': {
                'file_path': '/proj/config.json',
                'content': '{"bypass": true}',
            },
        }
        self.assertFalse(edit_mod._is_bypass_write_attempt(data))

    def test_benign_edit_to_setup_file_is_not_blocked(self):
        data = {
            'tool_input': {
                'file_path': 'swe-setup-complete.json',
                'new_string': '{"complete": true}',
            },
        }
        self.assertFalse(edit_mod._is_bypass_write_attempt(data))

    def test_empty_input_is_not_blocked(self):
        self.assertFalse(edit_mod._is_bypass_write_attempt({}))

    def test_none_tool_input_is_not_blocked(self):
        # tool_input explicitly None -> `or {}` guard
        self.assertFalse(edit_mod._is_bypass_write_attempt({'tool_input': None}))


class TestEditIsRawMemoryWrite(unittest.TestCase):
    def test_edit_on_memory_file_is_raw_write(self):
        data = {
            'tool_name': 'Edit',
            'tool_input': {'file_path': '/proj/.serena/memory/dom/DOM_X.md'},
        }
        self.assertTrue(edit_mod._is_raw_memory_write(data))

    def test_write_on_memories_plural_dir_is_raw_write(self):
        data = {
            'tool_name': 'Write',
            'tool_input': {'file_path': '/proj/.serena/memories/ref/REF_X.md'},
        }
        self.assertTrue(edit_mod._is_raw_memory_write(data))

    def test_wm_file_is_exempt(self):
        # WM_ session working memory is written by the harness/daemon by design
        data = {
            'tool_name': 'Write',
            'tool_input': {'file_path': '/proj/.serena/memories/WM_abc12345.md'},
        }
        self.assertFalse(edit_mod._is_raw_memory_write(data))

    def test_non_edit_write_tool_is_not_raw_memory_write(self):
        data = {
            'tool_name': 'Read',
            'tool_input': {'file_path': '/proj/.serena/memory/dom/DOM_X.md'},
        }
        self.assertFalse(edit_mod._is_raw_memory_write(data))

    def test_non_memory_path_is_not_raw_write(self):
        data = {
            'tool_name': 'Edit',
            'tool_input': {'file_path': '/proj/src/main.py'},
        }
        self.assertFalse(edit_mod._is_raw_memory_write(data))

    def test_backslash_path_is_normalized(self):
        data = {
            'tool_name': 'Edit',
            'tool_input': {'file_path': r'C:\proj\.serena\memory\dom\DOM_X.md'},
        }
        self.assertTrue(edit_mod._is_raw_memory_write(data))

    def test_missing_tool_input_is_not_raw_write(self):
        data = {'tool_name': 'Edit'}
        self.assertFalse(edit_mod._is_raw_memory_write(data))

    def test_none_tool_input_is_not_raw_write(self):
        data = {'tool_name': 'Edit', 'tool_input': None}
        self.assertFalse(edit_mod._is_raw_memory_write(data))

    def test_empty_input_is_not_raw_write(self):
        self.assertFalse(edit_mod._is_raw_memory_write({}))


class TestEditBlockMessage(unittest.TestCase):
    def test_classify_message_mentions_state_and_routing(self):
        msg = edit_mod._block_message('WF_CLASSIFY')
        self.assertIsInstance(msg, str)
        self.assertIn('WF_CLASSIFY', msg)
        # Classify branch routes the assistant onward to execution.
        self.assertIn('WF_EXECUTE', msg)

    def test_generic_message_mentions_the_blocking_state(self):
        msg = edit_mod._block_message('WF_RESEARCH')
        self.assertIsInstance(msg, str)
        self.assertIn('WF_RESEARCH', msg)
        self.assertIn('WF_EXECUTE', msg)

    def test_generic_message_for_unknown_state(self):
        msg = edit_mod._block_message('WF_SOMETHING_ELSE')
        self.assertIn('WF_SOMETHING_ELSE', msg)


class TestEditDriftBlockVerdict(unittest.TestCase):
    """_drift_block_verdict: hard-threshold enforcement pure function.

    Fail-open (returns None, no block) with no session id, no stream file, or
    no WM file. Denies once count_task_work_since_delegation reaches
    DRIFT_HARD_THRESHOLD UNLESS the WM file records 'single-agent: <reason>'.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name
        self.session_id = 'deadbeef'
        self.streams_dir = os.path.join(self.cwd, '.serena', 'streams')
        self.memories_dir = os.path.join(self.cwd, '.serena', 'memories')
        os.makedirs(self.streams_dir, exist_ok=True)
        os.makedirs(self.memories_dir, exist_ok=True)
        self._orig_stream_path = edit_mod.get_stream_path
        edit_mod.get_stream_path = (
            lambda sid: os.path.join(self.streams_dir, f'{sid}.jsonl'))
        from swe_hooks.core import session as core_session
        self._orig_root = core_session.get_project_root
        core_session.get_project_root = lambda: self.cwd

    def tearDown(self):
        edit_mod.get_stream_path = self._orig_stream_path
        from swe_hooks.core import session as core_session
        core_session.get_project_root = self._orig_root
        self.tmp.cleanup()

    def _write_stream(self, events):
        path = os.path.join(self.streams_dir, f'{self.session_id}.jsonl')
        with open(path, 'w') as f:
            for e in events:
                f.write(json.dumps(e) + '\n')
        return path

    def _write_wm(self, body):
        with open(os.path.join(
                self.memories_dir, f'WM_{self.session_id}.md'), 'w') as f:
            f.write(body)

    def test_no_session_id_returns_none(self):
        self._write_stream([{'type': 'task_work'}] * 12)
        self.assertIsNone(edit_mod._drift_block_verdict(None, self.cwd))

    def test_no_stream_file_returns_none(self):
        self.assertIsNone(
            edit_mod._drift_block_verdict(self.session_id, self.cwd))

    def test_below_hard_threshold_returns_none(self):
        n = edit_mod.DRIFT_HARD_THRESHOLD - 1
        self._write_stream([{'type': 'task_work'}] * n)
        self._write_wm('## Context\nnormal session\n')
        self.assertIsNone(
            edit_mod._drift_block_verdict(self.session_id, self.cwd))

    def test_at_hard_threshold_no_wm_note_denies(self):
        self._write_stream(
            [{'type': 'task_work'}] * edit_mod.DRIFT_HARD_THRESHOLD)
        self._write_wm('## Context\nnormal session\n')
        msg = edit_mod._drift_block_verdict(self.session_id, self.cwd)
        self.assertIsNotNone(msg)
        self.assertIn('STOP doing the work yourself', msg)
        self.assertIn(str(edit_mod.DRIFT_HARD_THRESHOLD), msg)

    def test_at_hard_threshold_no_wm_file_fails_open(self):
        # No WM file at all — fail open for THIS check specifically.
        self._write_stream(
            [{'type': 'task_work'}] * edit_mod.DRIFT_HARD_THRESHOLD)
        self.assertIsNone(
            edit_mod._drift_block_verdict(self.session_id, self.cwd))

    def test_single_agent_note_in_wm_allows(self):
        self._write_stream(
            [{'type': 'task_work'}] * edit_mod.DRIFT_HARD_THRESHOLD)
        self._write_wm(
            '## Context\nsingle-agent: tight coupled fix in one file\n')
        self.assertIsNone(
            edit_mod._drift_block_verdict(self.session_id, self.cwd))

    def test_single_agent_note_case_insensitive(self):
        self._write_stream(
            [{'type': 'task_work'}] * edit_mod.DRIFT_HARD_THRESHOLD)
        self._write_wm('## Context\nSINGLE-AGENT: reason here\n')
        self.assertIsNone(
            edit_mod._drift_block_verdict(self.session_id, self.cwd))

    def test_delegation_event_resets_count_below_threshold(self):
        events = ([{'type': 'task_work'}] * (edit_mod.DRIFT_HARD_THRESHOLD - 1)
                  + [{'type': 'delegation', 'tool': 'Agent'}]
                  + [{'type': 'task_work'}])
        self._write_stream(events)
        self._write_wm('## Context\nnormal session\n')
        self.assertIsNone(
            edit_mod._drift_block_verdict(self.session_id, self.cwd))


class TestEditGateDriftMainIntegration(unittest.TestCase):
    """main() end-to-end: drift block only fires in EDIT_ALLOWED states,
    after the sweep gate passes, and never for a spawned agent."""

    SESSION = 'deadbeef'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name
        self.streams_dir = os.path.join(self.cwd, '.serena', 'streams')
        self.memories_dir = os.path.join(self.cwd, '.serena', 'memories')
        os.makedirs(self.streams_dir, exist_ok=True)
        os.makedirs(self.memories_dir, exist_ok=True)
        reset_caches()

        from swe_hooks.core import session as core_session
        from swe_hooks.core import config as core_config
        self._orig_session_root = core_session.get_project_root
        self._orig_config_root = core_config.get_project_root
        core_session.get_project_root = lambda: self.cwd
        core_config.get_project_root = lambda: self.cwd

        self._orig_stream_path = edit_mod.get_stream_path
        edit_mod.get_stream_path = (
            lambda sid: os.path.join(self.streams_dir, f'{sid}.jsonl'))

        # State file: WF_EXECUTE, sweep sentinel present so the sweep gate
        # never blocks (drift block runs strictly after it).
        state_dir = os.path.join(self.cwd, '.serena', 'swe-state')
        os.makedirs(state_dir, exist_ok=True)
        with open(os.path.join(state_dir, f'{self.SESSION}.state'), 'w') as f:
            json.dump({'current_state': 'WF_EXECUTE'}, f)
        sweep_sentinel = os.path.join(
            self.streams_dir, f'.sweep_feature_{self.SESSION}')
        open(sweep_sentinel, 'w').close()

    def tearDown(self):
        from swe_hooks.core import session as core_session
        from swe_hooks.core import config as core_config
        core_session.get_project_root = self._orig_session_root
        core_config.get_project_root = self._orig_config_root
        edit_mod.get_stream_path = self._orig_stream_path
        self.tmp.cleanup()
        reset_caches()

    def _transcript(self):
        return f'/x/{self.SESSION}-0000-0000-0000-000000000000.jsonl'

    def _write_stream(self, events):
        path = os.path.join(self.streams_dir, f'{self.SESSION}.jsonl')
        with open(path, 'w') as f:
            for e in events:
                f.write(json.dumps(e) + '\n')

    def _write_wm(self, body):
        with open(os.path.join(
                self.memories_dir, f'WM_{self.SESSION}.md'), 'w') as f:
            f.write(body)

    def _run_main(self, tool_input, extra=None):
        import io
        payload = {
            'tool_name': 'Edit',
            'tool_input': tool_input,
            'transcript_path': self._transcript(),
            'cwd': self.cwd,
        }
        if extra:
            payload.update(extra)
        stdin_json = json.dumps(payload)
        buf = io.StringIO()
        from unittest import mock
        with mock.patch('sys.stdin', io.StringIO(stdin_json)), \
             mock.patch('select.select', return_value=([sys.stdin], [], [])), \
             mock.patch('sys.stdout', buf):
            with self.assertRaises(SystemExit):
                edit_mod.main()
        return json.loads(buf.getvalue() or '{}')

    def test_blocked_at_hard_threshold_without_wm_note(self):
        self._write_stream(
            [{'type': 'task_work'}] * edit_mod.DRIFT_HARD_THRESHOLD)
        self._write_wm('## Context\nnormal session\n')
        result = self._run_main({'file_path': '/proj/src/x.py'})
        out = result.get('hookSpecificOutput', {})
        self.assertEqual(out.get('permissionDecision'), 'deny')
        self.assertIn('STOP doing the work yourself',
                       out.get('permissionDecisionReason', ''))

    def test_allowed_with_single_agent_note(self):
        self._write_stream(
            [{'type': 'task_work'}] * edit_mod.DRIFT_HARD_THRESHOLD)
        self._write_wm(
            '## Context\nsingle-agent: one-file coupled fix, no split\n')
        result = self._run_main({'file_path': '/proj/src/x.py'})
        self.assertNotEqual(
            result.get('hookSpecificOutput', {}).get('permissionDecision'),
            'deny')

    def test_allowed_after_delegation_resets_count(self):
        events = ([{'type': 'task_work'}] * edit_mod.DRIFT_HARD_THRESHOLD
                  + [{'type': 'delegation', 'tool': 'Agent'}])
        self._write_stream(events)
        self._write_wm('## Context\nnormal session\n')
        result = self._run_main({'file_path': '/proj/src/x.py'})
        self.assertNotEqual(
            result.get('hookSpecificOutput', {}).get('permissionDecision'),
            'deny')

    def test_spawned_agent_never_blocked(self):
        self._write_stream(
            [{'type': 'task_work'}] * (edit_mod.DRIFT_HARD_THRESHOLD * 2))
        self._write_wm('## Context\nnormal session\n')
        result = self._run_main(
            {'file_path': '/proj/src/x.py'}, extra={'agent_id': 'sub-1'})
        self.assertNotEqual(
            result.get('hookSpecificOutput', {}).get('permissionDecision'),
            'deny')

    def test_below_threshold_not_blocked(self):
        self._write_stream(
            [{'type': 'task_work'}] * (edit_mod.DRIFT_HARD_THRESHOLD - 1))
        self._write_wm('## Context\nnormal session\n')
        result = self._run_main({'file_path': '/proj/src/x.py'})
        self.assertNotEqual(
            result.get('hookSpecificOutput', {}).get('permissionDecision'),
            'deny')


# ---------------------------------------------------------------------------
# swe_pre_tool_init_gate
# ---------------------------------------------------------------------------
class TestInitGateConstants(unittest.TestCase):
    def test_init_allowed_memories_is_frozenset(self):
        self.assertIsInstance(init_mod.INIT_ALLOWED_MEMORIES, frozenset)
        self.assertIn('wf/WF_INIT', init_mod.INIT_ALLOWED_MEMORIES)
        self.assertIn('claude/CLAUDE_OBLIGATIONS', init_mod.INIT_ALLOWED_MEMORIES)
        self.assertIn('wf/WF_CLASSIFY', init_mod.INIT_ALLOWED_MEMORIES)

    def test_skip_stream_tools_is_frozenset(self):
        self.assertIsInstance(init_mod.SKIP_STREAM_TOOLS, frozenset)
        self.assertIn('ToolSearch', init_mod.SKIP_STREAM_TOOLS)
        self.assertIn('SendMessage', init_mod.SKIP_STREAM_TOOLS)


class TestInitExtractSessionId(unittest.TestCase):
    def test_extracts_first_8_chars_of_uuid(self):
        path = ('~/.claude/projects/foo/'
                '00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl')
        self.assertEqual(init_mod._extract_session_id(path), '00893aaf')

    def test_empty_path_returns_none(self):
        self.assertIsNone(init_mod._extract_session_id(''))

    def test_none_path_returns_none(self):
        self.assertIsNone(init_mod._extract_session_id(None))

    def test_no_uuid_returns_none(self):
        self.assertIsNone(init_mod._extract_session_id('/tmp/no-uuid-here.jsonl'))

    def test_uppercase_uuid_is_not_matched(self):
        # pattern is lowercase-hex only
        path = '/x/00893AAF-19FA-41D2-8238-13269B9B3CA0.jsonl'
        self.assertIsNone(init_mod._extract_session_id(path))


class TestInitIsBypassWriteAttempt(unittest.TestCase):
    # Bash vector
    def test_bash_echo_bypass_true_into_setup_file_blocked(self):
        ti = {'command': 'echo \'{"bypass": true}\' > .serena/swe-setup-complete.json'}
        self.assertTrue(init_mod._is_bypass_write_attempt('Bash', ti))

    def test_bash_spaced_bypass_true_variant_blocked(self):
        ti = {'command': 'sed -i s/x/bypass true/ .serena/swe-setup-complete.json'}
        self.assertTrue(init_mod._is_bypass_write_attempt('Bash', ti))

    def test_bash_bypass_script_is_allowed(self):
        # the dedicated user-only bypass script is the sanctioned write path
        ti = {'command': 'python3 scripts/swe-bypass.py --enable swe-setup-complete'}
        self.assertFalse(init_mod._is_bypass_write_attempt('Bash', ti))

    def test_bash_touching_other_file_not_blocked(self):
        ti = {'command': 'echo \'{"bypass": true}\' > /tmp/other.json'}
        self.assertFalse(init_mod._is_bypass_write_attempt('Bash', ti))

    def test_bash_command_without_bypass_not_blocked(self):
        ti = {'command': 'cat .serena/swe-setup-complete.json'}
        self.assertFalse(init_mod._is_bypass_write_attempt('Bash', ti))

    # Edit/Write vector
    def test_edit_bypass_true_into_setup_file_blocked(self):
        ti = {'file_path': '.serena/swe-setup-complete.json',
              'new_string': '{"bypass": true}'}
        self.assertTrue(init_mod._is_bypass_write_attempt('Edit', ti))

    def test_write_bypass_true_via_content_blocked(self):
        ti = {'file_path': '/p/.serena/swe-setup-complete.json',
              'content': "{ 'bypass' : true }"}
        self.assertTrue(init_mod._is_bypass_write_attempt('Write', ti))

    def test_edit_memory_name_target_blocked(self):
        ti = {'memory_name': 'swe-setup-complete', 'repl': '{"bypass":true}'}
        self.assertTrue(init_mod._is_bypass_write_attempt('Write', ti))

    def test_edit_bypass_false_not_blocked(self):
        ti = {'file_path': '.serena/swe-setup-complete.json',
              'content': '{"bypass": false}'}
        self.assertFalse(init_mod._is_bypass_write_attempt('Edit', ti))

    def test_edit_other_file_not_blocked(self):
        ti = {'file_path': '/p/config.json', 'content': '{"bypass": true}'}
        self.assertFalse(init_mod._is_bypass_write_attempt('Edit', ti))

    def test_none_tool_input_not_blocked(self):
        self.assertFalse(init_mod._is_bypass_write_attempt('Edit', None))
        self.assertFalse(init_mod._is_bypass_write_attempt('Bash', None))


class TestInitCheckWorkingMemoryExists(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self._orig_root = init_mod.get_project_root
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        init_mod.get_project_root = lambda: self.root

    def tearDown(self):
        init_mod.get_project_root = self._orig_root
        self.tmp.cleanup()
        reset_caches()

    def _state_dir(self):
        d = os.path.join(self.root, '.serena', 'swe-state')
        os.makedirs(d, exist_ok=True)
        return d

    def _memories_dir(self):
        d = os.path.join(self.root, '.serena', 'memories')
        os.makedirs(d, exist_ok=True)
        return d

    def test_valid_state_file_present(self):
        sid = 'abc12345'
        with open(os.path.join(self._state_dir(), f'{sid}.state'), 'w') as f:
            f.write('{"current_state": "WF_EXECUTE"}')
        ok, msg = init_mod.check_working_memory_exists(sid)
        self.assertTrue(ok)
        self.assertIn('state file', msg)

    def test_empty_state_file_falls_through_to_missing_memories(self):
        sid = 'abc12345'
        # empty content -> not treated as valid; no memories dir -> missing
        with open(os.path.join(self._state_dir(), f'{sid}.state'), 'w') as f:
            f.write('   ')
        ok, msg = init_mod.check_working_memory_exists(sid)
        self.assertFalse(ok)
        self.assertIn('No .serena/memories directory', msg)

    def test_no_memories_dir_returns_false(self):
        ok, msg = init_mod.check_working_memory_exists('deadbeef')
        self.assertFalse(ok)
        self.assertIn('No .serena/memories directory', msg)

    def test_memories_dir_but_no_wm_file(self):
        self._memories_dir()
        ok, msg = init_mod.check_working_memory_exists('deadbeef')
        self.assertFalse(ok)
        self.assertIn('No state file', msg)

    def test_valid_wm_file_with_workflow_context(self):
        sid = 'feedface'
        mem = self._memories_dir()
        with open(os.path.join(mem, f'WM_{sid}.md'), 'w') as f:
            f.write('# WM\n## Workflow Context\n**Current State**: WF_EXECUTE\n')
        ok, msg = init_mod.check_working_memory_exists(sid)
        self.assertTrue(ok)
        self.assertIn('WM file', msg)

    def test_wm_file_missing_context_but_filename_matches(self):
        sid = 'feedface'
        mem = self._memories_dir()
        with open(os.path.join(mem, f'WM_{sid}.md'), 'w') as f:
            f.write('nothing structured here\n')
        ok, msg = init_mod.check_working_memory_exists(sid)
        self.assertTrue(ok)
        self.assertIn('filename match', msg)

    def test_no_session_id_scans_all_wm_files(self):
        mem = self._memories_dir()
        with open(os.path.join(mem, 'WM_something.md'), 'w') as f:
            f.write('## Workflow Context\n**Current State**: WF_INIT\n')
        ok, msg = init_mod.check_working_memory_exists(None)
        self.assertTrue(ok)
        self.assertIn('WM file', msg)


class TestInitCheckLiteMode(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self._orig_root = init_mod.get_project_root
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        init_mod.get_project_root = lambda: self.root

    def tearDown(self):
        init_mod.get_project_root = self._orig_root
        self.tmp.cleanup()
        reset_caches()

    def test_none_session_id_returns_false(self):
        self.assertFalse(init_mod.check_lite_mode(None))

    def test_no_lite_marker_returns_false(self):
        self.assertFalse(init_mod.check_lite_mode('abc12345'))

    def test_lite_marker_present_returns_true(self):
        sid = 'abc12345'
        mem = os.path.join(self.root, '.serena', 'memories')
        os.makedirs(mem, exist_ok=True)
        with open(os.path.join(mem, f'LITE_MODE_{sid}.md'), 'w') as f:
            f.write('lite')
        self.assertTrue(init_mod.check_lite_mode(sid))


class TestInitInjectMetadata(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write_state(self, sid, data):
        d = os.path.join(self.cwd, '.serena', 'swe-state')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f'{sid}.state'), 'w') as f:
            json.dump(data, f)

    def test_non_serena_tool_returns_none(self):
        self.assertIsNone(
            init_mod.inject_metadata('Bash', {'command': 'ls'}, 'abc12345', self.cwd)
        )

    def test_serena_tool_gets_metadata_from_state_file(self):
        sid = 'abc12345'
        self._write_state(sid, {'current_state': 'WF_EXECUTE',
                                'feature_keys': 'SWE'})
        ti = {'memory_name': 'wf/WF_EXECUTE'}
        out = init_mod.inject_metadata(
            'mcp__plugin_swe_serena__read_memory', ti, sid, self.cwd)
        self.assertIsNotNone(out)
        self.assertIn('_swe_metadata', out)
        meta = out['_swe_metadata']
        self.assertEqual(meta['session_id'], sid)
        self.assertEqual(meta['state'], 'WF_EXECUTE')
        self.assertEqual(meta['feature_keys'], 'SWE')
        # original input preserved and not mutated in place
        self.assertEqual(out['memory_name'], 'wf/WF_EXECUTE')
        self.assertNotIn('_swe_metadata', ti)

    def test_serena_alt_prefix_also_injected(self):
        sid = 'abc12345'
        out = init_mod.inject_metadata(
            'mcp__serena__list_memories', {}, sid, self.cwd)
        self.assertIsNotNone(out)
        self.assertIn('_swe_metadata', out)

    def test_serena_tool_with_no_state_file_gets_empty_state(self):
        sid = 'abc12345'  # no state file written
        out = init_mod.inject_metadata(
            'mcp__plugin_swe_serena__read_memory', {}, sid, self.cwd)
        self.assertIsNotNone(out)
        meta = out['_swe_metadata']
        self.assertEqual(meta['state'], '')
        self.assertEqual(meta['feature_keys'], '')
        self.assertEqual(meta['session_id'], sid)

    def test_malformed_state_json_is_swallowed(self):
        sid = 'abc12345'
        d = os.path.join(self.cwd, '.serena', 'swe-state')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f'{sid}.state'), 'w') as f:
            f.write('{not valid json')
        out = init_mod.inject_metadata(
            'mcp__plugin_swe_serena__read_memory', {}, sid, self.cwd)
        self.assertIsNotNone(out)
        # falls back to empty state, still injects
        self.assertEqual(out['_swe_metadata']['state'], '')


# ---------------------------------------------------------------------------
# swe_pre_tool_init_gate — two-tier degraded-mode circuit breaker (main()
# integration)
# ---------------------------------------------------------------------------
class TestInitGateDegradedModeIntegration(unittest.TestCase):
    """Drives init_mod.main() end-to-end: an INITIALIZED-but-not-session-
    initialized project, with a stream file already past the denial
    threshold, must unlock either Tier-1 recovery or Tier-2 degraded tools
    instead of denying forever.

    Tier 1 "recovery" (bare deny count >= 3, NO mcp_unavailable): Serena may
    be fully reachable — only recovery/diagnostic Bash unlocks (claude mcp
    list/get, ps/pgrep, restricted log reads, --reset-sentinel). NOT general
    Read/Grep/Glob/git status of the codebase.

    Tier 2 "degraded" (an mcp_unavailable event recorded): a genuine Serena
    connection failure — read-only tools (Read/Grep/Glob/LS/ToolSearch) and
    hardened read-only Bash unlock broadly. Edits/mutating Bash stay denied
    in both tiers.
    """

    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name
        os.makedirs(os.path.join(self.cwd, '.git'), exist_ok=True)
        os.makedirs(os.path.join(self.cwd, '.serena'), exist_ok=True)
        with open(os.path.join(self.cwd, '.serena', 'swe-setup-complete.json'), 'w') as f:
            json.dump({'complete': True}, f)
        self.session_id = 'deadbeef'
        self.transcript = f'/x/{self.session_id}-0000-0000-0000-000000000000.jsonl'

    def tearDown(self):
        self.tmp.cleanup()
        reset_caches()

    def _stream_path(self):
        d = os.path.join(self.cwd, '.serena', 'streams')
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, f'{self.session_id}.jsonl')

    def _write_denies(self, n):
        with open(self._stream_path(), 'w') as f:
            for _ in range(n):
                f.write(json.dumps({"type": "init_deny"}) + "\n")

    def _write_mcp_unavailable(self):
        with open(self._stream_path(), 'a') as f:
            f.write(json.dumps({"type": "mcp_unavailable"}) + "\n")
            f.write(json.dumps({"type": "degraded", "trigger": "mcp_unavailable"}) + "\n")

    def _run_main(self, tool_name, tool_input):
        import io
        import json as _json
        from unittest import mock
        payload = {
            'tool_name': tool_name,
            'tool_input': tool_input,
            'transcript_path': self.transcript,
            'cwd': self.cwd,
        }
        buf = io.StringIO()
        with mock.patch.object(sys, 'stdin', io.StringIO(_json.dumps(payload))), \
             mock.patch('select.select', return_value=([sys.stdin], [], [])), \
             mock.patch.object(os, 'getcwd', return_value=self.cwd), \
             mock.patch.dict(os.environ, {'CLAUDE_PROJECT_DIR': self.cwd}), \
             mock.patch('sys.stdout', buf):
            try:
                init_mod.main()
            except SystemExit:
                pass
        return _json.loads(buf.getvalue() or '{}')

    def test_below_threshold_bash_still_denied(self):
        self._write_denies(2)
        result = self._run_main('Bash', {'command': 'git status'})
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertEqual(decision, 'deny')

    # --- Tier 1: recovery (bare denies, Serena presumed reachable) ---------
    def test_tier1_recovery_claude_mcp_list_allowed(self):
        self._write_denies(3)
        result = self._run_main('Bash', {'command': 'claude mcp list'})
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertEqual(decision, 'allow')
        self.assertIn('recovery', result.get('systemMessage', '').lower())

    def test_tier1_recovery_ps_allowed(self):
        self._write_denies(3)
        result = self._run_main('Bash', {'command': 'ps aux | grep serena'})
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertEqual(decision, 'allow')

    def test_tier1_recovery_git_status_still_denied(self):
        # git status is NOT a recovery/diagnostic command — Tier 1 must not
        # unlock general codebase inspection while Serena may be fully up.
        self._write_denies(3)
        result = self._run_main('Bash', {'command': 'git status'})
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertEqual(decision, 'deny')

    def test_tier1_recovery_read_tool_still_denied(self):
        self._write_denies(3)
        result = self._run_main('Read', {'file_path': 'src/x.py'})
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertEqual(decision, 'deny')

    def test_tier1_recovery_grep_still_denied(self):
        self._write_denies(3)
        result = self._run_main('Grep', {'pattern': 'foo'})
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertEqual(decision, 'deny')

    def test_tier1_recovery_edit_still_denied(self):
        self._write_denies(3)
        result = self._run_main('Edit', {'file_path': '/x/y.py'})
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertEqual(decision, 'deny')

    def test_tier1_recovery_mutating_bash_still_denied(self):
        self._write_denies(3)
        result = self._run_main('Bash', {'command': 'rm -rf /tmp/x'})
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertEqual(decision, 'deny')

    # --- Tier 2: degraded (confirmed mcp_unavailable) -----------------------
    def test_tier2_degraded_read_tool_allowed(self):
        self._write_mcp_unavailable()
        result = self._run_main('Read', {'file_path': '/x/y.py'})
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertEqual(decision, 'allow')
        self.assertIn('degraded', result.get('systemMessage', '').lower())

    def test_tier2_degraded_readonly_bash_allowed(self):
        self._write_mcp_unavailable()
        result = self._run_main('Bash', {'command': 'git status'})
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertEqual(decision, 'allow')

    def test_tier2_degraded_mutating_bash_still_denied(self):
        self._write_mcp_unavailable()
        result = self._run_main('Bash', {'command': 'rm -rf /tmp/x'})
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertEqual(decision, 'deny')

    def test_tier2_degraded_edit_still_denied(self):
        self._write_mcp_unavailable()
        result = self._run_main('Edit', {'file_path': '/x/y.py'})
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertEqual(decision, 'deny')

    def test_tier2_degraded_bypass_strings_all_denied(self):
        # Every hardened-classifier bypass vector must stay denied even in
        # confirmed Tier-2 degraded mode.
        self._write_mcp_unavailable()
        for cmd in (
            'cat f > /etc/hosts',
            'cat `id`',
            'grep x y | tee /etc/passwd',
            'find . -exec rm {} \\;',
            'find . -execdir rm {} \\;',
            'find . -delete',
            'sed -i s/x/y/ file',
            'perl -i -pe "s/x/y/" file',
            'echo $(whoami)',
            'cat <(echo hi)',
            'echo hi >(cat)',
            'ls >> /tmp/out',
            'python3 -m unittest discover',
            'pytest tests/',
            'git commit -m x',
            'git push',
            'xargs rm',
        ):
            result = self._run_main('Bash', {'command': cmd})
            decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
            self.assertEqual(decision, 'deny', cmd)

    def test_tier2_degraded_benign_commands_allowed(self):
        self._write_mcp_unavailable()
        for cmd in (
            'git status',
            'ls -la .serena',
            'cat ~/.serena/logs/x.txt 2>/dev/null | tail -20',
        ):
            result = self._run_main('Bash', {'command': cmd})
            decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
            self.assertEqual(decision, 'allow', cmd)

    def test_docread_clears_tier2_degraded_and_resumes_normal_deny(self):
        self._write_mcp_unavailable()
        with open(self._stream_path(), 'a') as f:
            f.write(json.dumps({"type": "docread", "name": "wf/WF_INIT"}) + "\n")
        result = self._run_main('Bash', {'command': 'rm -rf /tmp/x'})
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertEqual(decision, 'deny')

    def test_docread_clears_tier1_recovery_and_resumes_normal_deny(self):
        self._write_denies(3)
        with open(self._stream_path(), 'a') as f:
            f.write(json.dumps({"type": "docread", "name": "wf/WF_INIT"}) + "\n")
        result = self._run_main('Bash', {'command': 'claude mcp list'})
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertEqual(decision, 'deny')


class TestInitGateSpawnedAgentExemption(unittest.TestCase):
    """Spawned agents (non-empty agent_id) must never see the workflow-init
    denial/directive text — they are explicitly instructed to bypass
    WF_INIT. The bypass-write hard guard and the (invisible) _swe_metadata
    injection are the ONLY things that still apply to them."""

    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name
        os.makedirs(os.path.join(self.cwd, '.git'), exist_ok=True)
        os.makedirs(os.path.join(self.cwd, '.serena'), exist_ok=True)
        with open(os.path.join(self.cwd, '.serena', 'swe-setup-complete.json'), 'w') as f:
            json.dump({'complete': True}, f)
        # NO session state / WM / sentinel written for this session id at
        # all — an uninitialized session, from the main session's PoV.
        self.session_id = 'deadbeef'
        self.transcript = f'/x/{self.session_id}-0000-0000-0000-000000000000.jsonl'

    def tearDown(self):
        self.tmp.cleanup()
        reset_caches()

    def _run_main(self, tool_name, tool_input, **extra):
        import io
        import json as _json
        from unittest import mock
        payload = {
            'tool_name': tool_name,
            'tool_input': tool_input,
            'transcript_path': self.transcript,
            'cwd': self.cwd,
        }
        payload.update(extra)
        buf = io.StringIO()
        with mock.patch.object(sys, 'stdin', io.StringIO(_json.dumps(payload))), \
             mock.patch('select.select', return_value=([sys.stdin], [], [])), \
             mock.patch.object(os, 'getcwd', return_value=self.cwd), \
             mock.patch.dict(os.environ, {'CLAUDE_PROJECT_DIR': self.cwd}), \
             mock.patch('sys.stdout', buf):
            try:
                init_mod.main()
            except SystemExit:
                pass
        return _json.loads(buf.getvalue() or '{}')

    def test_spawned_agent_uninitialized_session_no_deny(self):
        # Positive control first: main session, same uninitialized state,
        # IS denied — proves the fixture actually exercises the init gate.
        result = self._run_main('Bash', {'command': 'ls'})
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertEqual(decision, 'deny')

        # Spawned agent, identical payload plus a non-empty agent_id: no deny.
        result = self._run_main('Bash', {'command': 'ls'}, agent_id='sub-123')
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertNotEqual(decision, 'deny')

    def test_spawned_agent_bypass_write_attempt_still_denied(self):
        # The hard guard against setting "bypass": true must survive the
        # spawned-agent exemption — it is a security guard, not a workflow
        # directive.
        result = self._run_main(
            'Edit',
            {'file_path': '.serena/swe-setup-complete.json',
             'new_string': '{"bypass": true}'},
            agent_id='sub-123')
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertEqual(decision, 'deny')
        self.assertIn('BLOCKED',
                       result['hookSpecificOutput']['permissionDecisionReason'])

    def test_spawned_agent_gets_no_workflow_directive_text(self):
        result = self._run_main('Grep', {'pattern': 'x'}, agent_id='sub-123')
        # No deny, and no workflow-init text leaked via any other field.
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertNotEqual(decision, 'deny')
        blob = json.dumps(result)
        self.assertNotIn('WF_INIT', blob)
        self.assertNotIn('WORKFLOW NOT INITIALIZED', blob)

    def test_spawned_agent_serena_tool_still_gets_metadata_injection(self):
        # The _swe_metadata injection is invisible to the model and must
        # still apply — it is not a workflow directive.
        result = self._run_main(
            'mcp__plugin_swe_serena__read_memory',
            {'memory_name': 'wf/WF_EXECUTE'},
            agent_id='sub-123')
        updated = result.get('hookSpecificOutput', {}).get('updatedInput')
        self.assertIsNotNone(updated)
        self.assertIn('_swe_metadata', updated)


class TestInitGateScopeGuardIntegration(unittest.TestCase):
    """Drives init_mod.main() for a NAMED spawned agent (non-empty agent_id)
    through the per-agent scope guard (core.scope_guard): a bounded
    tool-call budget and a per-kind consecutive-failure streak, scoped
    entirely to that agent's own logged events."""

    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name
        os.makedirs(os.path.join(self.cwd, '.git'), exist_ok=True)
        os.makedirs(os.path.join(self.cwd, '.serena'), exist_ok=True)
        with open(os.path.join(self.cwd, '.serena', 'swe-setup-complete.json'), 'w') as f:
            json.dump({'complete': True}, f)
        self.session_id = 'deadbeef'
        self.transcript = f'/x/{self.session_id}-0000-0000-0000-000000000000.jsonl'
        self.agent_id = 'sub-scope-1'

    def tearDown(self):
        self.tmp.cleanup()
        reset_caches()

    def _stream_path(self):
        d = os.path.join(self.cwd, '.serena', 'streams')
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, f'{self.session_id}.jsonl')

    def _write_events(self, events):
        with open(self._stream_path(), 'w') as f:
            for e in events:
                f.write(json.dumps(e) + '\n')

    def _read_events(self):
        path = self._stream_path()
        if not os.path.exists(path):
            return []
        with open(path, 'r') as f:
            return [json.loads(line) for line in f if line.strip()]

    def _run_main(self, tool_name, tool_input, **extra):
        import io
        import json as _json
        from unittest import mock
        payload = {
            'tool_name': tool_name,
            'tool_input': tool_input,
            'transcript_path': self.transcript,
            'cwd': self.cwd,
            'agent_id': self.agent_id,
        }
        payload.update(extra)
        buf = io.StringIO()
        with mock.patch.object(sys, 'stdin', io.StringIO(_json.dumps(payload))), \
             mock.patch('select.select', return_value=([sys.stdin], [], [])), \
             mock.patch.object(os, 'getcwd', return_value=self.cwd), \
             mock.patch.dict(os.environ, {'CLAUDE_PROJECT_DIR': self.cwd}), \
             mock.patch('sys.stdout', buf):
            try:
                init_mod.main()
            except SystemExit:
                pass
        return _json.loads(buf.getvalue() or '{}')

    def test_subagent_under_budget_allowed_and_logged(self):
        self._write_events([
            {'type': 'agent_spawn', 'agent': self.agent_id, 'model': 'sonnet', 'budget': 60},
        ])
        result = self._run_main('Bash', {'command': 'ls'})
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertNotEqual(decision, 'deny')
        events = self._read_events()
        calls = [e for e in events if e.get('type') == 'agent_call']
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['agent'], self.agent_id)
        self.assertEqual(calls[0]['tool'], 'Bash')

    def test_subagent_over_budget_denied_with_scope_gate(self):
        events = [{'type': 'agent_spawn', 'agent': self.agent_id, 'model': 'haiku', 'budget': 3}]
        events += [{'type': 'agent_call', 'agent': self.agent_id, 'tool': 'Bash'} for _ in range(3)]
        self._write_events(events)
        result = self._run_main('Bash', {'command': 'ls'})
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertEqual(decision, 'deny')
        reason = result['hookSpecificOutput']['permissionDecisionReason']
        self.assertIn('[scope-gate]', reason)
        self.assertIn('budget exhausted', reason)

    def test_two_consecutive_test_failures_deny_edit_but_allow_read(self):
        self._write_events([
            {'type': 'agent_spawn', 'agent': self.agent_id, 'model': 'sonnet', 'budget': 60},
            {'type': 'agent_fail', 'agent': self.agent_id, 'kind': 'test'},
            {'type': 'agent_fail', 'agent': self.agent_id, 'kind': 'test'},
        ])
        edit_result = self._run_main('Edit', {'file_path': '/x/y.py'})
        decision = edit_result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertEqual(decision, 'deny')
        reason = edit_result['hookSpecificOutput']['permissionDecisionReason']
        self.assertIn('[scope-gate]', reason)
        self.assertIn('failed 2 times in a row', reason)

        read_result = self._run_main('Read', {'file_path': '/x/y.py'})
        read_decision = read_result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertNotEqual(read_decision, 'deny')

    def test_scope_extend_lifts_trip_and_resets_streak(self):
        self._write_events([
            {'type': 'agent_spawn', 'agent': self.agent_id, 'model': 'sonnet', 'budget': 60},
            {'type': 'agent_fail', 'agent': self.agent_id, 'kind': 'edit'},
            {'type': 'agent_fail', 'agent': self.agent_id, 'kind': 'edit'},
        ])
        denied = self._run_main('Edit', {'file_path': '/x/y.py'})
        self.assertEqual(
            denied.get('hookSpecificOutput', {}).get('permissionDecision'), 'deny')

        with open(self._stream_path(), 'a') as f:
            f.write(json.dumps(
                {'type': 'scope_extend', 'agent': self.agent_id, 'budget_add': 30}) + '\n')

        allowed = self._run_main('Edit', {'file_path': '/x/y.py'})
        self.assertNotEqual(
            allowed.get('hookSpecificOutput', {}).get('permissionDecision'), 'deny')

    def test_other_agents_events_do_not_affect_this_agent(self):
        self._write_events([
            {'type': 'agent_fail', 'agent': 'someone-else', 'kind': 'test'},
            {'type': 'agent_fail', 'agent': 'someone-else', 'kind': 'test'},
        ])
        result = self._run_main('Edit', {'file_path': '/x/y.py'})
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertNotEqual(decision, 'deny')

    def test_no_agent_id_skips_scope_guard(self):
        # No agent_id at all -> not a NAMED spawned agent per get_agent_id,
        # so is_spawned_agent() may still be False here (agent_id/agentId are
        # the ONLY signals checked) and the call falls through to the
        # ordinary uninitialized-session denial instead of the scope guard.
        result = self._run_main('Bash', {'command': 'ls'}, agent_id='')
        # Whatever the outcome, it must not carry a [scope-gate] message.
        blob = json.dumps(result)
        self.assertNotIn('[scope-gate]', blob)


# ---------------------------------------------------------------------------
# swe_pre_bash_test_gate
# ---------------------------------------------------------------------------
class TestBashTestGateConstants(unittest.TestCase):
    def test_test_command_patterns_shape(self):
        # TEST_COMMAND_PATTERNS is imported into this hook module from
        # swe_hooks.core.scope_guard (single source of truth, shared with
        # scope_guard.classify_kind's 'test' classification) — same list
        # object, same assertions as when it was defined locally.
        self.assertIsInstance(bash_mod.TEST_COMMAND_PATTERNS, list)
        # Broadened beyond Playwright: unittest/pytest, npm/npx test
        # runners, phpunit, go test, cargo test.
        self.assertTrue(len(bash_mod.TEST_COMMAND_PATTERNS) >= 7)
        self.assertIn(r'\bnpx\s+playwright\s+test\b',
                      bash_mod.TEST_COMMAND_PATTERNS)

    def test_test_command_patterns_is_scope_guard_source(self):
        scope_guard = import_core("swe_hooks.core.scope_guard")
        self.assertIs(bash_mod.TEST_COMMAND_PATTERNS,
                      scope_guard.TEST_COMMAND_PATTERNS)


class TestBashGetTestSentinelPath(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self._orig = bash_mod.get_stream_dir
        self.tmp = tempfile.TemporaryDirectory()
        self.stream_dir = os.path.join(self.tmp.name, '.serena', 'streams')
        os.makedirs(self.stream_dir, exist_ok=True)
        bash_mod.get_stream_dir = lambda: self.stream_dir

    def tearDown(self):
        bash_mod.get_stream_dir = self._orig
        self.tmp.cleanup()
        reset_caches()

    def test_sentinel_path_shape(self):
        p = bash_mod.get_test_sentinel_path('abc12345')
        self.assertEqual(p, os.path.join(self.stream_dir, '.test_feature_abc12345'))
        self.assertEqual(os.path.basename(p), '.test_feature_abc12345')

    def test_sentinel_path_uses_session_id(self):
        p = bash_mod.get_test_sentinel_path('deadbeef')
        self.assertTrue(p.endswith('.test_feature_deadbeef'))


class TestBashLoadPolicy(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self._orig = bash_mod.get_project_root
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        bash_mod.get_project_root = lambda: self.root

    def tearDown(self):
        bash_mod.get_project_root = self._orig
        self.tmp.cleanup()
        reset_caches()

    def _write_policy(self, obj):
        d = os.path.join(self.root, '.serena')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'bash-policy.json'), 'w') as f:
            json.dump(obj, f)

    def test_missing_file_returns_empty_list(self):
        self.assertEqual(bash_mod.load_bash_policy(), [])

    def test_valid_rules_are_loaded(self):
        rules = [
            {'pattern': r'docker\s+exec.*\bwp\b', 'message': 'use wp_cli MCP'},
            {'pattern': r'\bgit\s+commit\b', 'message': 'user handles git'},
        ]
        self._write_policy(rules)
        loaded = bash_mod.load_bash_policy()
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]['pattern'], r'docker\s+exec.*\bwp\b')
        self.assertEqual(loaded[1]['message'], 'user handles git')

    def test_non_list_json_returns_empty(self):
        self._write_policy({'pattern': 'x', 'message': 'y'})  # dict, not list
        self.assertEqual(bash_mod.load_bash_policy(), [])

    def test_malformed_rules_are_filtered_out(self):
        rules = [
            {'pattern': 'ok', 'message': 'good'},   # kept
            {'pattern': 'no-message'},              # dropped: missing message
            {'message': 'no-pattern'},              # dropped: missing pattern
            {'pattern': '', 'message': 'empty pat'},  # dropped: falsy pattern
            'not-a-dict',                            # dropped: not a dict
        ]
        self._write_policy(rules)
        loaded = bash_mod.load_bash_policy()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]['pattern'], 'ok')

    def test_invalid_json_file_returns_empty(self):
        d = os.path.join(self.root, '.serena')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'bash-policy.json'), 'w') as f:
            f.write('{ not valid json ')
        self.assertEqual(bash_mod.load_bash_policy(), [])

    def test_empty_list_returns_empty(self):
        self._write_policy([])
        self.assertEqual(bash_mod.load_bash_policy(), [])


class TestBashDenialEscalation(unittest.TestCase):
    """Deterministic-denial tracking: command_hash, count_prior_denials,
    build_denial_message escalation + compound note."""

    RULE = {'pattern': r'\bgit\s+push\b', 'message': 'push needs approval'}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stream = os.path.join(self.tmp.name, 'sess.jsonl')

    def tearDown(self):
        self.tmp.cleanup()

    def _write_events(self, events):
        with open(self.stream, 'w') as f:
            for e in events:
                f.write(json.dumps(e) + '\n')

    def test_command_hash_stable_and_trimmed(self):
        self.assertEqual(bash_mod.command_hash('git push'),
                         bash_mod.command_hash('  git push  '))
        self.assertNotEqual(bash_mod.command_hash('git push'),
                            bash_mod.command_hash('git push origin main'))

    def test_count_prior_denials_counts_matching_hash_only(self):
        h = bash_mod.command_hash('git push')
        other = bash_mod.command_hash('npm run x')
        self._write_events([
            {'type': 'bash_deny', 'h': h},
            {'type': 'tool', 'name': 'Bash'},
            {'type': 'bash_deny', 'h': other},
            {'type': 'bash_deny', 'h': h},
        ])
        self.assertEqual(bash_mod.count_prior_denials(self.stream, h), 2)
        self.assertEqual(bash_mod.count_prior_denials(self.stream, other), 1)

    def test_count_prior_denials_missing_stream_is_zero(self):
        self.assertEqual(bash_mod.count_prior_denials(
            os.path.join(self.tmp.name, 'nope.jsonl'), 'abc'), 0)

    def test_first_denial_has_no_escalation(self):
        msg = bash_mod.build_denial_message(self.RULE, 'git push', 0)
        self.assertIn('push needs approval', msg)
        self.assertNotIn('DETERMINISTIC DENIAL', msg)

    def test_first_repeat_escalates_but_does_not_hard_stop(self):
        msg = bash_mod.build_denial_message(self.RULE, 'git push', 1)
        self.assertIn('DETERMINISTIC DENIAL ×2', msg)
        self.assertIn('COMMAND STRING must change', msg)
        self.assertNotIn('HARD STOP', msg)

    def test_third_denial_hard_stops(self):
        msg = bash_mod.build_denial_message(self.RULE, 'git push', 2)
        self.assertIn('HARD STOP', msg)
        self.assertIn('×3', msg)
        self.assertIn('ask the user', msg)

    def test_compound_command_gets_none_ran_note(self):
        msg = bash_mod.build_denial_message(
            self.RULE, 'docker cp a b && git push', 0)
        self.assertIn('NONE of this compound command ran', msg)

    def test_simple_command_has_no_compound_note(self):
        msg = bash_mod.build_denial_message(self.RULE, 'git push', 0)
        self.assertNotIn('compound', msg)


class TestBashMissingCdAutoRepair(unittest.TestCase):
    """Auto-repair for the missing-absolute-cd rule: a repo-targeting command
    that lacks a leading `cd /` is deterministically un-satisfiable by a bare
    resend, so the gate rewrites it (prepend `cd <cwd>`, allow) rather than
    denying it repeatedly."""

    # The real missing-cd rule from .serena/bash-policy.json (negative lookahead).
    CD_RULE = {
        'pattern': r'^(?!.*\bcd\s+/)(?:.*(?:^|[\n;]|&&|\|\|)\s*)?'
                   r'(npm\s+run\s|yarn\s+(run\s+)?\w|gulp\b)',
        'message': 'Repo-targeting commands need an ABSOLUTE `cd`.',
    }
    OTHER_RULE = {'pattern': r'\bgit\s+push\b', 'message': 'push needs approval'}

    def test_identifies_missing_cd_rule(self):
        self.assertTrue(bash_mod.is_missing_cd_rule(self.CD_RULE))

    def test_non_cd_rule_is_not_missing_cd(self):
        self.assertFalse(bash_mod.is_missing_cd_rule(self.OTHER_RULE))

    def test_auto_repair_prepends_cd_to_cwd(self):
        got = bash_mod.auto_repair_cd(
            'npm run format:plugin -- em-events-calendar 2>&1',
            '/Users/webdev/LocalSites/convenely/convenely_plugin_repo')
        self.assertEqual(
            got,
            'cd /Users/webdev/LocalSites/convenely/convenely_plugin_repo\n'
            'npm run format:plugin -- em-events-calendar 2>&1')

    def test_repaired_command_passes_the_cd_rule(self):
        repaired = bash_mod.auto_repair_cd('npm run build', '/repo/root')
        # The whole point: the rewritten command no longer violates the rule.
        self.assertIsNone(
            bash_mod.check_bash_policy_against([self.CD_RULE], repaired))

    def test_no_cwd_cannot_repair(self):
        self.assertIsNone(bash_mod.auto_repair_cd('npm run build', ''))
        self.assertIsNone(bash_mod.auto_repair_cd('npm run build', None))

    def test_relative_cwd_cannot_repair(self):
        # Prepending a non-absolute cwd would not satisfy the `cd /` rule.
        self.assertIsNone(bash_mod.auto_repair_cd('npm run build', 'relative/dir'))


class TestBashTestGateSpawnedAgentExemption(unittest.TestCase):
    """Spawned agents are exempt from the test-doc requirement gate
    regardless of their own docreads — enforcement moved to DELEGATION time
    (swe_pre_agent_model_gate.py's [sweep-gate]) instead of per-test-command.
    The main agent is still gated on the FEATURE_TESTS sentinel, and the
    project Bash-policy check still applies to everyone, spawned or not."""

    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self._orig_root = bash_mod.get_project_root
        bash_mod.get_project_root = lambda: self.root
        from swe_hooks.core import session as core_session
        self._orig_session_root = core_session.get_project_root
        core_session.get_project_root = lambda: self.root
        self.streams_dir = os.path.join(self.root, '.serena', 'streams')
        os.makedirs(self.streams_dir, exist_ok=True)
        self._orig_stream_path = bash_mod.get_stream_path
        bash_mod.get_stream_path = (
            lambda sid: os.path.join(self.streams_dir, f'{sid}.jsonl'))

    def tearDown(self):
        bash_mod.get_project_root = self._orig_root
        from swe_hooks.core import session as core_session
        core_session.get_project_root = self._orig_session_root
        bash_mod.get_stream_path = self._orig_stream_path
        self.tmp.cleanup()
        reset_caches()

    def _write_test_doc(self):
        dev_dir = os.path.join(self.root, '.serena', 'memory', 'feature')
        os.makedirs(dev_dir, exist_ok=True)
        with open(os.path.join(dev_dir, 'FEATURE_TESTS.md'), 'w') as f:
            f.write('# FEATURE_TESTS\n')

    def _write_stream(self, session_id, events):
        path = os.path.join(self.streams_dir, f'{session_id}.jsonl')
        with open(path, 'w') as f:
            for e in events:
                f.write(json.dumps(e) + '\n')

    def _run_main(self, tool_input, **extra):
        import io
        import json as _json
        from unittest import mock
        payload = {
            'tool_name': 'Bash',
            'tool_input': tool_input,
            'transcript_path': '/x/deadbeef-0000-0000-0000-000000000000.jsonl',
            'cwd': self.root,
        }
        payload.update(extra)
        buf = io.StringIO()
        with mock.patch.object(sys, 'stdin', io.StringIO(_json.dumps(payload))), \
             mock.patch('select.select', return_value=([sys.stdin], [], [])), \
             mock.patch('sys.stdout', buf):
            try:
                bash_mod.main()
            except SystemExit:
                pass
        out = buf.getvalue()
        return _json.loads(out) if out else {}

    def test_main_session_playwright_without_sentinel_is_blocked(self):
        # Positive control: no agent_id, no sentinel -> blocked.
        result = self._run_main({'command': 'npx playwright test'})
        text = json.dumps(result)
        self.assertIn('TEST COMMAND BLOCKED', text)

    def test_no_test_docs_in_project_spawned_agent_allowed(self):
        # Project documents no test harness at all -> nothing to require.
        result = self._run_main(
            {'command': 'npx playwright test'}, agent_id='sub-123')
        self.assertEqual(result, {})

    def test_spawned_agent_without_own_docread_allowed(self):
        # Spawned agents are exempt regardless of docreads — enforcement is
        # at delegation time now, not per test command.
        self._write_test_doc()
        result = self._run_main(
            {'command': 'npx playwright test'}, agent_id='sub-123')
        self.assertEqual(result, {})

    def test_spawned_agent_with_docread_still_allowed(self):
        self._write_test_doc()
        self._write_stream('deadbeef', [
            {'type': 'docread', 'name': 'feature/FEATURE_TESTS', 'agent': 'sub-123'},
        ])
        result = self._run_main(
            {'command': 'npx playwright test'}, agent_id='sub-123')
        self.assertEqual(result, {})

    def test_spawned_agent_still_subject_to_bash_policy(self):
        # The project Bash-policy deny-list applies to every caller,
        # spawned or not — checked before the (now skipped) test-doc gate.
        policy_dir = os.path.join(self.root, '.serena')
        os.makedirs(policy_dir, exist_ok=True)
        with open(os.path.join(policy_dir, 'bash-policy.json'), 'w') as f:
            json.dump([{"pattern": "npx playwright test",
                        "message": "use the sanctioned test runner"}], f)
        result = self._run_main(
            {'command': 'npx playwright test'}, agent_id='sub-123')
        self.assertIn('BASH POLICY VIOLATION', json.dumps(result))

    def test_unittest_command_detected(self):
        result = self._run_main(
            {'command': 'python3 -m unittest discover -s tests'})
        self.assertIn('TEST COMMAND BLOCKED', json.dumps(result))

    def test_pytest_command_detected(self):
        result = self._run_main({'command': 'pytest tests/'})
        self.assertIn('TEST COMMAND BLOCKED', json.dumps(result))

    def test_npm_test_command_detected(self):
        result = self._run_main({'command': 'npm test'})
        self.assertIn('TEST COMMAND BLOCKED', json.dumps(result))

    def test_npm_run_test_command_detected(self):
        result = self._run_main({'command': 'npm run test'})
        self.assertIn('TEST COMMAND BLOCKED', json.dumps(result))

    def test_npx_jest_command_detected(self):
        result = self._run_main({'command': 'npx jest'})
        self.assertIn('TEST COMMAND BLOCKED', json.dumps(result))

    def test_npx_vitest_command_detected(self):
        result = self._run_main({'command': 'npx vitest run'})
        self.assertIn('TEST COMMAND BLOCKED', json.dumps(result))

    def test_phpunit_command_detected(self):
        result = self._run_main({'command': 'vendor/bin/phpunit'})
        self.assertIn('TEST COMMAND BLOCKED', json.dumps(result))

    def test_go_test_command_detected(self):
        result = self._run_main({'command': 'go test ./...'})
        self.assertIn('TEST COMMAND BLOCKED', json.dumps(result))

    def test_cargo_test_command_detected(self):
        result = self._run_main({'command': 'cargo test'})
        self.assertIn('TEST COMMAND BLOCKED', json.dumps(result))

    def test_non_test_command_not_gated(self):
        result = self._run_main({'command': 'ls -la'})
        self.assertEqual(result, {})


search_docs_mod = import_hook("pre/swe_pre_search_docs_gate")


class TestSearchDocsGateBudget(unittest.TestCase):
    """Budget semantics: one docread clears the gate for the next
    GATED_CALL_BUDGET gated calls; the next call after that re-fires.
    Prompt markers are irrelevant — clearance survives turn boundaries."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stream = os.path.join(self.tmp.name, 'sess.jsonl')

    def tearDown(self):
        self.tmp.cleanup()

    def _write_events(self, events):
        with open(self.stream, 'w') as f:
            for e in events:
                f.write(json.dumps(e) + '\n')

    def test_budget_constant_is_fifteen(self):
        self.assertEqual(search_docs_mod.GATED_CALL_BUDGET, 15)

    def test_no_docread_denies(self):
        self._write_events([{'type': 'prompt'}, {'type': 'search'}])
        self.assertFalse(search_docs_mod.docs_budget_allows(self.stream))

    def test_empty_stream_denies(self):
        self._write_events([])
        self.assertFalse(search_docs_mod.docs_budget_allows(self.stream))

    def test_docread_grants_budget(self):
        self._write_events([{'type': 'prompt'}, {'type': 'docread'}])
        self.assertTrue(search_docs_mod.docs_budget_allows(self.stream))

    def test_budget_survives_turn_boundary(self):
        # docread in an EARLIER turn still clears — no per-prompt re-arm.
        self._write_events([
            {'type': 'docread'},
            {'type': 'prompt'},
            {'type': 'gated'},
        ])
        self.assertTrue(search_docs_mod.docs_budget_allows(self.stream))

    def test_budget_not_exhausted_below_budget(self):
        self._write_events([{'type': 'docread'}]
                           + [{'type': 'gated'}] * (search_docs_mod.GATED_CALL_BUDGET - 1))
        self.assertTrue(search_docs_mod.docs_budget_allows(self.stream))

    def test_budget_exhausted_at_budget(self):
        self._write_events([{'type': 'docread'}]
                           + [{'type': 'gated'}] * search_docs_mod.GATED_CALL_BUDGET)
        self.assertFalse(search_docs_mod.docs_budget_allows(self.stream))

    def test_new_docread_refills_budget(self):
        self._write_events(
            [{'type': 'docread'}]
            + [{'type': 'gated'}] * search_docs_mod.GATED_CALL_BUDGET
            + [{'type': 'docread', 'name': 'feature/other'}])
        self.assertTrue(search_docs_mod.docs_budget_allows(self.stream))

    def test_gate_and_record_depletes_budget(self):
        # After one docread (no sweep sentinel): exactly GATED_CALL_BUDGET
        # calls pass, then deny.
        self._write_events([{'type': 'docread'}])
        n = search_docs_mod.GATED_CALL_BUDGET
        verdicts = [search_docs_mod.gate_and_record(self.stream) for _ in range(n + 1)]
        self.assertEqual(verdicts, [True] * n + [False])

    def test_deny_message_instructs_doc_backfill(self):
        # Cleared-but-discovery-was-required ⇒ the message must tell the agent
        # to ADD docs filling the gap found during discovery.
        msg = search_docs_mod.build_deny_message('Bash')
        self.assertIn('write_memory', msg)
        self.assertIn('search_memories_by_name', msg)

    def test_deny_message_routes_undocumented_area_to_onboard_agent(self):
        # When NO reasonable feature memories exist for the code area, the
        # FIRST step is NOT more manual grepping — it is delegating indexing
        # to a FOREGROUND agent running /swe-feature-onboard (new area) or
        # /swe-feature-update (stale docs), WAITING for it, then reading the
        # memories it created to clear the gate.
        msg = search_docs_mod.build_deny_message('Grep')
        self.assertIn('/swe-feature-onboard', msg)
        self.assertIn('/swe-feature-update', msg)
        self.assertIn('WAIT', msg)
        # foreground semantics: explicitly forbid fire-and-forget
        self.assertIn('run_in_background', msg)
        # the agent-tool delegation itself
        self.assertIn('Agent', msg)
        # satisfies swe_pre_agent_model_gate's foreground-justification check
        # instead of tripping it
        self.assertIn('[foreground-justified:', msg)
        # non-exclusive wording: the instructed onboarding agent must NOT be
        # told to follow ONLY these instructions — that trains it to reject
        # legitimate orchestrator steering delivered later via SendMessage.
        self.assertIn('legitimate amendments', msg)
        self.assertNotIn('Follow ONLY', msg)


class TestSearchDocsGateSweepBonus(unittest.TestCase):
    """A WM-verified 4d sweep (sweep sentinel present this task) tops the budget
    up ONCE by SWEEP_BONUS — so an agent that has provably done its research
    keeps source access through execution without hunting for a fresh unrelated
    memory to re-arm. The top-up is credited exactly once per task (a
    'sweep_bonus' marker in the stream), and re-reads still never refill."""

    def setUp(self):
        # Hermetic: patch the exact symbols the module imported so streams and
        # the sweep sentinel resolve into tmp — get_project_root() ignores
        # CLAUDE_PROJECT_DIR unless it contains .git/, so env override is not
        # enough (it would leak into the real repo .serena/streams).
        self.tmp = tempfile.TemporaryDirectory()
        self.session = 'sweepbon'
        self.stream = os.path.join(self.tmp.name, f'{self.session}.jsonl')
        self._sentinel = os.path.join(self.tmp.name, f'.sweep_feature_{self.session}')
        self._orig_stream = search_docs_mod.get_stream_path
        self._orig_sentinel = search_docs_mod.get_feature_sentinel_path
        search_docs_mod.get_stream_path = (
            lambda sid: os.path.join(self.tmp.name, f'{sid}.jsonl'))
        search_docs_mod.get_feature_sentinel_path = (
            lambda sid, gate: os.path.join(self.tmp.name, f'.{gate}_feature_{sid}'))

    def tearDown(self):
        search_docs_mod.get_stream_path = self._orig_stream
        search_docs_mod.get_feature_sentinel_path = self._orig_sentinel
        self.tmp.cleanup()

    def _write_events(self, events):
        with open(self.stream, 'w') as f:
            for e in events:
                f.write(json.dumps(e) + '\n')

    def _make_sweep_sentinel(self):
        with open(self._sentinel, 'w') as f:
            f.write('')

    def test_budget_constant_is_fifteen(self):
        self.assertEqual(search_docs_mod.GATED_CALL_BUDGET, 15)

    def test_sweep_bonus_constant(self):
        self.assertGreaterEqual(search_docs_mod.SWEEP_BONUS, 30)

    def test_sweep_present_survives_a_long_grind(self):
        # docread + verified sweep ⇒ base 15 + bonus 40; driving 25 gated
        # calls through the real gate (which stamps the one-time bonus on the
        # first call) leaves the agent STILL allowed deep into a long grind.
        self._make_sweep_sentinel()
        self._write_events([{'type': 'docread', 'name': 'feature/x'}])
        verdicts = [search_docs_mod.gate_and_record(self.stream) for _ in range(25)]
        self.assertTrue(all(verdicts))
        self.assertTrue(search_docs_mod.docs_budget_allows(self.stream))

    def test_sweep_bonus_present_in_budget_walk(self):
        # A stamped 'sweep_bonus' marker adds SWEEP_BONUS on top of the base:
        # base 15 + 40 = 55 survives 25 gated in a raw walk.
        self._write_events([{'type': 'docread', 'name': 'feature/x'},
                            {'type': 'sweep_bonus'}]
                           + [{'type': 'gated'}] * 25)
        self.assertTrue(search_docs_mod.docs_budget_allows(self.stream))

    def test_no_sweep_sentinel_no_bonus(self):
        # Without the sentinel, gate_and_record never stamps a bonus — only the
        # base budget applies, so 25 gated calls after one docread exhaust it.
        self._write_events([{'type': 'docread', 'name': 'feature/x'}])
        verdicts = [search_docs_mod.gate_and_record(self.stream) for _ in range(25)]
        self.assertFalse(all(verdicts))
        self.assertFalse(search_docs_mod.docs_budget_allows(self.stream))

    def test_bonus_credited_only_once_per_task(self):
        # gate_and_record appends the one-time 'sweep_bonus' marker on the
        # first allowed call under a present sentinel; a second walk must NOT
        # re-add it (budget = base + ONE bonus, then depletes).
        self._make_sweep_sentinel()
        self._write_events([{'type': 'docread', 'name': 'feature/x'}])
        cap = search_docs_mod.GATED_CALL_BUDGET + search_docs_mod.SWEEP_BONUS
        verdicts = [search_docs_mod.gate_and_record(self.stream)
                    for _ in range(cap + 1)]
        self.assertEqual(verdicts, [True] * cap + [False])
        # exactly one bonus marker was written
        with open(self.stream) as f:
            markers = [l for l in f if '"sweep_bonus"' in l]
        self.assertEqual(len(markers), 1)


class TestSearchDocsGateScoping(unittest.TestCase):
    """is_gated_call: which tool calls count as docs-first-gated code-surfing."""

    def test_wide_searches_always_gated(self):
        self.assertTrue(search_docs_mod.is_gated_call('Grep', {'pattern': 'x'}))
        self.assertTrue(search_docs_mod.is_gated_call('Glob', {'pattern': '*.php'}))
        self.assertTrue(search_docs_mod.is_gated_call(
            'mcp__plugin_swe_serena__search_for_pattern', {'substring_pattern': 'x'}))

    def test_bash_inspection_commands_gated(self):
        for cmd in ('cat package.json',
                    'head -20 .github/workflows/deploy.yml',
                    'cd /x && cat composer.json',
                    'git log --oneline -5',
                    'git diff HEAD~1',
                    'ls -la .github/workflows/',
                    'npm run build && cat dist/manifest.json',
                    # recon dressed as a pipeline — inspection after a pipe must match
                    'ls /x/*/hooks/ | head -40',
                    'ls /a 2>/dev/null; echo === ; find /b -name "*.py" | grep pre',
                    # FEEDBACK_ENFORCEMENT: newline-hidden command must match too
                    'echo setup\ncat package.json'):
            self.assertTrue(search_docs_mod.is_gated_call('Bash', {'command': cmd}), cmd)

    def test_bash_work_commands_not_gated(self):
        for cmd in ('npm run build',
                    'git commit -m "x"',
                    'mkdir -p /tmp/x',
                    'python3 scripts/test-bash-policy.py',
                    'git add -A',
                    'docker restart demo1-devcontainer-1'):
            self.assertFalse(search_docs_mod.is_gated_call('Bash', {'command': cmd}), cmd)

    def test_bash_work_with_output_filter_pipes_not_gated(self):
        # A work command whose OUTPUT is piped through a pagination/filter
        # stage is still work, not recon — the filter reads the command's own
        # output, not the codebase. Observed false positives: test runners and
        # formatters denied because of a trailing `| tail` / `| head`.
        for cmd in (
                'python3 -m pytest tests/test_sweep_gate.py -q 2>&1 | tail -15',
                'cd /x && python3 -m unittest tests.test_sweep_gate -v 2>&1 | tail -6',
                'cd /x/em-flex-pay && composer test:real 2>&1 | grep -E "FAIL|OK"',
                'vendor/bin/phpcbf --standard=phpcs.xml a.php b.php 2>&1 | head -20',
                'CLAUDE_PROJECT_DIR=$PWD python3 tools/set_state.py abc WF_EXECUTE | head -5',
                'git commit -m "x" 2>&1 | tail -3'):
            self.assertFalse(search_docs_mod.is_gated_call('Bash', {'command': cmd}), cmd)

    def test_bash_sequenced_recon_after_work_still_gated(self):
        # A `;`/`&&`-SEQUENCED inspection command is a standalone read of the
        # codebase (recon appended to work) — still gated. Only PIPES inherit
        # the work classification of their first stage.
        for cmd in ('npm run build && cat dist/manifest.json',
                    'echo "===" && grep -rn "Identity" tests/',
                    'composer test; git diff HEAD~1'):
            self.assertTrue(search_docs_mod.is_gated_call('Bash', {'command': cmd}), cmd)

    def test_bash_inspect_of_transient_output_path_not_gated(self):
        # Grepping/cat-ing a transient output path (/tmp, /var/tmp, $TMPDIR,
        # /dev/…) is result-inspection, not codebase recon — the file is command
        # output, never source. Observed false positive: a test run writing
        # /tmp/test-pp.log then a newline-separated `grep … /tmp/test-pp.log`.
        for cmd in (
                'grep -h "^OK\\|Failures" /tmp/test-pp.log',
                'cd /x/em-flex-pay && composer test > /tmp/test-pp.log 2>&1; echo "exit $?"\n'
                'grep -h "^OK\\|Failures\\|Errors\\|FAILURES" /tmp/test-pp.log',
                'cat /tmp/build.out',
                'tail -20 /var/tmp/run.log',
                'grep ERROR "$TMPDIR/out.txt"',
                'head /dev/stdin'):
            self.assertFalse(search_docs_mod.is_gated_call('Bash', {'command': cmd}), cmd)

    def test_bash_recon_of_project_paths_still_gated(self):
        # Absolute paths that are NOT transient output are still codebase recon.
        for cmd in ('find /b -name "*.py" | grep pre',
                    'grep -rn "Identity" /Users/webdev/x/src',
                    'cat /x/composer.json'):
            self.assertTrue(search_docs_mod.is_gated_call('Bash', {'command': cmd}), cmd)

    def test_docker_exec_container_recon_gated(self):
        # "Digging in Docker": docker exec / compose exec whose payload
        # reverse-engineers the running stack (grep/sed/cat/env recon or a
        # `php -r` inline probe of wp-config / object-cache / redis / env).
        # The group's first token is `docker`, so the plain inspection
        # classifier never sees it — this vector must gate independently.
        for cmd in (
                "docker exec c sh -c \"grep -rniE 'redis|object.?cache' "
                "/workspace/wp-config.php\"",
                "docker exec c sh -c 'sed -n \"1,40p\" /workspace/wp-config.php'",
                "docker exec c sh -c 'echo x; cat /workspace/wp-config-ocp.php'",
                "docker exec c php -d display_errors=1 -r "
                "'var_dump(getenv(\"PANTHEON_ENVIRONMENT\"));'",
                "docker exec c php -d display_errors=stderr -d "
                "error_reporting=E_ALL -r 'echo 1;'",
                "docker compose exec php sh -c 'grep WP_REDIS wp-config.php'",
                "docker exec c env"):
            self.assertTrue(
                search_docs_mod.is_gated_call('Bash', {'command': cmd}), cmd)

    def test_docker_lifecycle_and_wp_and_work_not_gated(self):
        # Container mutation/build/lifecycle and raw `docker exec … wp …`
        # (the WP-CLI-MCP / block-wordpress-exec path) and real work commands
        # run in the container are NOT docs recon.
        for cmd in (
                'docker compose -f .devcontainer/docker-compose.yml up -d',
                'docker exec c wp plugin list --allow-root --path=/workspace',
                'docker restart demo1-devcontainer-1',
                'docker exec c php artisan migrate',
                'docker exec c composer install',
                'docker exec c php index.php'):
            self.assertFalse(
                search_docs_mod.is_gated_call('Bash', {'command': cmd}), cmd)

    def test_read_never_gated(self):
        # Read opens a specific known file — not untargeted surfing. NEVER gated,
        # regardless of path (project source, config, or CLAUDE.md).
        for path in ('/Users/webdev/LocalSites/x/src/index.ts',
                     '/Users/webdev/LocalSites/x/CLAUDE.md',
                     '/Users/webdev/LocalSites/x/.serena/memories/WM_ab.md',
                     '/tmp/foo.log'):
            self.assertFalse(search_docs_mod.is_gated_call('Read', {'file_path': path}), path)

    def test_other_tools_not_gated(self):
        self.assertFalse(search_docs_mod.is_gated_call('Edit', {'file_path': '/x/y.php'}))
        self.assertFalse(search_docs_mod.is_gated_call('Bash', {}))
        self.assertFalse(search_docs_mod.is_gated_call('Read', {}))


class TestDocsGateSubagentExemption(unittest.TestCase):
    """Spawned agents must NEVER be doc-gated. Their transcripts sit UNDER
    the parent session dir (<session-uuid>/subagents/agent-<id>.jsonl), so
    extract_session_id resolves to the PARENT session, whose init sentinel
    exists — the no-sentinel exemption never triggers. The gate must detect
    the subagent transcript shape itself."""

    SUBAGENT_PATH = ("/Users/x/.claude/projects/-Users-x-proj/"
                     "94aee7ae-ebde-442b-a66c-2cac8ccdd262/subagents/"
                     "agent-ab0cfb5f7dcdeb663.jsonl")
    MAIN_PATH = ("/Users/x/.claude/projects/-Users-x-proj/"
                 "94aee7ae-ebde-442b-a66c-2cac8ccdd262.jsonl")

    def test_gate_exempts_subagent_transcript(self):
        self.assertTrue(search_docs_mod.is_subagent_transcript(self.SUBAGENT_PATH))

    def test_gate_does_not_exempt_main_transcript(self):
        self.assertFalse(search_docs_mod.is_subagent_transcript(self.MAIN_PATH))

    def test_subagent_path_resolves_to_parent_session(self):
        # the trap this exemption fixes: parent session id + existing
        # sentinel would otherwise gate the subagent on the parent budget
        self.assertEqual(
            search_docs_mod.extract_session_id(self.SUBAGENT_PATH), "94aee7ae")

    def _run_main(self, transcript_path, **extra):
        """Drive main() end-to-end with a fully-gated parent session
        (sentinel exists, budget spent). Returns the emitted hook JSON.
        `extra` merges additional fields into the hook input (e.g. agent_id)."""
        import contextlib
        import io
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        sentinel = os.path.join(tmp.name, '.init_94aee7ae')
        stream = os.path.join(tmp.name, '94aee7ae.jsonl')
        open(sentinel, 'w').close()
        with open(stream, 'w') as f:
            f.write(json.dumps({'type': 'prompt'}) + '\n')  # no docread: deny
        payload = {'tool_name': 'Grep', 'tool_input': {'pattern': 'x'},
                   'transcript_path': transcript_path}
        payload.update(extra)
        orig = (search_docs_mod.read_stdin_safe,
                search_docs_mod.get_sentinel_path,
                search_docs_mod.get_stream_path)
        search_docs_mod.read_stdin_safe = lambda **kw: payload
        search_docs_mod.get_sentinel_path = lambda sid: sentinel
        search_docs_mod.get_stream_path = lambda sid: stream
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                with self.assertRaises(SystemExit):
                    search_docs_mod.main()
        finally:
            (search_docs_mod.read_stdin_safe,
             search_docs_mod.get_sentinel_path,
             search_docs_mod.get_stream_path) = orig
        return json.loads(buf.getvalue())

    def test_main_allows_subagent_even_when_parent_fully_gated(self):
        result = self._run_main(self.SUBAGENT_PATH)
        self.assertEqual(result, {})

    def test_main_denies_main_session_when_budget_spent(self):
        # positive control: same gated setup DOES deny the main session
        result = self._run_main(self.MAIN_PATH)
        self.assertEqual(
            result['hookSpecificOutput']['permissionDecision'], 'deny')

    # --- agent_id/agent_type runtime signal (primary exemption) ---------------
    # The REAL-WORLD failure: Claude Code hands the PreToolUse hook the PARENT
    # transcript path for a spawned-agent tool call (session_id is the parent
    # id), so the transcript-shape check misses it. The robust discriminator is
    # the dedicated agent_id/agent_type field, present ONLY for subagents.

    def test_is_spawned_agent_true_on_agent_id(self):
        self.assertTrue(search_docs_mod.is_spawned_agent(
            {'agent_id': 'aac4dea2590360b94'}))

    def test_is_spawned_agent_true_on_agent_type(self):
        self.assertTrue(search_docs_mod.is_spawned_agent(
            {'agent_type': 'Explore'}))

    def test_is_spawned_agent_true_on_camelcase(self):
        # tolerate the camelCase variant seen in transcript records
        self.assertTrue(search_docs_mod.is_spawned_agent(
            {'agentId': 'aac4dea2590360b94'}))

    def test_is_spawned_agent_false_on_main_session(self):
        # main-session payload carries NO agent_id/agent_type
        self.assertFalse(search_docs_mod.is_spawned_agent(
            {'tool_name': 'Grep', 'transcript_path': self.MAIN_PATH}))

    def test_is_spawned_agent_false_on_empty_agent_fields(self):
        # empty-string agent fields must NOT exempt (defensive: never a subagent)
        self.assertFalse(search_docs_mod.is_spawned_agent(
            {'agent_id': '', 'agent_type': ''}))

    def test_is_spawned_agent_false_on_non_dict(self):
        self.assertFalse(search_docs_mod.is_spawned_agent(None))

    def test_main_allows_subagent_by_agent_id_with_parent_transcript(self):
        # THE regression: parent transcript path (misses is_subagent_transcript)
        # BUT agent_id present ⇒ still exempt even though the parent is fully
        # gated. Without the agent_id check this would deny.
        result = self._run_main(self.MAIN_PATH, agent_id='aac4dea2590360b94')
        self.assertEqual(result, {})

    def test_main_allows_subagent_by_agent_type_with_parent_transcript(self):
        result = self._run_main(self.MAIN_PATH, agent_type='Explore')
        self.assertEqual(result, {})

    def test_main_denies_main_session_with_empty_agent_fields(self):
        # negative control: empty agent fields on the MAIN session still deny —
        # the exemption keys on a NON-EMPTY agent id/type only.
        result = self._run_main(self.MAIN_PATH, agent_id='', agent_type='')
        self.assertEqual(
            result['hookSpecificOutput']['permissionDecision'], 'deny')


class TestDocsGateClearingWiring(unittest.TestCase):
    """The gate message sanctions search_memories_by_name/_by_front_matter as
    step 1 — those calls MUST therefore append a docread (i.e. be matched by
    the swe_post_read_state.py PostToolUse matcher). This was the original
    bug: the sanctioned clearing step did not clear the gate."""

    def _read_state_matchers(self):
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'hooks', 'hooks.json')
        with open(path) as f:
            config = json.load(f)
        for entry in config['hooks']['PostToolUse']:
            cmds = [h['command'] for h in entry.get('hooks', [])]
            if any('swe_post_read_state' in c for c in cmds):
                return entry['matcher']
        self.fail('swe_post_read_state.py not registered in PostToolUse')

    def test_memory_search_tools_feed_docread(self):
        matcher = self._read_state_matchers()
        for name in ('mcp__plugin_swe_serena__search_memories_by_name',
                     'mcp__serena__search_memories_by_name',
                     'mcp__plugin_swe_serena__search_memories_by_front_matter',
                     'mcp__serena__search_memories_by_front_matter'):
            self.assertIn(name, matcher.split('|'), name)


consent_mod = import_hook("pre/swe_pre_question_consent_gate")


class TestQuestionConsentGate(unittest.TestCase):
    """wm_has_blanket_consent: WM flag detection."""

    SESSION = 'cafe1234'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.memories = os.path.join(self.root, '.serena', 'memories')
        os.makedirs(self.memories, exist_ok=True)
        # find_working_memory_for_session resolves via get_project_root(),
        # not the cwd arg — point it at the temp root (same pattern as
        # test_core_session).
        from swe_hooks.core import session as core_session
        self._orig_root = core_session.get_project_root
        core_session.get_project_root = lambda: self.root

    def tearDown(self):
        from swe_hooks.core import session as core_session
        core_session.get_project_root = self._orig_root
        self.tmp.cleanup()
        reset_caches()

    def _write_wm(self, body):
        with open(os.path.join(self.memories, f'WM_{self.SESSION}.md'), 'w') as f:
            f.write(body)

    def test_blanket_consent_flag_detected(self):
        self._write_wm('## Context\n- blanket_consent: true (operator said go)\n')
        self.assertTrue(consent_mod.wm_has_blanket_consent(self.root, self.SESSION))

    def test_auto_approve_flag_detected(self):
        self._write_wm('## Task Context\n- auto_approve: true\n')
        self.assertTrue(consent_mod.wm_has_blanket_consent(self.root, self.SESSION))

    def test_no_flag_returns_false(self):
        self._write_wm('## Context\n- normal session\n')
        self.assertFalse(consent_mod.wm_has_blanket_consent(self.root, self.SESSION))

    def test_false_flag_returns_false(self):
        self._write_wm('## Context\n- auto_approve: false\n')
        self.assertFalse(consent_mod.wm_has_blanket_consent(self.root, self.SESSION))

    def test_missing_wm_returns_false(self):
        self.assertFalse(consent_mod.wm_has_blanket_consent(self.root, self.SESSION))


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# swe_pre_memory_index_gate
# ---------------------------------------------------------------------------
memidx_mod = import_hook("pre/swe_pre_memory_index_gate")


class TestMemoryIndexGateTargets(unittest.TestCase):
    def test_memory_name_memory_is_target(self):
        self.assertTrue(memidx_mod.targets_memory_index({'memory_name': 'MEMORY'}))

    def test_memory_name_memory_md_is_target(self):
        self.assertTrue(memidx_mod.targets_memory_index({'memory_name': 'MEMORY.md'}))

    def test_file_path_memory_md_is_target(self):
        self.assertTrue(memidx_mod.targets_memory_index(
            {'file_path': '/proj/.serena/memory/MEMORY.md'}))

    def test_auto_memory_symlink_path_is_target(self):
        self.assertTrue(memidx_mod.targets_memory_index(
            {'file_path': '/Users/x/.claude/projects/-proj/memory/MEMORY.md'}))

    def test_other_memory_is_not_target(self):
        self.assertFalse(memidx_mod.targets_memory_index(
            {'memory_name': 'feature/FEATURE_SWE'}))

    def test_other_file_is_not_target(self):
        self.assertFalse(memidx_mod.targets_memory_index(
            {'file_path': '/proj/README.md'}))

    def test_empty_input_is_not_target(self):
        self.assertFalse(memidx_mod.targets_memory_index({}))


class TestMemoryIndexGateCategoryLinks(unittest.TestCase):
    def test_spec_dir_link_detected_in_edit_repl(self):
        self.assertEqual(
            memidx_mod.written_category_links(
                {'repl': '- [Manager fleet-ops spec](spec/SPEC_MANAGER_FLEET_OPS.md) — build spec'}),
            ['spec'])

    def test_report_dir_link_detected_in_write_content(self):
        self.assertEqual(
            memidx_mod.written_category_links(
                {'content': '## Idx\n- [R](report/REPORT_AUDIT.md) — x'}),
            ['report'])

    def test_full_path_category_link_detected(self):
        self.assertEqual(
            memidx_mod.written_category_links(
                {'new_string': '- [S](.serena/memory/research/RESEARCH_X.md)'}),
            ['research'])

    def test_bare_basename_spec_link_detected(self):
        self.assertEqual(
            memidx_mod.written_category_links({'repl': '- [S](SPEC_FOO.md)'}),
            ['spec'])

    def test_multiple_categories_detected_sorted(self):
        blob = '- [A](spec/SPEC_A.md)\n- [B](project/PROJECT_B.md)'
        self.assertEqual(
            memidx_mod.written_category_links({'content': blob}),
            ['project', 'spec'])

    def test_feature_and_ref_links_pass(self):
        blob = ('- [CRM](feature/FEATURE_CRM.md) — core\n'
                '- [Deploy](ref/REF_DEPLOY.md) — rules')
        self.assertEqual(memidx_mod.written_category_links({'content': blob}), [])

    def test_prose_mention_of_spec_word_passes(self):
        self.assertEqual(
            memidx_mod.written_category_links(
                {'content': '- [X](feature/FEATURE_X.md) — per spec discussions'}),
            [])

    def test_specific_prefix_in_title_but_safe_target_passes(self):
        self.assertEqual(
            memidx_mod.written_category_links(
                {'content': '- [SPEC review notes](ref/REF_SPEC_REVIEWS.md) — how we review'}),
            [])

    def test_empty_input_passes(self):
        self.assertEqual(memidx_mod.written_category_links({}), [])


class TestMemoryIndexGateDedupe(unittest.TestCase):
    """B4 — new-memory dedupe: a write_memory CREATING a memory whose topic
    an existing memory already covers is denied toward edit_memory. Edits/
    overwrites of existing memories, WM_ files, and the literal
    [new-memory-justified: <reason>] tag always pass."""

    WRITE_TOOL = 'mcp__plugin_swe_serena__write_memory'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name
        ref_dir = os.path.join(self.cwd, '.serena', 'memories', 'ref')
        os.makedirs(ref_dir, exist_ok=True)
        with open(os.path.join(ref_dir, 'REF_MEMORY_STYLE.md'), 'w') as f:
            f.write('---\nname: REF_MEMORY_STYLE\n'
                    'description: terse-imperative style standard\n---\n'
                    'Style enforcement via swe_post_memory_style hook.\n')

    def tearDown(self):
        self.tmp.cleanup()

    def _deny(self, name, content=''):
        return memidx_mod.new_memory_dedupe_denial(
            self.WRITE_TOOL, {'memory_name': name, 'content': content},
            self.cwd)

    # --- tokenization ------------------------------------------------------
    def test_topic_tokens_strip_dir_and_type_prefix(self):
        self.assertEqual(memidx_mod.memory_topic_tokens('ref/REF_MEMORY_STYLE'),
                         {'memory', 'style'})

    def test_topic_tokens_drop_short_tokens(self):
        # wp (2) and api (3) are below the distinctive-token threshold.
        self.assertEqual(memidx_mod.memory_topic_tokens('dom/DOM_WP_API'), set())

    # --- deny paths --------------------------------------------------------
    def test_new_on_topic_name_denied_via_basename(self):
        msg = self._deny('ref/REF_STYLE_MEMORY')
        self.assertIsNotNone(msg)
        self.assertIn('ref/REF_MEMORY_STYLE', msg)
        self.assertIn('edit_memory', msg)
        self.assertIn('[new-memory-justified:', msg)

    def test_new_on_topic_name_denied_via_body(self):
        # 'enforcement' is not in the existing basename but IS in its body.
        msg = self._deny('dom/DOM_STYLE_ENFORCEMENT')
        self.assertIsNotNone(msg)
        self.assertIn('ref/REF_MEMORY_STYLE', msg)

    # --- allow paths -------------------------------------------------------
    def test_unrelated_new_memory_allowed(self):
        self.assertIsNone(self._deny('feature/FEATURE_PAYMENTS_GATEWAY'))

    def test_override_tag_allows(self):
        self.assertIsNone(self._deny(
            'ref/REF_STYLE_MEMORY',
            'body [new-memory-justified: splitting the style doc] body'))

    def test_existing_memory_overwrite_allowed(self):
        self.assertIsNone(self._deny('ref/REF_MEMORY_STYLE'))

    def test_existing_memory_by_bare_basename_allowed(self):
        self.assertIsNone(self._deny('REF_MEMORY_STYLE'))

    def test_edit_memory_tool_not_gated(self):
        self.assertIsNone(memidx_mod.new_memory_dedupe_denial(
            'mcp__plugin_swe_serena__edit_memory',
            {'memory_name': 'ref/REF_STYLE_MEMORY', 'repl': 'x'}, self.cwd))

    def test_wm_session_file_exempt(self):
        self.assertIsNone(self._deny('WM_deadbeef'))

    def test_name_without_distinctive_tokens_allowed(self):
        self.assertIsNone(self._deny('dom/DOM_WP_API'))

    def test_memory_md_and_wm_files_never_count_as_hits(self):
        mem = os.path.join(self.cwd, '.serena', 'memories')
        with open(os.path.join(mem, 'MEMORY.md'), 'w') as f:
            f.write('- [x](ref/REF_X.md) — alpha beta gateway payments\n')
        with open(os.path.join(mem, 'WM_cafe1234.md'), 'w') as f:
            f.write('alpha beta gateway payments\n')
        self.assertIsNone(self._deny('feature/FEATURE_PAYMENTS_GATEWAY'))

    # --- main() end-to-end -------------------------------------------------
    def _run_main(self, tool_input):
        import contextlib
        import io
        payload = {'tool_name': self.WRITE_TOOL, 'tool_input': tool_input,
                   'cwd': self.cwd}
        orig = memidx_mod.read_stdin_safe
        memidx_mod.read_stdin_safe = lambda **kw: payload
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                with self.assertRaises(SystemExit):
                    memidx_mod.main()
        finally:
            memidx_mod.read_stdin_safe = orig
        return json.loads(buf.getvalue())

    # Rule-bearing fixtures carry obligations: the H obligations check runs
    # BEFORE the dedupe check in main(), so these tests must pass it to reach
    # (or cleanly skip) the dedupe path they exercise.
    OBLIGATED = ('---\nname: x\ndescription: y\nmetadata:\n  type: reference\n'
                 'obligations:\n  - Test obligation line.\n---\nbody')

    def test_main_denies_duplicate_creation(self):
        result = self._run_main(
            {'memory_name': 'ref/REF_STYLE_MEMORY', 'content': self.OBLIGATED})
        out = result['hookSpecificOutput']
        self.assertEqual(out['permissionDecision'], 'deny')
        self.assertIn('on-topic memory already exists',
                      out['permissionDecisionReason'])

    def test_main_allows_unrelated_creation(self):
        result = self._run_main(
            {'memory_name': 'feature/FEATURE_PAYMENTS_GATEWAY',
             'content': self.OBLIGATED})
        self.assertEqual(result, {})

    def test_main_denies_rule_bearing_creation_without_obligations(self):
        result = self._run_main(
            {'memory_name': 'feature/FEATURE_PAYMENTS_GATEWAY',
             'content': 'new area'})
        out = result['hookSpecificOutput']
        self.assertEqual(out['permissionDecision'], 'deny')
        self.assertIn('obligations', out['permissionDecisionReason'])


# ---------------------------------------------------------------------------
# swe_pre_memory_index_gate — FOURTH DUTY: site-data denial
# ---------------------------------------------------------------------------
class TestMemoryIndexGateSiteDataDetectors(unittest.TestCase):
    """find_site_data_hits: each category denied, each placeholder allowed."""

    # --- IPv4 ----------------------------------------------------------
    def test_private_10_net_denied(self):
        hits = memidx_mod.find_site_data_hits('redis at 10.20.30.40 port 6379')
        self.assertEqual([c for c, _v in hits], ['IPv4 address'])

    def test_private_172_16_net_denied(self):
        hits = memidx_mod.find_site_data_hits('db host 172.16.5.1')
        self.assertEqual([c for c, _v in hits], ['IPv4 address'])

    def test_private_192_168_net_denied(self):
        hits = memidx_mod.find_site_data_hits('router at 192.168.1.1')
        self.assertEqual([c for c, _v in hits], ['IPv4 address'])

    def test_loopback_allowed(self):
        self.assertEqual(memidx_mod.find_site_data_hits('bind 127.0.0.1:8080'), [])

    def test_unspecified_allowed(self):
        self.assertEqual(memidx_mod.find_site_data_hits('listen 0.0.0.0'), [])

    def test_rfc5737_testnet1_allowed(self):
        self.assertEqual(memidx_mod.find_site_data_hits('192.0.2.10'), [])

    def test_rfc5737_testnet2_allowed(self):
        self.assertEqual(memidx_mod.find_site_data_hits('198.51.100.5'), [])

    def test_rfc5737_testnet3_allowed(self):
        self.assertEqual(memidx_mod.find_site_data_hits('203.0.113.7'), [])

    def test_version_string_1_3_40_not_ipv4(self):
        self.assertEqual(memidx_mod.find_site_data_hits('bump to v1.3.40'), [])

    def test_version_string_2_1_0_not_ipv4(self):
        self.assertEqual(memidx_mod.find_site_data_hits('release 2.1.0 shipped'), [])

    def test_five_octet_string_not_ipv4(self):
        self.assertEqual(memidx_mod.find_site_data_hits('id 1.2.3.4.5 logged'), [])

    # --- email -----------------------------------------------------------
    def test_real_email_denied(self):
        hits = memidx_mod.find_site_data_hits('contact ops@realcompany.io')
        self.assertIn('email address', [c for c, _v in hits])

    def test_example_test_email_allowed(self):
        self.assertEqual(memidx_mod.find_site_data_hits('user@example.test'), [])

    def test_example_com_email_allowed(self):
        self.assertEqual(memidx_mod.find_site_data_hits('a@example.com'), [])

    def test_anthropic_noreply_allowed(self):
        self.assertEqual(
            memidx_mod.find_site_data_hits('Co-Authored-By: Claude <noreply@anthropic.com>'),
            [])

    # --- credentialed URL --------------------------------------------------
    def test_credentialed_url_denied(self):
        hits = memidx_mod.find_site_data_hits('https://user:pass@host.com/path')
        self.assertIn('credentialed URL', [c for c, _v in hits])

    def test_angle_bracket_placeholder_url_allowed(self):
        self.assertEqual(
            memidx_mod.find_site_data_hits('https://<token>@github.com/org/repo'), [])

    def test_ftp_scheme_credential_denied(self):
        hits = memidx_mod.find_site_data_hits('ftp://admin:hunter2@files.corp.io/x')
        self.assertIn('credentialed URL', [c for c, _v in hits])

    # --- SSH connect strings ------------------------------------------------
    def test_ssh_prefixed_real_host_denied(self):
        hits = memidx_mod.find_site_data_hits('ssh admin@prodhost.internal.example.io')
        self.assertIn('SSH connect string', [c for c, _v in hits])

    def test_colon_suffixed_real_host_denied(self):
        hits = memidx_mod.find_site_data_hits('rsync deploy@build.corp.io:/var/www')
        self.assertIn('SSH connect string', [c for c, _v in hits])

    def test_git_github_placeholder_allowed(self):
        self.assertEqual(
            memidx_mod.find_site_data_hits('clone git@github.com:<org>/<repo>'), [])

    def test_git_github_real_org_path_denied(self):
        hits = memidx_mod.find_site_data_hits('clone git@github.com:realorg/realrepo')
        self.assertIn('SSH connect string', [c for c, _v in hits])

    # --- private key blocks --------------------------------------------------
    def test_rsa_private_key_block_denied(self):
        hits = memidx_mod.find_site_data_hits('-----BEGIN RSA PRIVATE KEY-----\nMII...')
        self.assertIn('private key block', [c for c, _v in hits])

    def test_openssh_private_key_block_denied(self):
        hits = memidx_mod.find_site_data_hits('-----BEGIN OPENSSH PRIVATE KEY-----\nb3Bl...')
        self.assertIn('private key block', [c for c, _v in hits])

    # --- token prefixes ------------------------------------------------------
    def test_github_pat_classic_denied(self):
        hits = memidx_mod.find_site_data_hits('token ghp_' + 'a' * 24)
        self.assertIn('GitHub PAT (classic)', [c for c, _v in hits])

    def test_github_pat_fine_grained_denied(self):
        hits = memidx_mod.find_site_data_hits('token github_pat_' + 'a' * 24)
        self.assertIn('GitHub PAT (fine-grained)', [c for c, _v in hits])

    def test_openai_style_key_denied(self):
        hits = memidx_mod.find_site_data_hits('key sk-' + 'a' * 25)
        self.assertIn('OpenAI-style secret key', [c for c, _v in hits])

    def test_aws_access_key_denied(self):
        hits = memidx_mod.find_site_data_hits('key AKIA' + 'A' * 16)
        self.assertIn('AWS access key ID', [c for c, _v in hits])

    def test_slack_token_denied(self):
        hits = memidx_mod.find_site_data_hits('token xoxb-1234567890123')
        self.assertIn('Slack token', [c for c, _v in hits])

    # --- truncation ------------------------------------------------------
    def test_truncate_caps_at_40_chars(self):
        long_val = 'a' * 60
        self.assertEqual(len(memidx_mod._truncate(long_val)), 41)  # 40 + ellipsis
        self.assertTrue(memidx_mod._truncate(long_val).startswith('a' * 40))


class TestMemoryIndexGateSiteDataVerdict(unittest.TestCase):
    """site_data_denial: tool matching, field scanning, deny message shape."""

    def test_write_memory_content_scanned(self):
        msg = memidx_mod.site_data_denial(
            'mcp__plugin_swe_serena__write_memory',
            {'memory_name': 'dom/DOM_X', 'content': 'redis at 10.20.30.40'})
        self.assertIsNotNone(msg)
        self.assertTrue(msg.startswith('🛑 BLOCKED'))
        self.assertIn('IPv4 address', msg)
        self.assertIn('10.20.30.40', msg)
        self.assertIn('mem:ref/REF_NO_SITE_DATA', msg)

    def test_edit_memory_repl_scanned(self):
        msg = memidx_mod.site_data_denial(
            'mcp__plugin_swe_serena__edit_memory',
            {'memory_name': 'dom/DOM_X', 'repl': 'db host 172.16.0.5'})
        self.assertIsNotNone(msg)
        self.assertIn('IPv4 address', msg)
        self.assertIn('172.16.0.5', msg)

    def test_non_memory_write_path_not_scanned(self):
        self.assertIsNone(memidx_mod.site_data_denial(
            'Write', {'file_path': '/proj/src/config.py', 'content': '10.20.30.40'}))

    def test_memory_md_under_serena_write_scanned(self):
        msg = memidx_mod.site_data_denial(
            'Write',
            {'file_path': '/proj/.serena/memory/dom/DOM_X.md',
             'content': 'server at 10.20.30.40'})
        self.assertIsNotNone(msg)
        self.assertIn('IPv4 address', msg)

    def test_memory_md_under_serena_edit_new_string_scanned(self):
        msg = memidx_mod.site_data_denial(
            'Edit',
            {'file_path': '/proj/.serena/memory/dom/DOM_X.md',
             'new_string': 'server at 10.20.30.40'})
        self.assertIsNotNone(msg)
        self.assertIn('IPv4 address', msg)

    def test_no_hits_allows(self):
        self.assertIsNone(memidx_mod.site_data_denial(
            'mcp__plugin_swe_serena__write_memory',
            {'memory_name': 'dom/DOM_X', 'content': 'redis caching strategy'}))

    def test_placeholders_together_allow(self):
        content = ('host.example, 192.0.2.10, user@example.test, <token>, '
                   'v1.3.40, v2.1.0, 127.0.0.1')
        self.assertIsNone(memidx_mod.site_data_denial(
            'mcp__plugin_swe_serena__write_memory',
            {'memory_name': 'dom/DOM_X', 'content': content}))

    # --- positive control: realistic memory body catches a real private IP ---
    def test_positive_control_realistic_memory_body_caught(self):
        body = (
            '---\nname: DOM_DEPLOY_TARGETS\n'
            'description: deploy target inventory\n'
            'metadata:\n  type: domain\nobligations:\n  - x\n---\n'
            '# Deploy Targets\n\n'
            'Staging DB runs on 10.4.12.19, reachable via '
            'ssh deploy@staging-db.internal.corp:22. '
            'Admin contact: ops@realcompany.io.\n'
        )
        msg = memidx_mod.site_data_denial(
            'mcp__plugin_swe_serena__write_memory',
            {'memory_name': 'dom/DOM_DEPLOY_TARGETS', 'content': body})
        self.assertIsNotNone(msg)
        self.assertIn('10.4.12.19', msg)

    # --- main() end-to-end: site-data denial fires ahead of every other check
    def _run_main(self, tool_name, tool_input):
        import contextlib
        import io
        payload = {'tool_name': tool_name, 'tool_input': tool_input, 'cwd': '/tmp'}
        orig = memidx_mod.read_stdin_safe
        memidx_mod.read_stdin_safe = lambda **kw: payload
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                with self.assertRaises(SystemExit):
                    memidx_mod.main()
        finally:
            memidx_mod.read_stdin_safe = orig
        return json.loads(buf.getvalue())

    def test_main_denies_site_data_in_new_memory_write(self):
        result = self._run_main(
            'mcp__plugin_swe_serena__write_memory',
            {'memory_name': 'dom/DOM_NEW_AREA', 'content': 'host at 10.1.1.1'})
        out = result['hookSpecificOutput']
        self.assertEqual(out['permissionDecision'], 'deny')
        self.assertIn('site-specific infrastructure data',
                      out['permissionDecisionReason'])

    def test_main_allows_clean_content(self):
        result = self._run_main(
            'mcp__plugin_swe_serena__write_memory',
            {'memory_name': 'dom/DOM_NEW_AREA',
             'content': ('---\nname: x\ndescription: y\nmetadata:\n  type: domain\n'
                         'obligations:\n  - x\n---\nbody with no site data')})
        self.assertEqual(result, {})


class TestDocsGateMemoryGrepLegitimization(unittest.TestCase):
    """B2 — a gated Grep/Glob/Bash-grep INTO a memory tree is a docs consult:
    never denied, spends no budget, credited as an always-fresh 'docread'
    (name='memory-grep') that refills the budget like read_memory."""

    MAIN_PATH = ("/Users/x/.claude/projects/-Users-x-proj/"
                 "94aee7ae-ebde-442b-a66c-2cac8ccdd262.jsonl")

    # --- detection ---------------------------------------------------------
    def test_memory_tree_targets_detected(self):
        for tool, tool_input in (
                ('Grep', {'path': '/proj/.serena/memories', 'pattern': 'redis'}),
                ('Grep', {'path': '.serena/memory/dom', 'pattern': 'cache'}),
                ('Glob', {'pattern': '.serena/memory/**/*.md'}),
                ('Glob', {'pattern': 'memories/**/*.md'}),
                ('mcp__plugin_swe_serena__search_for_pattern',
                 {'relative_path': '.serena/memories/', 'substring_pattern': 'x'}),
                ('Bash', {'command': 'grep -rn "redis" .serena/memories/'}),
                ('Bash', {'command':
                          'grep -n foo /x/plugin/memories/wf/WF_INIT.md'}),
        ):
            self.assertTrue(
                search_docs_mod.is_memory_tree_consult(tool, tool_input),
                (tool, tool_input))

    def test_non_memory_targets_not_detected(self):
        for tool, tool_input in (
                ('Grep', {'path': '/proj/src', 'pattern': 'redis'}),
                ('Grep', {'pattern': 'in-memory cache'}),
                ('Bash', {'command': 'cat package.json'}),
                ('Bash', {'command': 'grep -rn memory src/'}),
                ('Bash', {}),
        ):
            self.assertFalse(
                search_docs_mod.is_memory_tree_consult(tool, tool_input),
                (tool, tool_input))

    # --- budget semantics --------------------------------------------------
    def test_memory_grep_is_always_fresh(self):
        self.assertIn('memory-grep', search_docs_mod.ALWAYS_FRESH_NAMES)

    def test_repeated_memory_grep_docreads_keep_refilling(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        stream = os.path.join(tmp.name, 'sess.jsonl')
        events = ([{'type': 'docread', 'name': 'memory-grep'}]
                  + [{'type': 'gated'}] * search_docs_mod.GATED_CALL_BUDGET
                  + [{'type': 'docread', 'name': 'memory-grep'}])
        with open(stream, 'w') as f:
            for e in events:
                f.write(json.dumps(e) + '\n')
        self.assertTrue(search_docs_mod.docs_budget_allows(stream))

    # --- main() end-to-end -------------------------------------------------
    def _run_main(self, tool_name, tool_input, events):
        import contextlib
        import io
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        sentinel = os.path.join(tmp.name, '.init_94aee7ae')
        stream = os.path.join(tmp.name, '94aee7ae.jsonl')
        open(sentinel, 'w').close()
        with open(stream, 'w') as f:
            for e in events:
                f.write(json.dumps(e) + '\n')
        payload = {'tool_name': tool_name, 'tool_input': tool_input,
                   'transcript_path': self.MAIN_PATH}
        orig = (search_docs_mod.read_stdin_safe,
                search_docs_mod.get_sentinel_path,
                search_docs_mod.get_stream_path)
        search_docs_mod.read_stdin_safe = lambda **kw: payload
        search_docs_mod.get_sentinel_path = lambda sid: sentinel
        search_docs_mod.get_stream_path = lambda sid: stream
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                with self.assertRaises(SystemExit):
                    search_docs_mod.main()
        finally:
            (search_docs_mod.read_stdin_safe,
             search_docs_mod.get_sentinel_path,
             search_docs_mod.get_stream_path) = orig
        return json.loads(buf.getvalue()), stream

    def test_main_allows_memory_grep_with_budget_spent_and_refills(self):
        # No docread in the stream: a plain gated call would deny — the
        # memory-tree grep is allowed anyway AND credits a docread that
        # refills the budget for subsequent source reads.
        result, stream = self._run_main(
            'Grep', {'path': '/proj/.serena/memories', 'pattern': 'redis'},
            events=[{'type': 'prompt'}])
        self.assertEqual(result, {})
        with open(stream) as f:
            lines = f.read()
        self.assertIn('"memory-grep"', lines)
        self.assertTrue(search_docs_mod.docs_budget_allows(stream))

    def test_main_still_denies_plain_grep_when_budget_spent(self):
        # Positive control: without the memory-tree target the same setup
        # denies.
        result, _stream = self._run_main(
            'Grep', {'pattern': 'redis'}, events=[{'type': 'prompt'}])
        self.assertEqual(
            result['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_memory_grep_spends_no_budget(self):
        # With budget available, a memory-tree Bash grep must not append a
        # 'gated' (budget-spending) event.
        result, stream = self._run_main(
            'Bash', {'command': 'grep -rn "redis" .serena/memories/'},
            events=[{'type': 'docread', 'name': 'feature/x'}])
        self.assertEqual(result, {})
        with open(stream) as f:
            lines = f.read()
        self.assertNotIn('"gated"', lines)
        self.assertIn('"memory-grep"', lines)
