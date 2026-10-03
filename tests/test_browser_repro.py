"""Tests for the browser-repro-first gate.

Covers:
  - swe_hooks.core.browser_repro — every pure function: is_e2e_command
    (incl. a gated command hidden on line 2 of a multi-line Bash call),
    is_failed_e2e_output, is_browser_repro_tool (incl. scenario-list NOT
    counting), needs_browser_repro (ordering of e2e_fail vs browser_repro),
    is_e2e_delegation, has_browser_repro_na (the escape prefix).
  - hooks/pre/swe_pre_browser_repro_gate.py main() — deny/allow for both
    Bash (E2E rerun) and Agent/Task (E2E rerun-delegation).
  - hooks/post/swe_post_browser_repro.py main() — 'browser_repro' event
    recording on a browser-devtools tool call, scenario-list NOT recording.
  - hooks/post/swe_post_tool_failure.py — 'e2e_fail' recorded on a crashed
    (nonzero-exit) E2E Bash command.
  - hooks/post/swe_post_doc_claims.py — 'e2e_fail' recorded on an E2E Bash
    command that exits 0 at the shell level but shows a Playwright failure
    in its captured output (the redirected-to-a-log case), including for a
    spawned agent (unlike the doc-claims substitution check in the same
    hook, which is orchestrator-WM-only).

Stdlib unittest only, mirrors tests/test_doc_claims.py and
tests/test_hooks_pre.py's main()-level integration patterns.
"""
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_core, import_hook, reset_caches  # noqa: E402

br = import_core("swe_hooks.core.browser_repro")
gate_mod = import_hook("pre/swe_pre_browser_repro_gate")
repro_hook_mod = import_hook("post/swe_post_browser_repro")
failure_mod = import_hook("post/swe_post_tool_failure")
claims_hook_mod = import_hook("post/swe_post_doc_claims")


# ---------------------------------------------------------------------------
# core.browser_repro — is_e2e_command
# ---------------------------------------------------------------------------
class TestIsE2eCommand(unittest.TestCase):
    def test_npx_playwright_test_matches(self):
        self.assertTrue(br.is_e2e_command('npx playwright test specs/foo.spec.ts'))

    def test_run_test_single_script_matches(self):
        self.assertTrue(br.is_e2e_command('WP_SITE=demo1 ./run-test-single.sh "clone event"'))

    def test_npm_run_demo1_t_matches(self):
        self.assertTrue(br.is_e2e_command('npm run demo1:t -- "14-clone-event"'))

    def test_npm_run_demo1_bare_matches(self):
        self.assertTrue(br.is_e2e_command('npm run demo1'))

    def test_npm_run_demo1_scoped_project_matches(self):
        self.assertTrue(br.is_e2e_command('npm run demo1:em-events-calendar'))

    def test_gated_command_hidden_on_line_two_of_multiline_bash_matches(self):
        command = (
            "cd /Users/webdev/LocalSites/convenely/convenely_plugin_repo/tests\n"
            "npx playwright test specs/em-events-calendar/14-clone-event.spec.ts"
        )
        self.assertTrue(br.is_e2e_command(command))

    def test_unrelated_command_does_not_match(self):
        self.assertFalse(br.is_e2e_command('composer test'))

    def test_phpunit_does_not_match(self):
        self.assertFalse(br.is_e2e_command('cd em-crm && composer test'))

    def test_empty_command_does_not_match(self):
        self.assertFalse(br.is_e2e_command(''))
        self.assertFalse(br.is_e2e_command(None))

    def test_npm_run_test_without_colon_does_not_match_t_pattern(self):
        # 'npm run test' (bare project test script) is NOT the single-test
        # ':t' runner and not 'demo1' — must not false-positive.
        self.assertFalse(br.is_e2e_command('npm run test'))


