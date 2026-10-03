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
    no WM file. Denies once the weighted count_task_work_since_delegation
    reaches DRIFT_HARD_THRESHOLD UNLESS a 'single-agent: <reason>' line was
    added to WM AFTER the first hard block (drift_hard_block snapshot) of the
    current run; a delegation reset re-arms the block.
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

    def _stream_events(self):
        path = os.path.join(self.streams_dir, f'{self.session_id}.jsonl')
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]

    def test_preemptive_single_agent_note_does_not_disarm(self):
        # Note written BEFORE the hard block fired: snapshotted, never counts.
        self._write_stream(
            [{'type': 'task_work'}] * edit_mod.DRIFT_HARD_THRESHOLD)
        self._write_wm(
            '## Context\nsingle-agent: tight coupled fix in one file\n')
        self.assertIsNotNone(
            edit_mod._drift_block_verdict(self.session_id, self.cwd))
        # Still denied on retry — same note, already in the snapshot.
        self.assertIsNotNone(
            edit_mod._drift_block_verdict(self.session_id, self.cwd))
        blocks = [e for e in self._stream_events()
                  if e.get('type') == 'drift_hard_block']
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]['notes'],
                         ['single-agent: tight coupled fix in one file'])

    def test_note_added_after_hard_block_disarms(self):
        self._write_stream(
            [{'type': 'task_work'}] * edit_mod.DRIFT_HARD_THRESHOLD)
        self._write_wm('## Context\nnormal session\n')
        self.assertIsNotNone(
            edit_mod._drift_block_verdict(self.session_id, self.cwd))
        self._write_wm(
            '## Context\nnormal session\nSINGLE-AGENT: one-file fix\n')
        self.assertIsNone(
            edit_mod._drift_block_verdict(self.session_id, self.cwd))

    def test_disarm_ends_at_next_delegation_reset(self):
        self._write_stream(
            [{'type': 'task_work'}] * edit_mod.DRIFT_HARD_THRESHOLD)
        self._write_wm('## Context\nnormal session\n')
        self.assertIsNotNone(
            edit_mod._drift_block_verdict(self.session_id, self.cwd))
        self._write_wm('## Context\nsingle-agent: one-file fix\n')
        self.assertIsNone(
            edit_mod._drift_block_verdict(self.session_id, self.cwd))
        # Background delegation resets; a new run of 12 re-arms the block and
        # the old note is snapshotted, so it no longer disarms.
        path = os.path.join(self.streams_dir, f'{self.session_id}.jsonl')
        with open(path, 'a') as f:
            f.write(json.dumps({'type': 'delegation', 'tool': 'Agent'}) + '\n')
            for _ in range(edit_mod.DRIFT_HARD_THRESHOLD):
                f.write(json.dumps({'type': 'task_work', 'w': 1.0}) + '\n')
        self.assertIsNotNone(
            edit_mod._drift_block_verdict(self.session_id, self.cwd))

    def test_low_weight_events_below_threshold_not_blocked(self):
        # 12 low-weight (0.5) events = 6 < 12.
        self._write_stream(
            [{'type': 'task_work', 'w': 0.5}] * edit_mod.DRIFT_HARD_THRESHOLD)
        self._write_wm('## Context\nnormal session\n')
        self.assertIsNone(
            edit_mod._drift_block_verdict(self.session_id, self.cwd))

    def test_low_weight_events_reach_threshold_blocked(self):
        self._write_stream(
            [{'type': 'task_work', 'w': 0.5}] * (edit_mod.DRIFT_HARD_THRESHOLD * 2))
        self._write_wm('## Context\nnormal session\n')
        msg = edit_mod._drift_block_verdict(self.session_id, self.cwd)
        self.assertIsNotNone(msg)
        self.assertIn('weighted task-work 12', msg)

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

    def test_preemptive_note_blocked_then_new_note_allowed(self):
        self._write_stream(
            [{'type': 'task_work'}] * edit_mod.DRIFT_HARD_THRESHOLD)
        self._write_wm(
            '## Context\nsingle-agent: written up front, before any work\n')
        result = self._run_main({'file_path': '/proj/src/x.py'})
        self.assertEqual(
            result.get('hookSpecificOutput', {}).get('permissionDecision'),
            'deny')
        self._write_wm(
            '## Context\nsingle-agent: written up front, before any work\n'
            'single-agent: one-file coupled fix, no split\n')
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

    def test_auto_approve_flag_alone_not_detected(self):
        # auto_approve only skips the WF_CLASSIFY 2b plan-approval question —
        # it must NEVER deny AskUserQuestion.
        self._write_wm('## Task Context\n- auto_approve: true\n')
        self.assertFalse(consent_mod.wm_has_blanket_consent(self.root, self.SESSION))

    def test_no_flag_returns_false(self):
        self._write_wm('## Context\n- normal session\n')
        self.assertFalse(consent_mod.wm_has_blanket_consent(self.root, self.SESSION))

    def test_false_flag_returns_false(self):
        self._write_wm('## Context\n- auto_approve: false\n')
        self.assertFalse(consent_mod.wm_has_blanket_consent(self.root, self.SESSION))

    def test_missing_wm_returns_false(self):
        self.assertFalse(consent_mod.wm_has_blanket_consent(self.root, self.SESSION))

    def test_denied_under_consent_outside_done(self):
        for state in ('WF_EXECUTE', 'WF_VERIFY', 'WF_ARCH_REVIEW'):
            self.assertTrue(consent_mod.question_denied(True, state, {'q': 'x'}), state)

    def test_allowed_in_done_under_consent(self):
        self.assertFalse(consent_mod.question_denied(True, 'WF_DONE', {'q': 'x'}))

    def test_allowed_with_override_tag(self):
        self.assertFalse(consent_mod.question_denied(
            True, 'WF_EXECUTE', {'q': '[consent-override] drop table'}))

    def test_allowed_without_consent(self):
        self.assertFalse(consent_mod.question_denied(False, 'WF_EXECUTE', {'q': 'x'}))


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
