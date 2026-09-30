"""Tests for hooks/swe_hooks/core/scope_guard.py — per-subagent tool-call
budget + failure-streak circuit breaker.

Covers every pure function: budget_for_model (model-family matching),
parse_budget_tag / parse_scope_extend (tag parsing), classify_kind (edit/
test/bash classification), scope_state (streak accumulation + reset
semantics, extend resets + adds budget), scope_verdict (budget/streak deny,
read-only always allowed), and load_agent_events (stream filtering).

Deterministic + offline: no network, no real Serena. IO goes through
tempfile.TemporaryDirectory.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_core  # noqa: E402

scope_guard = import_core("swe_hooks.core.scope_guard")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
class TestConstants(unittest.TestCase):
    def test_fail_streak_limit_shape(self):
        self.assertEqual(
            scope_guard.FAIL_STREAK_LIMIT, {'test': 2, 'edit': 2, 'bash': 3})

    def test_model_budgets_shape(self):
        self.assertEqual(
            scope_guard.MODEL_BUDGETS,
            {'haiku': 25, 'sonnet': 60, 'opus': 120, 'fable': 120})

    def test_default_budget_and_extend(self):
        self.assertEqual(scope_guard.DEFAULT_BUDGET, 60)
        self.assertEqual(scope_guard.DEFAULT_EXTEND, 30)

    def test_edit_tools_contains_expected(self):
        for t in ('Edit', 'Write', 'NotebookEdit',
                  'mcp__plugin_swe_serena__replace_symbol_body',
                  'mcp__plugin_swe_serena__replace_content',
                  'mcp__plugin_swe_serena__insert_before_symbol',
                  'mcp__plugin_swe_serena__insert_after_symbol'):
            self.assertIn(t, scope_guard.EDIT_TOOLS)

    def test_edit_tools_excludes_read_tools(self):
        self.assertNotIn('Read', scope_guard.EDIT_TOOLS)
        self.assertNotIn('mcp__plugin_swe_serena__find_symbol', scope_guard.EDIT_TOOLS)

    def test_read_only_tools_contains_expected(self):
        for t in ('Read', 'Grep', 'Glob', 'LS', 'ToolSearch', 'SendMessage',
                  'TaskStop', 'mcp__plugin_swe_serena__read_memory',
                  'mcp__plugin_swe_serena__find_symbol'):
            self.assertIn(t, scope_guard.READ_ONLY_TOOLS)

    def test_read_only_tools_excludes_edit_tools(self):
        self.assertEqual(
            scope_guard.READ_ONLY_TOOLS & scope_guard.EDIT_TOOLS, set())


# ---------------------------------------------------------------------------
# budget_for_model
# ---------------------------------------------------------------------------
class TestBudgetForModel(unittest.TestCase):
    def test_haiku_alias(self):
        self.assertEqual(scope_guard.budget_for_model('haiku'), 25)

    def test_sonnet_alias(self):
        self.assertEqual(scope_guard.budget_for_model('sonnet'), 60)

    def test_opus_alias(self):
        self.assertEqual(scope_guard.budget_for_model('opus'), 120)

    def test_fable_alias(self):
        self.assertEqual(scope_guard.budget_for_model('fable'), 120)

    def test_full_model_id_family_match(self):
        self.assertEqual(scope_guard.budget_for_model('claude-haiku-5-1'), 25)
        self.assertEqual(scope_guard.budget_for_model('claude-sonnet-5'), 60)
        self.assertEqual(scope_guard.budget_for_model('claude-opus-4-5'), 120)

    def test_case_insensitive(self):
        self.assertEqual(scope_guard.budget_for_model('HAIKU'), 25)
        self.assertEqual(scope_guard.budget_for_model('Claude-Opus-5'), 120)

    def test_unknown_model_falls_back_to_default(self):
        self.assertEqual(scope_guard.budget_for_model('gpt-4'), scope_guard.DEFAULT_BUDGET)

    def test_empty_or_none_falls_back_to_default(self):
        self.assertEqual(scope_guard.budget_for_model(''), scope_guard.DEFAULT_BUDGET)
        self.assertEqual(scope_guard.budget_for_model(None), scope_guard.DEFAULT_BUDGET)


# ---------------------------------------------------------------------------
# parse_budget_tag
# ---------------------------------------------------------------------------
class TestParseBudgetTag(unittest.TestCase):
    def test_parses_tag(self):
        self.assertEqual(scope_guard.parse_budget_tag('do stuff [swe-budget: 40]'), 40)

    def test_parses_tag_no_space(self):
        self.assertEqual(scope_guard.parse_budget_tag('[swe-budget:15]'), 15)

    def test_case_insensitive(self):
        self.assertEqual(scope_guard.parse_budget_tag('[SWE-BUDGET: 99]'), 99)

    def test_no_tag_returns_none(self):
        self.assertIsNone(scope_guard.parse_budget_tag('just a prompt'))

    def test_empty_prompt_returns_none(self):
        self.assertIsNone(scope_guard.parse_budget_tag(''))
        self.assertIsNone(scope_guard.parse_budget_tag(None))


# ---------------------------------------------------------------------------
# parse_scope_extend
# ---------------------------------------------------------------------------
class TestParseScopeExtend(unittest.TestCase):
    def test_bare_tag_returns_default_extend(self):
        self.assertEqual(
            scope_guard.parse_scope_extend('please continue [scope-extend]'),
            scope_guard.DEFAULT_EXTEND)

    def test_tag_with_n_returns_n(self):
        self.assertEqual(
            scope_guard.parse_scope_extend('[scope-extend: 50]'), 50)

    def test_tag_with_n_no_space(self):
        self.assertEqual(scope_guard.parse_scope_extend('[scope-extend:10]'), 10)

    def test_case_insensitive(self):
        self.assertEqual(
            scope_guard.parse_scope_extend('[SCOPE-EXTEND: 5]'), 5)

    def test_no_tag_returns_none(self):
        self.assertIsNone(scope_guard.parse_scope_extend('keep going'))

    def test_empty_message_returns_none(self):
        self.assertIsNone(scope_guard.parse_scope_extend(''))
        self.assertIsNone(scope_guard.parse_scope_extend(None))


# ---------------------------------------------------------------------------
# classify_kind
# ---------------------------------------------------------------------------
class TestClassifyKind(unittest.TestCase):
    def test_edit_tool_is_edit(self):
        self.assertEqual(scope_guard.classify_kind('Edit', {}), 'edit')
        self.assertEqual(scope_guard.classify_kind('Write', {}), 'edit')
        self.assertEqual(scope_guard.classify_kind('NotebookEdit', {}), 'edit')
        self.assertEqual(
            scope_guard.classify_kind(
                'mcp__plugin_swe_serena__replace_symbol_body', {}),
            'edit')

    def test_bash_test_command_is_test(self):
        self.assertEqual(
            scope_guard.classify_kind('Bash', {'command': 'python3 -m unittest tests.foo'}),
            'test')
        self.assertEqual(
            scope_guard.classify_kind('Bash', {'command': 'npm test'}), 'test')
        self.assertEqual(
            scope_guard.classify_kind('Bash', {'command': 'pytest tests/'}), 'test')

    def test_bash_non_test_command_is_bash(self):
        self.assertEqual(
            scope_guard.classify_kind('Bash', {'command': 'ls -la'}), 'bash')
        self.assertEqual(
            scope_guard.classify_kind('Bash', {'command': 'git status'}), 'bash')

    def test_bash_missing_command_is_bash(self):
        self.assertEqual(scope_guard.classify_kind('Bash', {}), 'bash')

    def test_other_tools_are_none(self):
        self.assertIsNone(scope_guard.classify_kind('Read', {}))
        self.assertIsNone(scope_guard.classify_kind('Grep', {'pattern': 'x'}))
        self.assertIsNone(scope_guard.classify_kind('SendMessage', {}))


# ---------------------------------------------------------------------------
# load_agent_events
# ---------------------------------------------------------------------------
class TestLoadAgentEvents(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stream_path = os.path.join(self.tmp.name, 'stream.jsonl')

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, events):
        with open(self.stream_path, 'w') as f:
            for e in events:
                f.write(json.dumps(e) + '\n')

    def test_missing_file_returns_empty(self):
        self.assertEqual(
            scope_guard.load_agent_events('/no/such/file.jsonl', 'agent-1'), [])

    def test_filters_by_agent_id(self):
        self._write([
            {'type': 'agent_call', 'agent': 'agent-1', 'tool': 'Bash'},
            {'type': 'agent_call', 'agent': 'agent-2', 'tool': 'Bash'},
        ])
        events = scope_guard.load_agent_events(self.stream_path, 'agent-1')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['agent'], 'agent-1')

    def test_filters_by_tracked_type(self):
        self._write([
            {'type': 'agent_call', 'agent': 'agent-1', 'tool': 'Bash'},
            {'type': 'tool', 'agent': 'agent-1', 'name': 'Bash'},
            {'type': 'docread', 'agent': 'agent-1', 'name': 'wf/WF_X'},
        ])
        events = scope_guard.load_agent_events(self.stream_path, 'agent-1')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['type'], 'agent_call')

    def test_all_tracked_types_pass(self):
        self._write([
            {'type': 'agent_spawn', 'agent': 'a1', 'model': 'sonnet', 'budget': 60},
            {'type': 'agent_call', 'agent': 'a1', 'tool': 'Bash'},
            {'type': 'agent_ok', 'agent': 'a1', 'kind': 'bash'},
            {'type': 'agent_fail', 'agent': 'a1', 'kind': 'bash'},
            {'type': 'scope_extend', 'agent': 'a1', 'budget_add': 30},
        ])
        events = scope_guard.load_agent_events(self.stream_path, 'a1')
        self.assertEqual(len(events), 5)

    def test_malformed_lines_skipped(self):
        with open(self.stream_path, 'w') as f:
            f.write('not json\n')
            f.write(json.dumps({'type': 'agent_call', 'agent': 'a1', 'tool': 'X'}) + '\n')
        events = scope_guard.load_agent_events(self.stream_path, 'a1')
        self.assertEqual(len(events), 1)

    def test_empty_stream_path_returns_empty(self):
        self.assertEqual(scope_guard.load_agent_events('', 'a1'), [])
        self.assertEqual(scope_guard.load_agent_events(None, 'a1'), [])


# ---------------------------------------------------------------------------
# scope_state
# ---------------------------------------------------------------------------
class TestScopeState(unittest.TestCase):
    def test_no_events_uses_default_budget(self):
        state = scope_guard.scope_state([], 'a1')
        self.assertEqual(state['budget'], scope_guard.DEFAULT_BUDGET)
        self.assertEqual(state['calls'], 0)
        self.assertEqual(state['streaks'], {})
        self.assertEqual(state['extended'], 0)

    def test_spawn_budget_used(self):
        events = [{'type': 'agent_spawn', 'agent': 'a1', 'model': 'haiku', 'budget': 25}]
        state = scope_guard.scope_state(events, 'a1')
        self.assertEqual(state['budget'], 25)

    def test_latest_spawn_budget_wins(self):
        events = [
            {'type': 'agent_spawn', 'agent': 'a1', 'budget': 25},
            {'type': 'agent_spawn', 'agent': 'a1', 'budget': 60},
        ]
        state = scope_guard.scope_state(events, 'a1')
        self.assertEqual(state['budget'], 60)

    def test_calls_counted(self):
        events = [
            {'type': 'agent_call', 'agent': 'a1', 'tool': 'Bash'},
            {'type': 'agent_call', 'agent': 'a1', 'tool': 'Read'},
            {'type': 'agent_call', 'agent': 'a1', 'tool': 'Edit'},
        ]
        state = scope_guard.scope_state(events, 'a1')
        self.assertEqual(state['calls'], 3)

    def test_fail_streak_accumulates(self):
        events = [
            {'type': 'agent_fail', 'agent': 'a1', 'kind': 'test'},
            {'type': 'agent_fail', 'agent': 'a1', 'kind': 'test'},
        ]
        state = scope_guard.scope_state(events, 'a1')
        self.assertEqual(state['streaks']['test'], 2)

    def test_ok_resets_streak_of_same_kind(self):
        events = [
            {'type': 'agent_fail', 'agent': 'a1', 'kind': 'test'},
            {'type': 'agent_fail', 'agent': 'a1', 'kind': 'test'},
            {'type': 'agent_ok', 'agent': 'a1', 'kind': 'test'},
        ]
        state = scope_guard.scope_state(events, 'a1')
        self.assertEqual(state['streaks']['test'], 0)

    def test_ok_does_not_reset_streak_of_other_kind(self):
        events = [
            {'type': 'agent_fail', 'agent': 'a1', 'kind': 'test'},
            {'type': 'agent_fail', 'agent': 'a1', 'kind': 'edit'},
            {'type': 'agent_ok', 'agent': 'a1', 'kind': 'test'},
        ]
        state = scope_guard.scope_state(events, 'a1')
        self.assertEqual(state['streaks']['test'], 0)
        self.assertEqual(state['streaks']['edit'], 1)

    def test_streak_continues_after_ok_then_new_fail(self):
        events = [
            {'type': 'agent_fail', 'agent': 'a1', 'kind': 'bash'},
            {'type': 'agent_ok', 'agent': 'a1', 'kind': 'bash'},
            {'type': 'agent_fail', 'agent': 'a1', 'kind': 'bash'},
        ]
        state = scope_guard.scope_state(events, 'a1')
        self.assertEqual(state['streaks']['bash'], 1)

    def test_scope_extend_adds_budget(self):
        events = [
            {'type': 'agent_spawn', 'agent': 'a1', 'budget': 60},
            {'type': 'scope_extend', 'agent': 'a1', 'budget_add': 30},
        ]
        state = scope_guard.scope_state(events, 'a1')
        self.assertEqual(state['budget'], 90)
        self.assertEqual(state['extended'], 30)

    def test_multiple_scope_extends_accumulate(self):
        events = [
            {'type': 'agent_spawn', 'agent': 'a1', 'budget': 60},
            {'type': 'scope_extend', 'agent': 'a1', 'budget_add': 30},
            {'type': 'scope_extend', 'agent': 'a1', 'budget_add': 10},
        ]
        state = scope_guard.scope_state(events, 'a1')
        self.assertEqual(state['budget'], 100)

    def test_scope_extend_resets_all_streaks(self):
        events = [
            {'type': 'agent_fail', 'agent': 'a1', 'kind': 'test'},
            {'type': 'agent_fail', 'agent': 'a1', 'kind': 'test'},
            {'type': 'agent_fail', 'agent': 'a1', 'kind': 'edit'},
            {'type': 'scope_extend', 'agent': 'a1', 'budget_add': 30},
        ]
        state = scope_guard.scope_state(events, 'a1')
        self.assertEqual(state['streaks']['test'], 0)
        self.assertEqual(state['streaks']['edit'], 0)

    def test_events_from_other_agent_ignored(self):
        events = [
            {'type': 'agent_fail', 'agent': 'a2', 'kind': 'test'},
            {'type': 'agent_call', 'agent': 'a2', 'tool': 'Bash'},
        ]
        state = scope_guard.scope_state(events, 'a1')
        self.assertEqual(state['calls'], 0)
        self.assertEqual(state['streaks'], {})


# ---------------------------------------------------------------------------
# scope_verdict
# ---------------------------------------------------------------------------
class TestScopeVerdict(unittest.TestCase):
    def test_empty_state_allows(self):
        state = {'budget': 60, 'calls': 0, 'streaks': {}, 'extended': 0}
        self.assertEqual(scope_guard.scope_verdict(state, 'Bash'), '')

    def test_budget_exhausted_denies(self):
        state = {'budget': 10, 'calls': 10, 'streaks': {}, 'extended': 0}
        verdict = scope_guard.scope_verdict(state, 'Bash')
        self.assertIn('[scope-gate]', verdict)
        self.assertIn('budget exhausted', verdict)
        self.assertIn('10/10', verdict)

    def test_budget_over_denies(self):
        state = {'budget': 10, 'calls': 15, 'streaks': {}, 'extended': 0}
        self.assertNotEqual(scope_guard.scope_verdict(state, 'Bash'), '')

    def test_under_budget_allows(self):
        state = {'budget': 60, 'calls': 5, 'streaks': {}, 'extended': 0}
        self.assertEqual(scope_guard.scope_verdict(state, 'Bash'), '')

    def test_fail_streak_at_limit_denies_edit(self):
        state = {'budget': 60, 'calls': 5, 'streaks': {'edit': 2}, 'extended': 0}
        verdict = scope_guard.scope_verdict(state, 'Edit')
        self.assertIn('[scope-gate]', verdict)
        self.assertIn('edit failed 2 times in a row', verdict)

    def test_fail_streak_below_limit_allows(self):
        state = {'budget': 60, 'calls': 5, 'streaks': {'edit': 1}, 'extended': 0}
        self.assertEqual(scope_guard.scope_verdict(state, 'Edit'), '')

    def test_test_streak_limit_is_2(self):
        state = {'budget': 60, 'calls': 5, 'streaks': {'test': 2}, 'extended': 0}
        self.assertIn('[scope-gate]', scope_guard.scope_verdict(state, 'Bash'))

    def test_bash_streak_limit_is_3(self):
        state = {'budget': 60, 'calls': 5, 'streaks': {'bash': 2}, 'extended': 0}
        self.assertEqual(scope_guard.scope_verdict(state, 'Bash'), '')
        state['streaks']['bash'] = 3
        self.assertIn('[scope-gate]', scope_guard.scope_verdict(state, 'Bash'))

    def test_read_only_tool_always_allowed_even_over_budget(self):
        state = {'budget': 10, 'calls': 50, 'streaks': {'edit': 5}, 'extended': 0}
        for tool in ('Read', 'Grep', 'Glob', 'LS', 'ToolSearch', 'SendMessage',
                     'TaskStop', 'mcp__plugin_swe_serena__read_memory',
                     'mcp__plugin_swe_serena__find_symbol'):
            self.assertEqual(scope_guard.scope_verdict(state, tool), '', tool)

    def test_verdict_mentions_stop_and_orchestrator(self):
        state = {'budget': 10, 'calls': 10, 'streaks': {}, 'extended': 0}
        verdict = scope_guard.scope_verdict(state, 'Bash')
        self.assertIn('STOP', verdict)
        self.assertIn('orchestrator', verdict)
        self.assertIn('scope-extend', verdict)


# ---------------------------------------------------------------------------
# End-to-end: events -> state -> verdict
# ---------------------------------------------------------------------------
class TestEndToEnd(unittest.TestCase):
    def test_two_consecutive_test_failures_trip_gate_for_edit_too(self):
        # A subagent that failed a test twice in a row should be denied on
        # its NEXT edit attempt as well as further test runs — the streak
        # limit for 'test' (2) has been reached, and scope_verdict checks
        # every kind's streak against its own limit regardless of which
        # tool is being attempted next.
        events = [
            {'type': 'agent_fail', 'agent': 'a1', 'kind': 'test'},
            {'type': 'agent_fail', 'agent': 'a1', 'kind': 'test'},
        ]
        state = scope_guard.scope_state(events, 'a1')
        self.assertNotEqual(scope_guard.scope_verdict(state, 'Edit'), '')
        self.assertNotEqual(
            scope_guard.scope_verdict(
                state, 'Bash'),
            '')
        # But read-only tools remain available.
        self.assertEqual(scope_guard.scope_verdict(state, 'Read'), '')

    def test_scope_extend_lifts_trip(self):
        events = [
            {'type': 'agent_fail', 'agent': 'a1', 'kind': 'edit'},
            {'type': 'agent_fail', 'agent': 'a1', 'kind': 'edit'},
            {'type': 'scope_extend', 'agent': 'a1', 'budget_add': 30},
        ]
        state = scope_guard.scope_state(events, 'a1')
        self.assertEqual(scope_guard.scope_verdict(state, 'Edit'), '')


if __name__ == '__main__':
    unittest.main()