# ---------------------------------------------------------------------------
# core.browser_repro — is_failed_e2e_output
# ---------------------------------------------------------------------------
class TestIsFailedE2eOutput(unittest.TestCase):
    def test_n_failed_summary_line_detected(self):
        self.assertTrue(br.is_failed_e2e_output(
            "Running 12 tests using 1 worker\n\n  1 failed\n  11 passed"))

    def test_exit_nonzero_marker_detected(self):
        self.assertTrue(br.is_failed_e2e_output("all tests ran\nexit 1"))

    def test_exit_zero_marker_is_not_a_failure(self):
        self.assertFalse(br.is_failed_e2e_output("all tests ran\nexit 0"))

    def test_all_passed_output_is_not_a_failure(self):
        self.assertFalse(br.is_failed_e2e_output("12 passed (3.4s)"))

    def test_empty_output_is_not_a_failure(self):
        self.assertFalse(br.is_failed_e2e_output(''))
        self.assertFalse(br.is_failed_e2e_output(None))


# ---------------------------------------------------------------------------
# core.browser_repro — is_browser_repro_tool
# ---------------------------------------------------------------------------
class TestIsBrowserReproTool(unittest.TestCase):
    def test_navigation_tool_counts(self):
        self.assertTrue(br.is_browser_repro_tool(
            'mcp__browser-devtools__navigation_go-to'))

    def test_interaction_tool_counts(self):
        self.assertTrue(br.is_browser_repro_tool(
            'mcp__browser-devtools__interaction_click'))

    def test_a11y_tool_counts(self):
        self.assertTrue(br.is_browser_repro_tool(
            'mcp__browser-devtools__a11y_take-aria-snapshot'))

    def test_content_tool_counts(self):
        self.assertTrue(br.is_browser_repro_tool(
            'mcp__browser-devtools__content_take-screenshot'))

    def test_o11y_tool_counts(self):
        self.assertTrue(br.is_browser_repro_tool(
            'mcp__browser-devtools__o11y_get-console-messages'))

    def test_scenario_run_counts(self):
        self.assertTrue(br.is_browser_repro_tool(
            'mcp__browser-devtools__scenario-run'))

    def test_execute_counts(self):
        self.assertTrue(br.is_browser_repro_tool(
            'mcp__browser-devtools__execute'))

    def test_scenario_list_does_not_count(self):
        self.assertFalse(br.is_browser_repro_tool(
            'mcp__browser-devtools__scenario-list'))

    def test_scenario_search_does_not_count(self):
        self.assertFalse(br.is_browser_repro_tool(
            'mcp__browser-devtools__scenario-search'))

    def test_scenario_add_does_not_count(self):
        self.assertFalse(br.is_browser_repro_tool(
            'mcp__browser-devtools__scenario-add'))

    def test_scenario_delete_does_not_count(self):
        self.assertFalse(br.is_browser_repro_tool(
            'mcp__browser-devtools__scenario-delete'))

    def test_scenario_update_does_not_count(self):
        self.assertFalse(br.is_browser_repro_tool(
            'mcp__browser-devtools__scenario-update'))

    def test_non_browser_devtools_tool_does_not_count(self):
        self.assertFalse(br.is_browser_repro_tool('mcp__wp-cli__wp_cli'))
        self.assertFalse(br.is_browser_repro_tool('Bash'))

    def test_empty_tool_name_does_not_count(self):
        self.assertFalse(br.is_browser_repro_tool(''))
        self.assertFalse(br.is_browser_repro_tool(None))


# ---------------------------------------------------------------------------
# core.browser_repro — needs_browser_repro
# ---------------------------------------------------------------------------
class TestNeedsBrowserRepro(unittest.TestCase):
    def test_no_events_does_not_need_repro(self):
        self.assertFalse(br.needs_browser_repro([]))

    def test_no_failure_at_all_does_not_need_repro(self):
        events = [{'type': 'docread'}, {'type': 'browser_repro'}]
        self.assertFalse(br.needs_browser_repro(events))

    def test_failure_with_no_repro_at_all_needs_repro(self):
        events = [{'type': 'e2e_fail'}]
        self.assertTrue(br.needs_browser_repro(events))

    def test_repro_after_failure_satisfies(self):
        events = [{'type': 'e2e_fail'}, {'type': 'browser_repro'}]
        self.assertFalse(br.needs_browser_repro(events))

    def test_repro_before_failure_does_not_satisfy(self):
        # A repro that happened BEFORE this failure does not excuse it —
        # the ordering must be repro AFTER the most recent failure.
        events = [{'type': 'browser_repro'}, {'type': 'e2e_fail'}]
        self.assertTrue(br.needs_browser_repro(events))

    def test_second_failure_after_a_satisfied_first_needs_repro_again(self):
        events = [
            {'type': 'e2e_fail'},
            {'type': 'browser_repro'},
            {'type': 'e2e_fail'},
        ]
        self.assertTrue(br.needs_browser_repro(events))

    def test_repro_from_a_different_agent_still_satisfies(self):
        events = [
            {'type': 'e2e_fail', 'agent': 'agent-A'},
            {'type': 'browser_repro', 'agent': 'agent-B'},
        ]
        self.assertFalse(br.needs_browser_repro(events))

    def test_non_dict_events_are_ignored(self):
        events = ['garbage', {'type': 'e2e_fail'}, 42]
        self.assertTrue(br.needs_browser_repro(events))


