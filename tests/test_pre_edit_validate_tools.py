"""Tests for target-path extraction across tool shapes in
hooks/pre/swe_pre_edit_validate.py.

Defect under test: commit 91f3c70 added NotebookEdit, MultiEdit and Serena
create_text_file/replace_lines/delete_lines/insert_at_line/replace_in_files
to this hook's hooks.json matcher, but target extraction read only
file_path then relative_path — NotebookEdit sends its target under
notebook_path, so NotebookEdit targets resolved to '' and every gate
(sweep, doc) silently skipped them.

Fix: `_extract_target_path` (file_path, then notebook_path, then
relative_path) is the single source of truth, used by both
`_sweep_gate_verdict` and `_doc_gate_target`/`_doc_gate_block`.

This file exercises main() end-to-end for each tool shape named in the
defect report: NotebookEdit (notebook_path), MultiEdit (file_path), Serena
create_text_file/replace_lines/delete_lines/insert_at_line (relative_path),
and replace_in_files with a directory relative_path (doc-gate skipped,
sweep sentinel still enforced).

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


class TestExtractTargetPathPure(unittest.TestCase):
    """_extract_target_path(tool_input) — pure precedence function."""

    def test_file_path_wins_over_notebook_path(self):
        self.assertEqual(
            edit_mod._extract_target_path(
                {'file_path': 'a.py', 'notebook_path': 'b.ipynb'}),
            'a.py')

    def test_notebook_path_used_when_no_file_path(self):
        self.assertEqual(
            edit_mod._extract_target_path({'notebook_path': 'nb.ipynb'}),
            'nb.ipynb')

    def test_notebook_path_wins_over_relative_path(self):
        self.assertEqual(
            edit_mod._extract_target_path(
                {'notebook_path': 'nb.ipynb', 'relative_path': 'x.py'}),
            'nb.ipynb')

    def test_relative_path_used_when_no_file_or_notebook_path(self):
        self.assertEqual(
            edit_mod._extract_target_path({'relative_path': 'x.py'}), 'x.py')

    def test_empty_when_none_present(self):
        self.assertEqual(edit_mod._extract_target_path({}), '')
        self.assertEqual(edit_mod._extract_target_path(None), '')

    def test_doc_gate_target_delegates(self):
        self.assertEqual(
            edit_mod._doc_gate_target({'notebook_path': 'nb.ipynb'}),
            'nb.ipynb')


class TestToolShapesMainIntegration(unittest.TestCase):
    """main() end-to-end across tool shapes: NotebookEdit, MultiEdit, Serena
    symbolic edit tools, replace_in_files-with-directory."""

    SESSION = 'f00dc0de'

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
        self._orig_edit_mod_root = edit_mod.get_project_root
        edit_mod.get_project_root = lambda: self.cwd

        state_dir = os.path.join(self.cwd, '.serena', 'swe-state')
        os.makedirs(state_dir, exist_ok=True)
        with open(os.path.join(state_dir, f'{self.SESSION}.state'), 'w') as f:
            json.dump({'current_state': 'WF_EXECUTE'}, f)
        self.sweep_sentinel = os.path.join(
            self.streams_dir, f'.sweep_feature_{self.SESSION}')
        open(self.sweep_sentinel, 'w').close()
        open(os.path.join(self.streams_dir, f'.init_{self.SESSION}'), 'w').close()
        open(os.path.join(self.streams_dir, f'{self.SESSION}.jsonl'), 'a').close()

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

    def _run_main(self, tool_name, tool_input, extra=None):
        import io
        payload = {
            'tool_name': tool_name,
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

    # --- NotebookEdit: notebook_path -----------------------------------

    def test_notebook_edit_denied_when_governing_memory_unread(self):
        self._write_feature_doc('feature/FEATURE_NB', ['notebooks/**/*.ipynb'])
        target = os.path.join(self.cwd, 'notebooks', 'analysis.ipynb')
        result = self._run_main(
            'NotebookEdit', {'notebook_path': target, 'new_source': 'x = 1'})
        out = result.get('hookSpecificOutput', {})
        self.assertEqual(out.get('permissionDecision'), 'deny')
        self.assertIn('[doc-gate]', out.get('permissionDecisionReason', ''))
        self.assertIn('feature/FEATURE_NB', out.get('permissionDecisionReason', ''))

    def test_notebook_edit_allowed_after_memory_read(self):
        self._write_feature_doc('feature/FEATURE_NB', ['notebooks/**/*.ipynb'])
        self._write_stream([
            {'type': 'docread', 'name': 'feature/FEATURE_NB'},
        ])
        target = os.path.join(self.cwd, 'notebooks', 'analysis.ipynb')
        result = self._run_main(
            'NotebookEdit', {'notebook_path': target, 'new_source': 'x = 1'})
        out = result.get('hookSpecificOutput', {})
        self.assertNotEqual(out.get('permissionDecision'), 'deny')

    # --- MultiEdit: file_path --------------------------------------------

    def test_multiedit_denied_when_governing_memory_unread(self):
        self._write_feature_doc('feature/FEATURE_WIDGET', ['src/widget/**/*.py'])
        target = os.path.join(self.cwd, 'src', 'widget', 'core.py')
        result = self._run_main(
            'MultiEdit', {'file_path': target, 'edits': [
                {'old_string': 'a', 'new_string': 'b'}]})
        out = result.get('hookSpecificOutput', {})
        self.assertEqual(out.get('permissionDecision'), 'deny')
        self.assertIn('[doc-gate]', out.get('permissionDecisionReason', ''))

    def test_multiedit_allowed_after_memory_read(self):
        self._write_feature_doc('feature/FEATURE_WIDGET', ['src/widget/**/*.py'])
        self._write_stream([
            {'type': 'docread', 'name': 'feature/FEATURE_WIDGET'},
        ])
        target = os.path.join(self.cwd, 'src', 'widget', 'core.py')
        result = self._run_main(
            'MultiEdit', {'file_path': target, 'edits': [
                {'old_string': 'a', 'new_string': 'b'}]})
        out = result.get('hookSpecificOutput', {})
        self.assertNotEqual(out.get('permissionDecision'), 'deny')

    # --- Serena symbolic edit tools: relative_path ------------------------

    def test_create_text_file_denied_when_governing_memory_unread(self):
        self._write_feature_doc('feature/FEATURE_WIDGET', ['src/widget/**/*.py'])
        result = self._run_main(
            'mcp__plugin_swe_serena__create_text_file',
            {'relative_path': 'src/widget/new.py', 'content': 'x = 1'})
        out = result.get('hookSpecificOutput', {})
        self.assertEqual(out.get('permissionDecision'), 'deny')
        self.assertIn('[doc-gate]', out.get('permissionDecisionReason', ''))

    def test_create_text_file_allowed_after_memory_read(self):
        self._write_feature_doc('feature/FEATURE_WIDGET', ['src/widget/**/*.py'])
        self._write_stream([
            {'type': 'docread', 'name': 'feature/FEATURE_WIDGET'},
        ])
        result = self._run_main(
            'mcp__plugin_swe_serena__create_text_file',
            {'relative_path': 'src/widget/new.py', 'content': 'x = 1'})
        out = result.get('hookSpecificOutput', {})
        self.assertNotEqual(out.get('permissionDecision'), 'deny')

    def test_replace_lines_denied_when_governing_memory_unread(self):
        self._write_feature_doc('feature/FEATURE_WIDGET', ['src/widget/**/*.py'])
        result = self._run_main(
            'mcp__plugin_swe_serena__replace_lines',
            {'relative_path': 'src/widget/core.py', 'start_line': 1,
             'end_line': 2, 'content': 'x = 1'})
        out = result.get('hookSpecificOutput', {})
        self.assertEqual(out.get('permissionDecision'), 'deny')
        self.assertIn('[doc-gate]', out.get('permissionDecisionReason', ''))

    def test_replace_lines_allowed_after_memory_read(self):
        self._write_feature_doc('feature/FEATURE_WIDGET', ['src/widget/**/*.py'])
        self._write_stream([
            {'type': 'docread', 'name': 'feature/FEATURE_WIDGET'},
        ])
        result = self._run_main(
            'mcp__plugin_swe_serena__replace_lines',
            {'relative_path': 'src/widget/core.py', 'start_line': 1,
             'end_line': 2, 'content': 'x = 1'})
        out = result.get('hookSpecificOutput', {})
        self.assertNotEqual(out.get('permissionDecision'), 'deny')

    def test_delete_lines_denied_when_governing_memory_unread(self):
        self._write_feature_doc('feature/FEATURE_WIDGET', ['src/widget/**/*.py'])
        result = self._run_main(
            'mcp__plugin_swe_serena__delete_lines',
            {'relative_path': 'src/widget/core.py', 'start_line': 1,
             'end_line': 2})
        out = result.get('hookSpecificOutput', {})
        self.assertEqual(out.get('permissionDecision'), 'deny')
        self.assertIn('[doc-gate]', out.get('permissionDecisionReason', ''))

    def test_delete_lines_allowed_after_memory_read(self):
        self._write_feature_doc('feature/FEATURE_WIDGET', ['src/widget/**/*.py'])
        self._write_stream([
            {'type': 'docread', 'name': 'feature/FEATURE_WIDGET'},
        ])
        result = self._run_main(
            'mcp__plugin_swe_serena__delete_lines',
            {'relative_path': 'src/widget/core.py', 'start_line': 1,
             'end_line': 2})
        out = result.get('hookSpecificOutput', {})
        self.assertNotEqual(out.get('permissionDecision'), 'deny')

    def test_insert_at_line_denied_when_governing_memory_unread(self):
        self._write_feature_doc('feature/FEATURE_WIDGET', ['src/widget/**/*.py'])
        result = self._run_main(
            'mcp__plugin_swe_serena__insert_at_line',
            {'relative_path': 'src/widget/core.py', 'line': 1,
             'content': 'x = 1'})
        out = result.get('hookSpecificOutput', {})
        self.assertEqual(out.get('permissionDecision'), 'deny')
        self.assertIn('[doc-gate]', out.get('permissionDecisionReason', ''))

    def test_insert_at_line_allowed_after_memory_read(self):
        self._write_feature_doc('feature/FEATURE_WIDGET', ['src/widget/**/*.py'])
        self._write_stream([
            {'type': 'docread', 'name': 'feature/FEATURE_WIDGET'},
        ])
        result = self._run_main(
            'mcp__plugin_swe_serena__insert_at_line',
            {'relative_path': 'src/widget/core.py', 'line': 1,
             'content': 'x = 1'})
        out = result.get('hookSpecificOutput', {})
        self.assertNotEqual(out.get('permissionDecision'), 'deny')

    # --- replace_in_files with a directory relative_path -------------------

    def test_replace_in_files_directory_skips_doc_gate_but_enforces_sweep(self):
        # Doc-gate is skipped for a directory target (no single file to
        # compute required docs for) — but the sweep sentinel is still
        # required, same as any other edit in an execution state.
        self._write_feature_doc('feature/FEATURE_WIDGET', ['src/widget/**/*.py'])
        target_dir = os.path.join(self.cwd, 'src', 'widget')
        os.makedirs(target_dir, exist_ok=True)
        os.remove(self.sweep_sentinel)
        result = self._run_main(
            'mcp__plugin_swe_serena__replace_in_files',
            {'relative_path': target_dir, 'needle': 'a', 'repl': 'b'})
        out = result.get('hookSpecificOutput', {})
        self.assertEqual(out.get('permissionDecision'), 'deny')
        self.assertIn('SWEEP GATE', out.get('permissionDecisionReason', ''))

    def test_replace_in_files_directory_allowed_with_sweep_no_doc_gate(self):
        # Governing memory for src/widget/** is deliberately left UNREAD —
        # if the doc-gate were (incorrectly) applied to the directory
        # target, this would deny. It must not.
        self._write_feature_doc('feature/FEATURE_WIDGET', ['src/widget/**/*.py'])
        target_dir = os.path.join(self.cwd, 'src', 'widget')
        os.makedirs(target_dir, exist_ok=True)
        result = self._run_main(
            'mcp__plugin_swe_serena__replace_in_files',
            {'relative_path': target_dir, 'needle': 'a', 'repl': 'b'})
        out = result.get('hookSpecificOutput', {})
        self.assertNotEqual(out.get('permissionDecision'), 'deny')


if __name__ == '__main__':
    unittest.main()
