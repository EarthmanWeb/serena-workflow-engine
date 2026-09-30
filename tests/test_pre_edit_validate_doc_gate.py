"""Tests for the per-agent DOC REQUIREMENT gate in
hooks/pre/swe_pre_edit_validate.py.

Targets:
  - doc_gate_verdict(target, project_root, read_names) — pure function.
  - main() integration: the doc-requirement gate applies to the MAIN AGENT
    ONLY. A spawned agent is fully exempt from edit validation (state gate,
    sweep gate, doc gate, drift block) and is allowed regardless of its own
    docreads — doc-requirement enforcement for subagents happens at
    DELEGATION time instead (swe_pre_agent_model_gate.py's [sweep-gate]).

Deterministic + offline: no network, no real Serena, no real git. IO goes
through tempfile.TemporaryDirectory.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_hook, reset_caches  # noqa: E402

edit_mod = import_hook("pre/swe_pre_edit_validate")


class TestDocGateVerdictPure(unittest.TestCase):
    """doc_gate_verdict(target, project_root, read_names) — pure function
    over core.doc_requirements.required_docs_for_path /
    unread_required_docs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write_feature_doc(self, name, paths):
        rel_dir, base = name.split('/')
        d = os.path.join(self.root, '.serena', 'memory', rel_dir)
        os.makedirs(d, exist_ok=True)
        lines = ['---', 'paths:']
        for p in paths:
            lines.append(f'  - "{p}"')
        lines.append('---')
        lines.append(f'# {base}')
        with open(os.path.join(d, base + '.md'), 'w') as f:
            f.write('\n'.join(lines))

    def _write_test_harness_doc(self):
        d = os.path.join(self.root, '.serena', 'memory', 'feature')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'FEATURE_TESTS.md'), 'w') as f:
            f.write('# FEATURE_TESTS\n')

    def test_empty_target_allows(self):
        self.assertEqual(edit_mod.doc_gate_verdict('', self.root, set()), '')

    def test_unmatched_path_allows(self):
        verdict = edit_mod.doc_gate_verdict(
            'src/unrelated.py', self.root, set())
        self.assertEqual(verdict, '')

    def test_matched_path_unread_denies(self):
        self._write_feature_doc('feature/FEATURE_WIDGET', ['src/widget/**/*.py'])
        verdict = edit_mod.doc_gate_verdict(
            'src/widget/core.py', self.root, set())
        self.assertNotEqual(verdict, '')
        self.assertIn('[doc-gate]', verdict)
        self.assertIn('feature/FEATURE_WIDGET', verdict)
        self.assertIn('read_memory("feature/FEATURE_WIDGET")', verdict)
        self.assertIn('src/widget/core.py', verdict)
        self.assertIn('then retry this edit', verdict)

    def test_matched_path_read_allows(self):
        self._write_feature_doc('feature/FEATURE_WIDGET', ['src/widget/**/*.py'])
        verdict = edit_mod.doc_gate_verdict(
            'src/widget/core.py', self.root, {'feature/FEATURE_WIDGET'})
        self.assertEqual(verdict, '')

    def test_test_artifact_requires_feature_tests(self):
        self._write_test_harness_doc()
        verdict = edit_mod.doc_gate_verdict(
            'tests/test_new.py', self.root, set())
        self.assertIn('[doc-gate]', verdict)
        self.assertIn('feature/FEATURE_TESTS', verdict)

    def test_test_artifact_with_feature_tests_read_allows(self):
        self._write_test_harness_doc()
        verdict = edit_mod.doc_gate_verdict(
            'tests/test_new.py', self.root, {'feature/FEATURE_TESTS'})
        self.assertEqual(verdict, '')

    def test_test_artifact_no_harness_doc_ungated(self):
        verdict = edit_mod.doc_gate_verdict(
            'tests/test_new.py', self.root, set())
        self.assertEqual(verdict, '')