# ---------------------------------------------------------------------------
# core.browser_repro — is_e2e_delegation
# ---------------------------------------------------------------------------
class TestIsE2eDelegation(unittest.TestCase):
    def test_playwright_mention_matches(self):
        self.assertTrue(br.is_e2e_delegation(
            "Rerun the playwright spec with the layout-shift fix applied."))

    def test_spec_ts_filename_matches(self):
        self.assertTrue(br.is_e2e_delegation(
            "Fix specs/em-events-calendar/14-clone-event.spec.ts and rerun it."))

    def test_run_test_single_matches(self):
        self.assertTrue(br.is_e2e_delegation(
            "Use run-test-single.sh to confirm the fix."))

    def test_demo1_t_matches(self):
        self.assertTrue(br.is_e2e_delegation("npm run demo1:t -- 'clone event'"))

    def test_npm_run_demo1_matches(self):
        self.assertTrue(br.is_e2e_delegation("Run npm run demo1 again please."))

    def test_unrelated_prompt_does_not_match(self):
        self.assertFalse(br.is_e2e_delegation(
            "Read the FEATURE_CRM memory and summarize the board system."))

    def test_empty_prompt_does_not_match(self):
        self.assertFalse(br.is_e2e_delegation(''))
        self.assertFalse(br.is_e2e_delegation(None))


# ---------------------------------------------------------------------------
# core.browser_repro — has_browser_repro_na (escape prefix)
# ---------------------------------------------------------------------------
class TestHasBrowserReproNa(unittest.TestCase):
    def test_escape_prefix_present(self):
        self.assertTrue(br.has_browser_repro_na(
            'BROWSER_REPRO_NA=1 npx playwright test specs/em-crm/01.spec.ts'))

    def test_escape_prefix_absent(self):
        self.assertFalse(br.has_browser_repro_na(
            'npx playwright test specs/em-crm/01.spec.ts'))

    def test_escape_prefix_requires_value_one(self):
        self.assertFalse(br.has_browser_repro_na(
            'BROWSER_REPRO_NA=0 npx playwright test specs/em-crm/01.spec.ts'))

    def test_empty_command(self):
        self.assertFalse(br.has_browser_repro_na(''))
        self.assertFalse(br.has_browser_repro_na(None))


