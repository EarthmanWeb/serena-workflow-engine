"""Tests for hooks/pre/* pure functions and module constants.

Targets:
  - pre/swe_pre_edit_validate: _is_bypass_write_attempt, _is_raw_memory_write,
    _block_message; constants EDIT_ALLOWED, WARN_STATES.
  - pre/swe_pre_tool_init_gate: _extract_session_id, _is_bypass_write_attempt,
    check_working_memory_exists, check_lite_mode, inject_metadata; constants
    INIT_ALLOWED_MEMORIES, SKIP_STREAM_TOOLS.
  - pre/swe_pre_bash_test_gate: get_test_sentinel_path, load_bash_policy;
    constant TEST_COMMAND_PATTERNS.

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
from _hookutil import import_hook, reset_caches  # noqa: E402

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
# swe_pre_bash_test_gate
# ---------------------------------------------------------------------------
class TestBashTestGateConstants(unittest.TestCase):
    def test_test_command_patterns_shape(self):
        self.assertIsInstance(bash_mod.TEST_COMMAND_PATTERNS, list)
        self.assertTrue(len(bash_mod.TEST_COMMAND_PATTERNS) >= 1)
        # the sole pattern gates playwright test execution via npx
        self.assertIn(r'\bnpx\s+playwright\s+test\b',
                      bash_mod.TEST_COMMAND_PATTERNS)


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

    def test_repeat_denial_escalates_with_count(self):
        msg = bash_mod.build_denial_message(self.RULE, 'git push', 2)
        self.assertIn('DETERMINISTIC DENIAL ×3', msg)
        self.assertIn('COMMAND STRING must change', msg)

    def test_compound_command_gets_none_ran_note(self):
        msg = bash_mod.build_denial_message(
            self.RULE, 'docker cp a b && git push', 0)
        self.assertIn('NONE of this compound command ran', msg)

    def test_simple_command_has_no_compound_note(self):
        msg = bash_mod.build_denial_message(self.RULE, 'git push', 0)
        self.assertNotIn('compound', msg)


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

    def test_budget_constant_is_five(self):
        self.assertEqual(search_docs_mod.GATED_CALL_BUDGET, 5)

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

    def test_budget_not_exhausted_at_four_gated(self):
        self._write_events([{'type': 'docread'}] + [{'type': 'gated'}] * 4)
        self.assertTrue(search_docs_mod.docs_budget_allows(self.stream))

    def test_budget_exhausted_at_five_gated(self):
        self._write_events([{'type': 'docread'}] + [{'type': 'gated'}] * 5)
        self.assertFalse(search_docs_mod.docs_budget_allows(self.stream))

    def test_new_docread_refills_budget(self):
        self._write_events(
            [{'type': 'docread'}] + [{'type': 'gated'}] * 5 + [{'type': 'docread'}])
        self.assertTrue(search_docs_mod.docs_budget_allows(self.stream))

    def test_gate_and_record_depletes_budget(self):
        # After one docread: exactly GATED_CALL_BUDGET calls pass, then deny.
        self._write_events([{'type': 'docread'}])
        verdicts = [search_docs_mod.gate_and_record(self.stream) for _ in range(6)]
        self.assertEqual(verdicts, [True] * 5 + [False])

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

    def _run_main(self, transcript_path):
        """Drive main() end-to-end with a fully-gated parent session
        (sentinel exists, budget spent). Returns the emitted hook JSON."""
        import contextlib
        import io
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        sentinel = os.path.join(tmp.name, '.init_94aee7ae')
        stream = os.path.join(tmp.name, '94aee7ae.jsonl')
        open(sentinel, 'w').close()
        with open(stream, 'w') as f:
            f.write(json.dumps({'type': 'prompt'}) + '\n')  # no docread: deny
        orig = (search_docs_mod.read_stdin_safe,
                search_docs_mod.get_sentinel_path,
                search_docs_mod.get_stream_path)
        search_docs_mod.read_stdin_safe = lambda **kw: {
            'tool_name': 'Grep', 'tool_input': {'pattern': 'x'},
            'transcript_path': transcript_path}
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