class TestDocGateMainIntegration(unittest.TestCase):
    """main() end-to-end: per-agent doc gate applies to both spawned agents
    (as the ONLY check) and the main agent (in addition to sweep/drift)."""

    SESSION = 'deadbeef'

    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name
        self.streams_dir = os.path.join(self.cwd, '.serena', 'streams')
        self.memories_dir = os.path.join(self.cwd, '.serena', 'memories')
        os.makedirs(self.streams_dir, exist_ok=True)
        os.makedirs(self.memories_dir, exist_ok=True)

        from swe_hooks.core import session as core_session
        from swe_hooks.core import config as core_config
        self._orig_session_root = core_session.get_project_root
        self._orig_config_root = core_config.get_project_root
        core_session.get_project_root = lambda: self.cwd
        core_config.get_project_root = lambda: self.cwd

        self._orig_stream_path = edit_mod.get_stream_path
        edit_mod.get_stream_path = (
            lambda sid: os.path.join(self.streams_dir, f'{sid}.jsonl'))
        # edit_mod's own `from ... import get_project_root` binding must be
        # patched directly too — rebinding core_config's module attribute
        # does not change a name already imported into edit_mod's namespace.
        self._orig_edit_mod_root = edit_mod.get_project_root
        edit_mod.get_project_root = lambda: self.cwd

        # Main-agent flows need WF_EXECUTE + sweep sentinel so the doc gate
        # (which runs after the sweep gate) is actually reached.
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
        edit_mod.get_project_root = self._orig_edit_mod_root
        self.tmp.cleanup()
        reset_caches()

    def _write_feature_doc(self, name, paths):
        rel_dir, base = name.split('/')
        d = os.path.join(self.cwd, '.serena', 'memory', rel_dir)
        os.makedirs(d, exist_ok=True)
        lines = ['---', 'paths:']
        for p in paths:
            lines.append(f'  - "{p}"')
        lines.append('---')
        lines.append(f'# {base}')
        with open(os.path.join(d, base + '.md'), 'w') as f:
            f.write('\n'.join(lines))

    def _write_stream(self, events):
        path = os.path.join(self.streams_dir, f'{self.SESSION}.jsonl')
        with open(path, 'w') as f:
            for e in events:
                f.write(json.dumps(e) + '\n')

    def _transcript(self):
        return f'/x/{self.SESSION}-0000-0000-0000-000000000000.jsonl'

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

    # --- spawned agent: fully exempt, no doc gate --------------------------

    def test_subagent_editing_matched_path_without_own_docread_allowed(self):
        # Spawned agents are fully exempt from the doc gate — enforcement
        # moved to delegation time (swe_pre_agent_model_gate.py).
        self._write_feature_doc('feature/FEATURE_WIDGET', ['src/widget/**/*.py'])
        result = self._run_main(
            {'file_path': os.path.join(self.cwd, 'src/widget/core.py')},
            extra={'agent_id': 'sub-1'})
        out = result.get('hookSpecificOutput', {})
        self.assertNotEqual(out.get('permissionDecision'), 'deny')

    def test_subagent_editing_matched_path_with_docread_still_allowed(self):
        self._write_feature_doc('feature/FEATURE_WIDGET', ['src/widget/**/*.py'])
        self._write_stream([
            {'type': 'docread', 'name': 'feature/FEATURE_WIDGET', 'agent': 'sub-1'},
        ])
        result = self._run_main(
            {'file_path': os.path.join(self.cwd, 'src/widget/core.py')},
            extra={'agent_id': 'sub-1'})
        out = result.get('hookSpecificOutput', {})
        self.assertNotEqual(out.get('permissionDecision'), 'deny')

    def test_subagent_editing_unmatched_path_allowed(self):
        self._write_feature_doc('feature/FEATURE_WIDGET', ['src/widget/**/*.py'])
        result = self._run_main(
            {'file_path': os.path.join(self.cwd, 'src/other/thing.py')},
            extra={'agent_id': 'sub-1'})
        out = result.get('hookSpecificOutput', {})
        self.assertNotEqual(out.get('permissionDecision'), 'deny')

    def test_subagent_bypasses_state_gate_but_not_doc_gate(self):
        # No state file at all for this session -> a main-agent edit would
        # hit the WF_CLASSIFY block, but a spawned agent must reach ONLY the
        # doc gate, never the state-based block.
        os.remove(os.path.join(self.cwd, '.serena', 'swe-state',
                                f'{self.SESSION}.state'))
        result = self._run_main(
            {'file_path': os.path.join(self.cwd, 'src/other/thing.py')},
            extra={'agent_id': 'sub-1'})
        out = result.get('hookSpecificOutput', {})
        self.assertNotEqual(out.get('permissionDecision'), 'deny')

    # --- main agent: doc gate applies in addition to sweep/drift ----------

    def test_main_agent_matched_path_without_docread_denied(self):
        self._write_feature_doc('feature/FEATURE_WIDGET', ['src/widget/**/*.py'])
        result = self._run_main(
            {'file_path': os.path.join(self.cwd, 'src/widget/core.py')})
        out = result.get('hookSpecificOutput', {})
        self.assertEqual(out.get('permissionDecision'), 'deny')
        self.assertIn('[doc-gate]', out.get('permissionDecisionReason', ''))

    def test_main_agent_matched_path_with_docread_allowed(self):
        self._write_feature_doc('feature/FEATURE_WIDGET', ['src/widget/**/*.py'])
        self._write_stream([
            {'type': 'docread', 'name': 'feature/FEATURE_WIDGET'},
        ])
        result = self._run_main(
            {'file_path': os.path.join(self.cwd, 'src/widget/core.py')})
        out = result.get('hookSpecificOutput', {})
        self.assertNotEqual(out.get('permissionDecision'), 'deny')

    def test_main_agent_unmatched_path_allowed(self):
        result = self._run_main(
            {'file_path': os.path.join(self.cwd, 'src/other/thing.py')})
        out = result.get('hookSpecificOutput', {})
        self.assertNotEqual(out.get('permissionDecision'), 'deny')

    def test_main_agent_wm_write_exempt_from_doc_gate(self):
        self._write_feature_doc('feature/FEATURE_WIDGET', ['**/*'])
        result = self._run_main(
            {'file_path': os.path.join(
                self.cwd, '.serena', 'memories', f'WM_{self.SESSION}.md')})
        out = result.get('hookSpecificOutput', {})
        self.assertNotEqual(out.get('permissionDecision'), 'deny')


if __name__ == '__main__':
    unittest.main()