# ---------------------------------------------------------------------------
# pre/swe_pre_browser_repro_gate — main() integration
# ---------------------------------------------------------------------------
class TestBrowserReproGateMain(unittest.TestCase):
    SESSION = 'f00dcafe'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name
        self.stream = os.path.join(self.cwd, f'{self.SESSION}.jsonl')
        self._orig_stream_path = gate_mod.get_stream_path
        gate_mod.get_stream_path = lambda sid: self.stream
        reset_caches()

    def tearDown(self):
        gate_mod.get_stream_path = self._orig_stream_path
        self.tmp.cleanup()
        reset_caches()

    def _transcript(self):
        return f'/x/{self.SESSION}-0000-0000-0000-000000000000.jsonl'

    def _write_stream(self, events):
        with open(self.stream, 'w') as f:
            for e in events:
                f.write(json.dumps(e) + '\n')

    def _run_main(self, tool_name, tool_input):
        payload = {
            'tool_name': tool_name,
            'tool_input': tool_input,
            'transcript_path': self._transcript(),
            'cwd': self.cwd,
        }
        orig = gate_mod.read_stdin_safe
        gate_mod.read_stdin_safe = lambda **kw: payload
        buf = io.StringIO()
        import contextlib
        try:
            with contextlib.redirect_stdout(buf):
                with self.assertRaises(SystemExit):
                    gate_mod.main()
        finally:
            gate_mod.read_stdin_safe = orig
        return json.loads(buf.getvalue() or '{}')

    # --- Bash ---

    def test_bash_e2e_denied_after_unreproduced_failure(self):
        self._write_stream([{'type': 'e2e_fail'}])
        result = self._run_main('Bash', {'command': 'npx playwright test specs/foo.spec.ts'})
        out = result.get('hookSpecificOutput', {})
        self.assertEqual(out.get('permissionDecision'), 'deny')
        self.assertIn('BROWSER REPRO FIRST', out.get('permissionDecisionReason', ''))

    def test_bash_e2e_allowed_when_no_failure_recorded(self):
        result = self._run_main('Bash', {'command': 'npx playwright test specs/foo.spec.ts'})
        self.assertNotEqual(
            result.get('hookSpecificOutput', {}).get('permissionDecision'), 'deny')

    def test_bash_e2e_allowed_after_repro_follows_failure(self):
        self._write_stream([{'type': 'e2e_fail'}, {'type': 'browser_repro'}])
        result = self._run_main('Bash', {'command': 'npx playwright test specs/foo.spec.ts'})
        self.assertNotEqual(
            result.get('hookSpecificOutput', {}).get('permissionDecision'), 'deny')

    def test_bash_e2e_allowed_with_escape_prefix(self):
        self._write_stream([{'type': 'e2e_fail'}])
        result = self._run_main(
            'Bash',
            {'command': 'BROWSER_REPRO_NA=1 npx playwright test specs/foo.spec.ts'})
        self.assertNotEqual(
            result.get('hookSpecificOutput', {}).get('permissionDecision'), 'deny')

    def test_bash_non_e2e_command_allowed_even_after_failure(self):
        self._write_stream([{'type': 'e2e_fail'}])
        result = self._run_main('Bash', {'command': 'composer test'})
        self.assertNotEqual(
            result.get('hookSpecificOutput', {}).get('permissionDecision'), 'deny')

    # --- Agent/Task ---

    def test_agent_e2e_rerun_delegation_denied_after_unreproduced_failure(self):
        self._write_stream([{'type': 'e2e_fail'}])
        result = self._run_main('Agent', {
            'prompt': 'Rerun specs/em-events-calendar/14-clone-event.spec.ts with the fix.',
            'model': 'sonnet',
        })
        out = result.get('hookSpecificOutput', {})
        self.assertEqual(out.get('permissionDecision'), 'deny')
        self.assertIn('BROWSER REPRO FIRST', out.get('permissionDecisionReason', ''))

    def test_task_tool_name_also_gated(self):
        self._write_stream([{'type': 'e2e_fail'}])
        result = self._run_main('Task', {
            'prompt': 'Use npm run demo1:t to confirm the fix works now.',
            'model': 'sonnet',
        })
        self.assertEqual(
            result.get('hookSpecificOutput', {}).get('permissionDecision'), 'deny')

    def test_agent_e2e_delegation_allowed_after_repro(self):
        self._write_stream([{'type': 'e2e_fail'}, {'type': 'browser_repro'}])
        result = self._run_main('Agent', {
            'prompt': 'Rerun specs/em-events-calendar/14-clone-event.spec.ts with the fix.',
            'model': 'sonnet',
        })
        self.assertNotEqual(
            result.get('hookSpecificOutput', {}).get('permissionDecision'), 'deny')

    def test_agent_non_e2e_prompt_allowed_even_after_failure(self):
        self._write_stream([{'type': 'e2e_fail'}])
        result = self._run_main('Agent', {
            'prompt': 'Read FEATURE_CRM and summarize the board system.',
            'model': 'haiku',
        })
        self.assertNotEqual(
            result.get('hookSpecificOutput', {}).get('permissionDecision'), 'deny')

    def test_other_tool_untouched(self):
        self._write_stream([{'type': 'e2e_fail'}])
        result = self._run_main('Read', {'file_path': '/x/y.py'})
        self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# post/swe_post_browser_repro — main() integration
