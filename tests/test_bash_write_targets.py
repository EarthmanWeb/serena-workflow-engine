"""Tests for hooks/swe_hooks/core/memory_fs.py `bash_write_targets()` — the
file paths a Bash command WRITES, as written (unresolved, de-duplicated,
order of appearance). Used by a later stage to apply the full edit gate to
Bash writes into project source.

Stdlib unittest only, offline/deterministic. Module loaded via
tests/_hookutil.py (import_core).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_core  # noqa: E402

memory_fs = import_core("swe_hooks.core.memory_fs")


class TestRedirection(unittest.TestCase):
    def test_simple_overwrite_redirect(self):
        self.assertEqual(
            memory_fs.bash_write_targets('echo x > a.txt'), ['a.txt'])

    def test_append_redirect(self):
        self.assertEqual(
            memory_fs.bash_write_targets('echo x >> a.txt'), ['a.txt'])

    def test_clobber_redirect_known_limitation(self):
        # KNOWN LIMITATION (shared with bash_memory_access): BASH_PIPE_SPLIT_RE
        # (`\|(?!\|)`) splits on the lone `|` inside `>|`, since it has no
        # special-case for a clobber redirect — the shared splitter is reused
        # unchanged per task scope, so this edge case is NOT detected. The
        # bare `>|` with nothing before the pipe char still produces no
        # crash and no false target.
        self.assertEqual(memory_fs.bash_write_targets('echo x >| a.txt'), [])

    def test_fd_redirect(self):
        self.assertEqual(
            memory_fs.bash_write_targets('echo x 3> a.txt'), ['a.txt'])

    def test_and_redirect(self):
        self.assertEqual(
            memory_fs.bash_write_targets('echo x &> a.txt'), ['a.txt'])

    def test_fd_dup_excluded(self):
        self.assertEqual(memory_fs.bash_write_targets('echo x 2>&1'), [])

    def test_dev_null_excluded(self):
        self.assertEqual(memory_fs.bash_write_targets('echo x > /dev/null'), [])

    def test_dev_stdout_excluded(self):
        self.assertEqual(
            memory_fs.bash_write_targets('echo x > /dev/stdout'), [])

    def test_dev_stderr_excluded(self):
        self.assertEqual(
            memory_fs.bash_write_targets('echo x > /dev/stderr'), [])

    def test_heredoc_body_not_a_command_only_target_reported(self):
        cmd = "cat > wp-content/mu-plugins/zz-tmp-trace.php <<'EOF'\n<?php echo 1;\nEOF"
        self.assertEqual(
            memory_fs.bash_write_targets(cmd),
            ['wp-content/mu-plugins/zz-tmp-trace.php'])

    def test_heredoc_body_containing_redirect_text_not_flagged(self):
        cmd = "cat <<'EOF'\n> x\nEOF"
        self.assertEqual(memory_fs.bash_write_targets(cmd), [])

    def test_redirect_inside_quoted_script_not_flagged(self):
        self.assertEqual(memory_fs.bash_write_targets("sed 's/>/x/' f"), [])


class TestTee(unittest.TestCase):
    def test_tee_single_target(self):
        self.assertEqual(
            memory_fs.bash_write_targets('echo x | tee out.log'), ['out.log'])

    def test_tee_append_flag(self):
        self.assertEqual(
            memory_fs.bash_write_targets('echo x | tee -a out.log'), ['out.log'])

    def test_tee_multiple_targets(self):
        self.assertEqual(
            memory_fs.bash_write_targets('echo x | tee a.txt b.txt'),
            ['a.txt', 'b.txt'])


class TestSedInPlace(unittest.TestCase):
    def test_sed_without_inplace_flag_is_empty(self):
        self.assertEqual(memory_fs.bash_write_targets("sed 's/a/b/' f"), [])

    def test_sed_bare_dash_i(self):
        self.assertEqual(
            memory_fs.bash_write_targets("sed -i 's/a/b/' f.txt"), ['f.txt'])

    def test_sed_bsd_empty_suffix(self):
        self.assertEqual(
            memory_fs.bash_write_targets("sed -i '' \"s/a/b/\" f.txt"),
            ['f.txt'])

    def test_sed_glued_suffix(self):
        self.assertEqual(
            memory_fs.bash_write_targets("sed -i.bak 's/a/b/' f.txt"),
            ['f.txt'])

    def test_sed_long_flag_in_place(self):
        self.assertEqual(
            memory_fs.bash_write_targets("sed --in-place 's/a/b/' f.txt"),
            ['f.txt'])

    def test_sed_combined_flags_ei(self):
        self.assertEqual(
            memory_fs.bash_write_targets("sed -Ei 's/a/b/' f.txt"), ['f.txt'])

    def test_sed_with_e_flag_script_excluded(self):
        self.assertEqual(
            memory_fs.bash_write_targets("sed -i -e 's/a/b/' f.txt"),
            ['f.txt'])

    def test_sed_multiple_file_operands(self):
        self.assertEqual(
            memory_fs.bash_write_targets("sed -i 's/a/b/' f1.txt f2.txt"),
            ['f1.txt', 'f2.txt'])


class TestPerlInPlace(unittest.TestCase):
    def test_perl_without_inplace_is_empty(self):
        self.assertEqual(
            memory_fs.bash_write_targets("perl -e 's/a/b/' f.txt"), [])

    def test_perl_pi_flag(self):
        self.assertEqual(
            memory_fs.bash_write_targets("perl -pi -e 's/a/b/' f.txt"),
            ['f.txt'])

    def test_perl_i_with_backup_suffix(self):
        self.assertEqual(
            memory_fs.bash_write_targets("perl -i.bak -e 's/a/b/' f.txt"),
            ['f.txt'])

    def test_perl_bare_i_flag(self):
        self.assertEqual(
            memory_fs.bash_write_targets("perl -i -e 's/a/b/' f.txt"),
            ['f.txt'])


class TestCpMvInstall(unittest.TestCase):
    def test_cp_destination(self):
        self.assertEqual(
            memory_fs.bash_write_targets('cp a.txt b.txt'), ['b.txt'])

    def test_mv_destination(self):
        self.assertEqual(
            memory_fs.bash_write_targets('mv a.txt b.txt'), ['b.txt'])

    def test_install_destination(self):
        self.assertEqual(
            memory_fs.bash_write_targets('install -m 0644 a.txt /usr/local/bin/x'),
            ['/usr/local/bin/x'])

    def test_cp_target_directory_flag(self):
        self.assertEqual(
            memory_fs.bash_write_targets('cp a.txt b.txt -t dest/'), ['dest/'])

    def test_cp_target_directory_long_flag_eq(self):
        self.assertEqual(
            memory_fs.bash_write_targets('cp a.txt --target-directory=dest/'),
            ['dest/'])

    def test_cp_single_operand_no_destination(self):
        # Only one non-flag operand (no source+dest pair) -> nothing to report.
        self.assertEqual(memory_fs.bash_write_targets('cp -r a.txt'), [])


class TestTouchTruncateDd(unittest.TestCase):
    def test_touch_target(self):
        self.assertEqual(
            memory_fs.bash_write_targets('touch new.txt'), ['new.txt'])

    def test_truncate_target(self):
        self.assertEqual(
            memory_fs.bash_write_targets('truncate -s 0 new.txt'), ['new.txt'])

    def test_truncate_size_long_flag(self):
        self.assertEqual(
            memory_fs.bash_write_targets('truncate --size=0 new.txt'),
            ['new.txt'])

    def test_dd_of_target(self):
        self.assertEqual(
            memory_fs.bash_write_targets('dd if=/dev/zero of=out.img bs=1M count=1'),
            ['out.img'])

    def test_dd_without_of_is_empty(self):
        self.assertEqual(
            memory_fs.bash_write_targets('dd if=/dev/zero bs=1M count=1'), [])


class TestInlineInterpreters(unittest.TestCase):
    def test_python_c_write_open_mode_w(self):
        self.assertEqual(
            memory_fs.bash_write_targets(
                "python3 -c \"open('a.txt', 'w').write('x')\""),
            ['a.txt'])

    def test_python_c_read_only_reports_nothing(self):
        self.assertEqual(
            memory_fs.bash_write_targets(
                "python3 -c \"print(open('a.txt').read())\""),
            [])

    def test_python_c_read_mode_explicit_reports_nothing(self):
        self.assertEqual(
            memory_fs.bash_write_targets(
                "python3 -c \"open('a.txt', 'r').read()\""),
            [])

    def test_python_write_text_indicator(self):
        self.assertEqual(
            memory_fs.bash_write_targets(
                "python3 -c \"import pathlib; pathlib.Path('a.txt').write_text('x')\""),
            ['a.txt'])

    def test_python_shutil_copy_indicator_returns_both_literals(self):
        self.assertEqual(
            memory_fs.bash_write_targets(
                "python3 -c \"import shutil; shutil.copy('a.txt', 'b.txt')\""),
            ['a.txt', 'b.txt'])

    def test_node_e_write_file_indicator(self):
        self.assertEqual(
            memory_fs.bash_write_targets(
                "node -e \"require('fs').writeFile('out.js', 'x', ()=>{})\""),
            ['out.js'])

    def test_node_e_no_write_indicator_reports_nothing(self):
        self.assertEqual(
            memory_fs.bash_write_targets(
                "node -e \"console.log(require('fs').readFileSync('a.txt'))\""),
            [])

    def test_php_r_file_put_contents(self):
        self.assertEqual(
            memory_fs.bash_write_targets(
                "php -r \"file_put_contents('a.php', 'x');\""),
            ['a.php'])

    def test_php_r_fopen_read_mode_reports_nothing(self):
        self.assertEqual(
            memory_fs.bash_write_targets("php -r \"fopen('a.php', 'r');\""),
            [])

    def test_php_r_fopen_write_mode(self):
        self.assertEqual(
            memory_fs.bash_write_targets("php -r \"fopen('a.php', 'w');\""),
            ['a.php'])

    def test_ruby_e_file_write(self):
        self.assertEqual(
            memory_fs.bash_write_targets(
                "ruby -e \"File.write('a.rb', 'x')\""),
            ['a.rb'])

    def test_python_heredoc_write_indicator(self):
        cmd = ("python3 - <<'EOF'\n"
               "open('a.txt', 'w').write('x')\n"
               "EOF")
        self.assertEqual(memory_fs.bash_write_targets(cmd), ['a.txt'])

    def test_python_heredoc_no_write_indicator(self):
        cmd = ("python3 - <<'EOF'\n"
               "print(open('a.txt').read())\n"
               "EOF")
        self.assertEqual(memory_fs.bash_write_targets(cmd), [])

    def test_script_file_invocation_not_inline(self):
        self.assertEqual(
            memory_fs.bash_write_targets('python3 scripts/x.py --out a.txt'),
            [])


class TestShellCRecursion(unittest.TestCase):
    def test_bash_c_recurses_into_redirect(self):
        self.assertEqual(
            memory_fs.bash_write_targets('bash -c "cat > f.txt"'), ['f.txt'])

    def test_sh_c_recurses_into_append(self):
        self.assertEqual(
            memory_fs.bash_write_targets("sh -c 'echo hi >> log.txt'"),
            ['log.txt'])

    def test_zsh_c_recurses(self):
        self.assertEqual(
            memory_fs.bash_write_targets("zsh -c 'touch new.txt'"),
            ['new.txt'])

    def test_bash_c_no_double_count_when_quoted_script_has_semicolon(self):
        # The `;` inside the quoted -c argument must not be treated as a
        # command-group separator that corrupts the inline write detection.
        self.assertEqual(
            memory_fs.bash_write_targets(
                'bash -c "touch a.txt; touch b.txt"'),
            ['a.txt', 'b.txt'])


class TestExclusions(unittest.TestCase):
    def test_git_commands_excluded(self):
        self.assertEqual(
            memory_fs.bash_write_targets('git add f && git commit -m x'), [])

    def test_git_checkout_excluded(self):
        self.assertEqual(
            memory_fs.bash_write_targets('git checkout -- f.txt'), [])

    def test_mkdir_excluded(self):
        self.assertEqual(
            memory_fs.bash_write_targets('mkdir -p a/b/c'), [])

    def test_rm_excluded(self):
        self.assertEqual(memory_fs.bash_write_targets('rm -f a.txt'), [])

    def test_ln_excluded(self):
        self.assertEqual(
            memory_fs.bash_write_targets('ln -s a.txt b.txt'), [])

    def test_cat_read_only_excluded(self):
        self.assertEqual(memory_fs.bash_write_targets('cat f'), [])

    def test_plain_ls_excluded(self):
        self.assertEqual(memory_fs.bash_write_targets('ls -la'), [])


class TestGroupsAndPipesAndDedup(unittest.TestCase):
    def test_multiple_groups_merge_targets_in_order(self):
        self.assertEqual(
            memory_fs.bash_write_targets(
                'touch a.txt && echo x > b.txt; cp b.txt c.txt'),
            ['a.txt', 'b.txt', 'c.txt'])

    def test_duplicate_target_reported_once_first_appearance_order(self):
        self.assertEqual(
            memory_fs.bash_write_targets(
                'touch a.txt && echo x > a.txt'),
            ['a.txt'])

    def test_pipe_stage_tee_then_grep(self):
        self.assertEqual(
            memory_fs.bash_write_targets('echo x | tee -a a.txt | grep y'),
            ['a.txt'])

    def test_empty_command_returns_empty(self):
        self.assertEqual(memory_fs.bash_write_targets(''), [])

    def test_none_command_returns_empty(self):
        self.assertEqual(memory_fs.bash_write_targets(None), [])


if __name__ == '__main__':
    unittest.main()
