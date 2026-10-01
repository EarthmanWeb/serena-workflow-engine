"""Tests for the Bash-write-as-edit gate in hooks/pre/swe_pre_edit_validate.py.

Targets:
  - collect_values_session (hooks/swe_hooks/core/stream.py) — session-scoped
    (not task-scoped) doc-gate reads.
  - _in_project_bash_targets / _bash_write_gate_verdict / main() Bash branch —
    a Bash command that writes into project source gets the FULL edit gate
    (planning-state block, sweep-sentinel requirement, doc-gate, drift hard
    block), with the same main-agent/spawned-agent exemptions as a direct
    Edit call. A Bash command with no in-project write target, or a
    non-writing command, is a silent no-op ({}).

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


class TestPreEditValidateBash(unittest.TestCase):
    SESSION = 'cafef00d'

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

        # Main-agent flows need WF_EXECUTE + sweep sentinel so the Bash gate
        # (which runs the same checks as an Edit) is actually reached.
        state_dir = os.path.join(self.cwd, '.serena', 'swe-state')
        os.makedirs(state_dir, exist_ok=True)
        with open(os.path.join(state_dir, f'{self.SESSION}.state'), 'w') as f:
            json.dump({'current_state': 'WF_EXECUTE'}, f)
        self.sweep_sentinel = os.path.join(
            self.streams_dir, f'.sweep_feature_{self.SESSION}')
        open(self.sweep_sentinel, 'w').close()
        # _sweep_gate_verdict fails open (no gate) unless the init sentinel
        # AND the session stream file both exist — create both so the sweep
        # check actually runs for the "missing sweep sentinel" test case.
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

    def _write_dev_doc(self, name):
        rel_dir, base = name.split('/')
        d = os.path.join(self.cwd, '.serena', 'memory', rel_dir)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, base + '.md'), 'w') as f:
            f.write(f'# {base}\n')

    def _write_stream(self, events):
        path = os.path.join(self.streams_dir, f'{self.SESSION}.jsonl')
        with open(path, 'w') as f:
            for e in events:
                f.write(json.dumps(e) + '\n')

    def _transcript(self):
        return f'/x/{self.SESSION}-0000-0000-0000-000000000000.jsonl'

    def _run_main(self, command, extra=None):
        import io
        payload = {
            'tool_name': 'Bash',
            'tool_input': {'command': command},
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

    # --- non-writing / out-of-project Bash: silent no-op -------------------

    def test_non_writing_ls_is_noop(self):
        result = self._run_main('ls')
        self.assertEqual(result, {})

    def test_non_writing_git_status_is_noop(self):
        result = self._run_main('git status')
        self.assertEqual(result, {})

    def test_non_writing_sed_substitution_no_inplace_is_noop(self):
        result = self._run_main("sed 's/a/b/' f")
        self.assertEqual(result, {})

    def test_write_to_tmp_is_noop(self):
        result = self._run_main('cat > /tmp/scratch.txt <<EOF\nx\nEOF')
        self.assertEqual(result, {})

    def test_write_to_serena_dir_is_noop(self):
        # Memory-store writes are handled by swe_pre_memory_fs_gate.py, not
        # this hook — must not duplicate that gate.
        target = os.path.join(self.cwd, '.serena', 'memory', 'foo.md')
        result = self._run_main(f'echo x > {target}')
        self.assertEqual(result, {})

    def test_write_to_git_dir_is_noop(self):
        target = os.path.join(self.cwd, '.git', 'hooks', 'pre-commit')
        result = self._run_main(f'echo x > {target}')
        self.assertEqual(result, {})

    # --- in-project write target: full edit gate ----------------------------

    def test_php_write_denied_when_dev_php_unread(self):
        self._write_dev_doc('dev/DEV_PHP')
        target = os.path.join(self.cwd, 'src', 'x.php')
        result = self._run_main(f'cat > {target} <<EOF\n<?php\nEOF')
        out = result.get('hookSpecificOutput', {})
        self.assertEqual(out.get('permissionDecision'), 'deny')
        reason = out.get('permissionDecisionReason', '')
        self.assertIn('[doc-gate]', reason)
        self.assertIn('treated as an edit', reason)
        self.assertIn(target, reason)

    def test_php_write_allowed_after_dev_php_read(self):
        self._write_dev_doc('dev/DEV_PHP')
        self._write_stream([
            {'type': 'docread', 'name': 'dev/DEV_PHP'},
        ])
        target = os.path.join(self.cwd, 'src', 'x.php')
        result = self._run_main(f'cat > {target} <<EOF\n<?php\nEOF')
        out = result.get('hookSpecificOutput', {})
        self.assertNotEqual(out.get('permissionDecision'), 'deny')

    def test_session_scope_read_from_earlier_task_counts(self):
        # Session-scoped doc-gate: a docread from an EARLIER task (before a
        # WF_CLASSIFY task-boundary 'state' event) still satisfies the gate
        # for a later task's Bash write — collect_values_session ignores the
        # task-boundary window collect_values_since_task_start would apply.
        self._write_dev_doc('dev/DEV_PHP')
        self._write_stream([
            {'type': 'docread', 'name': 'dev/DEV_PHP'},
            {'type': 'state', 'from_s': 'WF_DONE', 'to_s': 'WF_CLASSIFY',
             's': self.SESSION},
        ])
        target = os.path.join(self.cwd, 'src', 'y.php')
        result = self._run_main(f'cat > {target} <<EOF\n<?php\nEOF')
        out = result.get('hookSpecificOutput', {})
        self.assertNotEqual(out.get('permissionDecision'), 'deny')

    def test_bash_write_in_planning_state_denied(self):
        state_dir = os.path.join(self.cwd, '.serena', 'swe-state')
        with open(os.path.join(state_dir, f'{self.SESSION}.state'), 'w') as f:
            json.dump({'current_state': 'WF_CLASSIFY'}, f)
        target = os.path.join(self.cwd, 'src', 'x.py')
        result = self._run_main(f'echo x > {target}')
        out = result.get('hookSpecificOutput', {})
        self.assertEqual(out.get('permissionDecision'), 'deny')

    def test_bash_write_without_sweep_sentinel_denied(self):
        os.remove(self.sweep_sentinel)
        target = os.path.join(self.cwd, 'src', 'x.py')
        result = self._run_main(f'echo x > {target}')
        out = result.get('hookSpecificOutput', {})
        self.assertEqual(out.get('permissionDecision'), 'deny')
        self.assertIn('SWEEP GATE', out.get('permissionDecisionReason', ''))

    def test_spawned_agent_bash_write_exempt(self):
        # Spawned agents are FULLY exempt from edit validation (same as a
        # direct Edit call) — resolved before the Bash branch is reached.
        os.remove(self.sweep_sentinel)  # would deny a main-agent write
        target = os.path.join(self.cwd, 'src', 'x.py')
        result = self._run_main(f'echo x > {target}', extra={'agent_id': 'sub-1'})
        out = result.get('hookSpecificOutput', {})
        self.assertNotEqual(out.get('permissionDecision'), 'deny')

    def test_unmatched_path_write_allowed(self):
        target = os.path.join(self.cwd, 'src', 'unrelated.txt')
        result = self._run_main(f'echo x > {target}')
        out = result.get('hookSpecificOutput', {})
        self.assertNotEqual(out.get('permissionDecision'), 'deny')


class TestInProjectBashTargets(unittest.TestCase):
    """_in_project_bash_targets — resolution + exclusion, pure function."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_relative_target_resolved_against_cwd(self):
        targets = edit_mod._in_project_bash_targets(
            'echo x > a.txt', self.root, self.root)
        self.assertEqual(targets, [os.path.join(self.root, 'a.txt')])

    def test_outside_root_dropped(self):
        targets = edit_mod._in_project_bash_targets(
            'echo x > /tmp/outside.txt', self.root, self.root)
        self.assertEqual(targets, [])

    def test_serena_subtree_excluded(self):
        cmd = f'echo x > {os.path.join(self.root, ".serena", "memory", "a.md")}'
        targets = edit_mod._in_project_bash_targets(cmd, self.root, self.root)
        self.assertEqual(targets, [])

    def test_git_subtree_excluded(self):
        cmd = f'echo x > {os.path.join(self.root, ".git", "config")}'
        targets = edit_mod._in_project_bash_targets(cmd, self.root, self.root)
        self.assertEqual(targets, [])

    def test_no_targets_for_non_writing_command(self):
        targets = edit_mod._in_project_bash_targets('ls -la', self.root, self.root)
        self.assertEqual(targets, [])


if __name__ == '__main__':
    unittest.main()