# ---------------------------------------------------------------------------
class TestPostBrowserReproMain(unittest.TestCase):
    SESSION = 'ab00cd11'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name
        self.stream = os.path.join(self.cwd, f'{self.SESSION}.jsonl')
        self._orig_stream_path = repro_hook_mod.get_stream_path
        repro_hook_mod.get_stream_path = lambda sid: self.stream

    def tearDown(self):
        repro_hook_mod.get_stream_path = self._orig_stream_path
        self.tmp.cleanup()

    def _run_main(self, tool_name, agent_id=None):
        payload = {
            'tool_name': tool_name,
            'transcript_path': f'/x/{self.SESSION}-0000-0000-0000-000000000000.jsonl',
            'cwd': self.cwd,
        }
        if agent_id:
            payload['agent_id'] = agent_id
        orig = repro_hook_mod.read_stdin_safe
        repro_hook_mod.read_stdin_safe = lambda **kw: payload
        buf = io.StringIO()
        import contextlib
        try:
            with contextlib.redirect_stdout(buf):
                with self.assertRaises(SystemExit):
                    repro_hook_mod.main()
        finally:
            repro_hook_mod.read_stdin_safe = orig
        return json.loads(buf.getvalue() or '{}')

    def _events(self):
        if not os.path.exists(self.stream):
            return []
        with open(self.stream) as f:
            return [json.loads(line) for line in f if line.strip()]

    def test_navigation_tool_records_browser_repro_event(self):
        self._run_main('mcp__browser-devtools__navigation_go-to')
        events = self._events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['type'], 'browser_repro')

    def test_scenario_list_does_not_record(self):
        self._run_main('mcp__browser-devtools__scenario-list')
        self.assertEqual(self._events(), [])

    def test_other_tool_does_not_record(self):
        self._run_main('Bash')
        self.assertEqual(self._events(), [])

    def test_records_agent_field_for_spawned_agent(self):
        self._run_main('mcp__browser-devtools__interaction_click', agent_id='agent-42')
        events = self._events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].get('agent'), 'agent-42')

    def test_main_agent_call_has_no_agent_field(self):
        self._run_main('mcp__browser-devtools__a11y_take-aria-snapshot')
        events = self._events()
        self.assertEqual(len(events), 1)
        self.assertNotIn('agent', events[0])


# ---------------------------------------------------------------------------
# post/swe_post_tool_failure — e2e_fail on a crashed (nonzero-exit) E2E run
# ---------------------------------------------------------------------------
class TestToolFailureE2eFailRecording(unittest.TestCase):
    SESSION = '12ab34cd'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name
        self.stream = os.path.join(self.cwd, f'{self.SESSION}.jsonl')
        self._orig_stream_path = failure_mod.get_stream_path
        failure_mod.get_stream_path = lambda sid: self.stream

    def tearDown(self):
        failure_mod.get_stream_path = self._orig_stream_path
        self.tmp.cleanup()

    def _run_main(self, tool_name, tool_input, tool_error='Command failed', agent_id=None):
        payload = {
            'tool_name': tool_name,
            'tool_input': tool_input,
            'tool_error': tool_error,
            'transcript_path': f'/x/{self.SESSION}-0000-0000-0000-000000000000.jsonl',
            'cwd': self.cwd,
        }
        if agent_id:
            payload['agent_id'] = agent_id
        orig = failure_mod.read_stdin_safe
        failure_mod.read_stdin_safe = lambda **kw: payload
        buf = io.StringIO()
        import contextlib
        try:
            with contextlib.redirect_stdout(buf):
                with self.assertRaises(SystemExit):
                    failure_mod.main()
        finally:
            failure_mod.read_stdin_safe = orig
        return json.loads(buf.getvalue() or '{}')

    def _events(self, event_type):
        if not os.path.exists(self.stream):
            return []
        with open(self.stream) as f:
            return [json.loads(line) for line in f
                    if line.strip() and json.loads(line).get('type') == event_type]

    def test_crashed_playwright_command_records_e2e_fail(self):
        self._run_main('Bash', {'command': 'npx playwright test specs/foo.spec.ts'})
        self.assertEqual(len(self._events('e2e_fail')), 1)

    def test_non_e2e_bash_failure_does_not_record_e2e_fail(self):
        self._run_main('Bash', {'command': 'composer test'})
        self.assertEqual(len(self._events('e2e_fail')), 0)

    def test_non_bash_tool_does_not_record_e2e_fail(self):
        self._run_main('Edit', {'file_path': '/x/y.py'})
        self.assertEqual(len(self._events('e2e_fail')), 0)

    def test_spawned_agent_e2e_fail_carries_agent_field(self):
        self._run_main(
            'Bash', {'command': 'npx playwright test specs/foo.spec.ts'},
            agent_id='agent-99')
        events = self._events('e2e_fail')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].get('agent'), 'agent-99')


