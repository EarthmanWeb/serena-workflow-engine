"""Tests for hooks/swe_hooks/core/memory_fs.py and
hooks/pre/swe_pre_memory_fs_gate.py — DENY filesystem access to Serena memory
stores, redirect to Serena memory MCP tools.

Stdlib unittest only, offline/deterministic. Modules loaded via
tests/_hookutil.py (import_core for the core module, import_hook for the
gate).
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_hook, import_core  # noqa: E402

memory_fs = import_core("swe_hooks.core.memory_fs")
gate_mod = import_hook("pre/swe_pre_memory_fs_gate")


# ---------------------------------------------------------------------------
# is_memory_store_path
# ---------------------------------------------------------------------------
class TestIsMemoryStorePath(unittest.TestCase):
    def test_empty_path_is_false(self):
        self.assertFalse(memory_fs.is_memory_store_path('', '/x/proj'))
        self.assertFalse(memory_fs.is_memory_store_path(None, '/x/proj'))

    def test_serena_memory_singular_matches(self):
        self.assertTrue(memory_fs.is_memory_store_path(
            '/x/proj/.serena/memory/ref/A.md', '/x/proj'))

    def test_serena_memories_plural_matches(self):
        self.assertTrue(memory_fs.is_memory_store_path(
            '/x/proj/.serena/memories/WM_abc.md'.replace('WM_abc', 'x'), '/x/proj'))

    def test_memory_paths_conf_does_not_match(self):
        self.assertFalse(memory_fs.is_memory_store_path(
            '/x/proj/.serena/memory-paths.conf', '/x/proj'))

    def test_relative_path_joined_onto_cwd(self):
        self.assertTrue(memory_fs.is_memory_store_path(
            '.serena/memory/a.md', '/x/proj'))

    def test_wm_basename_exempt(self):
        self.assertFalse(memory_fs.is_memory_store_path(
            '/x/proj/.serena/memories/WM_abc12345.md', '/x/proj'))

    def test_glob_token_in_path_still_matches(self):
        self.assertTrue(memory_fs.is_memory_store_path(
            '/x/proj/.serena/memory/ref/*.md', '/x/proj'))

    def test_plugin_source_memories_tree_not_a_store(self):
        self.assertFalse(memory_fs.is_memory_store_path(
            '/x/proj/memories/wf/WF_INIT.md', '/x/proj'))

    def test_non_memory_path_is_false(self):
        self.assertFalse(memory_fs.is_memory_store_path(
            '/x/proj/hooks/pre/swe_pre_edit_validate.py', '/x/proj'))

    def test_symlink_target_detected_via_realpath(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        proj = os.path.join(tmp.name, 'proj')
        real_memory = os.path.join(proj, '.serena', 'memory')
        os.makedirs(real_memory)
        encoded_dir = os.path.join(
            tmp.name, 'home', '.claude', 'projects', 'enc')
        os.makedirs(encoded_dir)
        symlink_path = os.path.join(encoded_dir, 'memory')
        os.symlink(real_memory, symlink_path)
        target = os.path.join(symlink_path, 'ref', 'A.md')
        self.assertTrue(memory_fs.is_memory_store_path(target, tmp.name))


# ---------------------------------------------------------------------------
# bash_memory_access — DENY cases
# ---------------------------------------------------------------------------
class TestBashMemoryAccessDeny(unittest.TestCase):
    def test_transcript_case_1_cd_then_grep_pipeline(self):
        cmd = ('cd /x/proj/.serena/memory && grep -rlnE '
               '"environment-switcher|sps_admin_bar" . | head; echo ---; '
               'grep -rliE "admin.?bar" --include=*.md . | head -30')
        self.assertTrue(memory_fs.bash_memory_access(cmd, '/x/proj'))

    def test_transcript_case_2_cwd_inside_memory(self):
        cmd = ('grep -rliE "admin.?bar" . | head -30; echo ---; '
               'head -15 index/INDEX_X.md')
        self.assertTrue(
            memory_fs.bash_memory_access(cmd, '/x/proj/.serena/memory'))

    def test_transcript_case_3_grep_then_sed(self):
        cmd = 'grep -l "keywords:" ref/*.md | head -3; sed -n \'1,20p\' ref/REF_X.md'
        self.assertTrue(
            memory_fs.bash_memory_access(cmd, '/x/proj/.serena/memory'))

    def test_cat_memory_md(self):
        self.assertTrue(memory_fs.bash_memory_access(
            'cat .serena/memory/MEMORY.md', '/x/proj'))

    def test_awk_brace_expansion_operand(self):
        self.assertTrue(memory_fs.bash_memory_access(
            'awk \'/^name:/\' .serena/memory/{dom,ref}/*.md', '/x/proj'))

    def test_ls_memories_plural(self):
        self.assertTrue(memory_fs.bash_memory_access(
            'ls .serena/memories/', '/x/proj'))

    def test_redirect_append_into_memory(self):
        self.assertTrue(memory_fs.bash_memory_access(
            'echo x >> .serena/memory/a.md', '/x/proj'))

    def test_sed_inplace_memory(self):
        self.assertTrue(memory_fs.bash_memory_access(
            "sed -i 's/a/b/' .serena/memory/a.md", '/x/proj'))

    def test_python_inline_c_reading_memory(self):
        self.assertTrue(memory_fs.bash_memory_access(
            "python3 -c \"open('.serena/memory/a.md').read()\"", '/x/proj'))

    def test_python_heredoc_reading_memory(self):
        cmd = ("python3 - <<'EOF'\n"
               "print(open('.serena/memory/a.md').read())\n"
               "EOF")
        self.assertTrue(memory_fs.bash_memory_access(cmd, '/x/proj'))

    def test_perl_inplace_memory(self):
        self.assertTrue(memory_fs.bash_memory_access(
            "perl -pi -e 's/a/b/' .serena/memory/a.md", '/x/proj'))


class TestBashMemoryAccessAllow(unittest.TestCase):
    def test_grep_source_for_the_literal_string_allowed(self):
        self.assertFalse(memory_fs.bash_memory_access(
            'grep -rn ".serena/memory" hooks/', '/x/proj'))

    def test_grep_source_for_partial_string_allowed(self):
        self.assertFalse(memory_fs.bash_memory_access(
            r'grep -rn "\.serena/memor" hooks/', '/x/proj'))

    def test_script_file_run_with_root_flag_allowed(self):
        self.assertFalse(memory_fs.bash_memory_access(
            'python3 scripts/memory-size-audit.py --root .serena/memory',
            '/x/proj'))

    def test_git_add_and_commit_allowed(self):
        self.assertFalse(memory_fs.bash_memory_access(
            'git add .serena/memory/x.md && git commit -m x', '/x/proj'))

    def test_cat_memory_paths_conf_allowed(self):
        self.assertFalse(memory_fs.bash_memory_access(
            'cat .serena/memory-paths.conf', '/x/proj'))

    def test_mkdir_memory_dir_allowed(self):
        self.assertFalse(memory_fs.bash_memory_access(
            'mkdir -p .serena/memory', '/x/proj'))

    def test_ls_unrelated_dir_allowed(self):
        self.assertFalse(memory_fs.bash_memory_access('ls hooks', '/x/proj'))

    def test_cp_between_env_vars_allowed(self):
        self.assertFalse(memory_fs.bash_memory_access(
            'cp "$AUTO_MEMORY_DIR"/x.md "$SERENA_MEMORY_DIR"/', '/x/proj'))


# ---------------------------------------------------------------------------
# tool_memory_access — non-Bash tools
# ---------------------------------------------------------------------------
class TestToolMemoryAccessNonBash(unittest.TestCase):
    def test_read_memory_store_file_denied(self):
        self.assertTrue(memory_fs.tool_memory_access(
            'Read', {'file_path': '/x/proj/.serena/memory/ref/A.md'}, '/x/proj'))

    def test_read_plugin_source_memories_allowed(self):
        self.assertFalse(memory_fs.tool_memory_access(
            'Read', {'file_path': '/x/proj/memories/wf/WF_INIT.md'}, '/x/proj'))

    def test_read_wm_file_allowed(self):
        self.assertFalse(memory_fs.tool_memory_access(
            'Read', {'file_path': '/x/proj/.serena/memories/WM_abc12345.md'},
            '/x/proj'))

    def test_grep_path_memory_store_denied(self):
        self.assertTrue(memory_fs.tool_memory_access(
            'Grep', {'path': '.serena/memory'}, '/x/proj'))

    def test_grep_glob_joined_onto_path_denied(self):
        self.assertTrue(memory_fs.tool_memory_access(
            'Grep', {'path': '.', 'glob': '.serena/memory/**'}, '/x/proj'))

    def test_glob_pattern_denied(self):
        self.assertTrue(memory_fs.tool_memory_access(
            'Glob', {'pattern': '**/.serena/memory/**/*.md'}, '/x/proj'))

    def test_read_through_real_symlink_denied(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        proj = os.path.join(tmp.name, 'proj')
        real_memory = os.path.join(proj, '.serena', 'memory')
        os.makedirs(real_memory)
        encoded_dir = os.path.join(
            tmp.name, 'home', '.claude', 'projects', 'enc')
        os.makedirs(encoded_dir)
        symlink_path = os.path.join(encoded_dir, 'memory')
        os.symlink(real_memory, symlink_path)
        target = os.path.join(symlink_path, 'ref', 'A.md')
        self.assertTrue(memory_fs.tool_memory_access(
            'Read', {'file_path': target}, tmp.name))

    def test_other_tool_always_false(self):
        self.assertFalse(memory_fs.tool_memory_access(
            'TodoWrite', {'file_path': '.serena/memory/a.md'}, '/x/proj'))


# ---------------------------------------------------------------------------
# Gate: exemptions
# ---------------------------------------------------------------------------
class TestGateExemptions(unittest.TestCase):
    def test_is_init_agent_exact_type(self):
        self.assertTrue(gate_mod._is_init_agent({'agent_type': 'swe-init-agent'}))

    def test_is_init_agent_qualified_type(self):
        self.assertTrue(gate_mod._is_init_agent(
            {'agent_type': 'swe:swe-init-agent'}))

    def test_is_init_agent_false_for_other_agent(self):
        self.assertFalse(gate_mod._is_init_agent({'agent_type': 'Explore'}))

    def test_is_init_agent_false_for_main_agent(self):
        self.assertFalse(gate_mod._is_init_agent({}))


class TestGateMainExemptions(unittest.TestCase):
    def _run_main(self, payload, setup_state):
        import contextlib
        import io
        orig = (gate_mod.read_stdin_safe, gate_mod.resolve_setup_state)
        gate_mod.read_stdin_safe = lambda **kw: payload
        gate_mod.resolve_setup_state = lambda root: setup_state
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                with self.assertRaises(SystemExit):
                    gate_mod.main()
        finally:
            gate_mod.read_stdin_safe, gate_mod.resolve_setup_state = orig
        return json.loads(buf.getvalue())

    def test_setup_not_initialized_allows(self):
        result = self._run_main(
            {'tool_name': 'Bash',
             'tool_input': {'command': 'cat .serena/memory/MEMORY.md'},
             'cwd': '/x/proj'},
            {'initialized': False, 'bypassed': False})
        self.assertEqual(result, {})

    def test_setup_bypassed_allows(self):
        result = self._run_main(
            {'tool_name': 'Bash',
             'tool_input': {'command': 'cat .serena/memory/MEMORY.md'},
             'cwd': '/x/proj'},
            {'initialized': True, 'bypassed': True})
        self.assertEqual(result, {})

    def test_init_agent_allows(self):
        result = self._run_main(
            {'tool_name': 'Bash',
             'tool_input': {'command': 'cat .serena/memory/MEMORY.md'},
             'cwd': '/x/proj', 'agent_type': 'swe-init-agent'},
            {'initialized': True, 'bypassed': False})
        self.assertEqual(result, {})

    def test_non_memory_call_allows_without_setup_check(self):
        result = self._run_main(
            {'tool_name': 'Bash', 'tool_input': {'command': 'ls hooks'},
             'cwd': '/x/proj'},
            {'initialized': True, 'bypassed': False})
        self.assertEqual(result, {})

    def test_managed_project_denies(self):
        result = self._run_main(
            {'tool_name': 'Bash',
             'tool_input': {'command': 'cat .serena/memory/MEMORY.md'},
             'cwd': '/x/proj'},
            {'initialized': True, 'bypassed': False})
        out = result['hookSpecificOutput']
        self.assertEqual(out['permissionDecision'], 'deny')
        self.assertIn('[memory-fs]', out['permissionDecisionReason'])


# ---------------------------------------------------------------------------
# Gate: deny message content
# ---------------------------------------------------------------------------
class TestDenyMessage(unittest.TestCase):
    def test_derives_memory_name_for_single_file_target(self):
        msg = gate_mod.build_deny_message(
            'Read', {'file_path': '/x/proj/.serena/memory/ref/REF_A.md'},
            '/x/proj')
        self.assertIn('read_memory(memory_name="ref/REF_A")', msg)

    def test_falls_back_to_placeholder_for_bash(self):
        msg = gate_mod.build_deny_message(
            'Bash', {'command': 'cat .serena/memory/MEMORY.md'}, '/x/proj')
        self.assertIn('read_memory(memory_name="<topic>/<NAME>")', msg)

    def test_mentions_list_find_write_and_wm_tools(self):
        msg = gate_mod.build_deny_message('Bash', {'command': 'ls hooks'}, '/x/proj')
        self.assertIn('list_memories', msg)
        self.assertIn('search_memories_by_name', msg)
        self.assertIn('search_memories_by_front_matter', msg)
        self.assertIn('write_memory', msg)
        self.assertIn('edit_memory', msg)
        self.assertIn('swe_wm_read', msg)
        self.assertIn('reconnect Serena', msg)


if __name__ == '__main__':
    unittest.main()