# ---------------------------------------------------------------------------
# post/swe_post_doc_claims — e2e_fail on a redirected (exit-0) E2E run
# ---------------------------------------------------------------------------
class TestDocClaimsE2eFailRecording(unittest.TestCase):
    SESSION = '34cd56ef'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name
        self.stream = os.path.join(self.cwd, f'{self.SESSION}.jsonl')
        self._orig_stream_path = claims_hook_mod.get_stream_path
        claims_hook_mod.get_stream_path = lambda sid: self.stream

    def tearDown(self):
        claims_hook_mod.get_stream_path = self._orig_stream_path
        self.tmp.cleanup()

    def _run_main(self, command, tool_response='', agent_id=None, tool_name='Bash'):
        payload = {
            'tool_name': tool_name,
            'tool_input': {'command': command},
            'tool_response': tool_response,
            'transcript_path': f'/x/{self.SESSION}-0000-0000-0000-000000000000.jsonl',
            'cwd': self.cwd,
        }
        if agent_id:
            payload['agent_id'] = agent_id
        orig = claims_hook_mod.read_stdin_safe
        claims_hook_mod.read_stdin_safe = lambda **kw: payload
        buf = io.StringIO()
        import contextlib
        try:
            with contextlib.redirect_stdout(buf):
                with self.assertRaises(SystemExit):
                    claims_hook_mod.main()
        finally:
            claims_hook_mod.read_stdin_safe = orig
        return json.loads(buf.getvalue() or '{}')

    def _events(self, event_type):
        if not os.path.exists(self.stream):
            return []
        with open(self.stream) as f:
            return [json.loads(line) for line in f
                    if line.strip() and json.loads(line).get('type') == event_type]

    def test_redirected_run_with_failed_output_records_e2e_fail(self):
        self._run_main(
            'npx playwright test specs/foo.spec.ts > run.log 2>&1; echo exit $?',
            tool_response='Running 3 tests\n\n  1 failed\n  2 passed\nexit 1')
        self.assertEqual(len(self._events('e2e_fail')), 1)

    def test_redirected_run_with_passing_output_does_not_record(self):
        self._run_main(
            'npx playwright test specs/foo.spec.ts > run.log 2>&1; echo exit $?',
            tool_response='3 passed\nexit 0')
        self.assertEqual(len(self._events('e2e_fail')), 0)

    def test_non_e2e_command_does_not_record(self):
        self._run_main('composer test', tool_response='1 failed')
        self.assertEqual(len(self._events('e2e_fail')), 0)

    def test_spawned_agent_e2e_fail_still_recorded(self):
        # Unlike the doc-claims substitution check in this same hook, e2e_fail
        # recording is NOT orchestrator-WM-only — a subagent's observed
        # failure must still trip the gate for everyone.
        self._run_main(
            'npx playwright test specs/foo.spec.ts > run.log 2>&1; echo exit $?',
            tool_response='1 failed', agent_id='agent-7')
        events = self._events('e2e_fail')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].get('agent'), 'agent-7')


if __name__ == '__main__':
    unittest.main()
