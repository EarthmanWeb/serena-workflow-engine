"""Tests for hooks/session/swe_session_start.py's outdated-daemon reaper.

Targets the pure helpers extracted from _reap_outdated_daemons:
  _parse_ps, _find_session_root, _is_descendant, _select_outdated_pids, _vtuple

Focus: the session-exemption fix. Before the fix, _reap_outdated_daemons killed
ANY outdated-versioned SWE daemon process line, including ones this very
session had just launched from the old cache path (pre-self-update). The fix
walks the ppid chain to find "the Claude process" for this session and never
reaps anything descended from it, while still reaping outdated daemons
belonging to OTHER sessions.

Stdlib unittest only; deterministic and fully offline — no real `ps` call,
no real processes killed.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_hook  # noqa: E402

mod = import_hook("session/swe_session_start")


def old_serena(pid, ppid, version="1.2.80"):
    return (pid, ppid,
            f"uv run python /Users/x/.claude/plugins/cache/EarthmanWeb/swe/"
            f"{version}/scripts/serena_memory_patch.py --project /x")


def new_serena(pid, ppid, version="1.2.81"):
    return old_serena(pid, ppid, version)


class ParsePsTests(unittest.TestCase):
    def test_parses_pid_ppid_command(self):
        out = "  100   1  /bin/launchd\n  200 100  /usr/bin/zsh -l\n"
        procs = mod._parse_ps(out)
        self.assertEqual(procs[100], (1, '/bin/launchd'))
        self.assertEqual(procs[200], (100, '/usr/bin/zsh -l'))

    def test_command_with_multiple_spaces_preserved_as_one_field(self):
        out = "300 200 uv run python /a/b/serena_memory_patch.py --project /x\n"
        procs = mod._parse_ps(out)
        self.assertIn('serena_memory_patch.py', procs[300][1])

    def test_blank_lines_skipped(self):
        out = "\n\n100 1 foo\n\n"
        procs = mod._parse_ps(out)
        self.assertEqual(len(procs), 1)

    def test_malformed_line_skipped(self):
        out = "not-a-pid ppid command\n100 1 ok\n"
        procs = mod._parse_ps(out)
        self.assertEqual(list(procs.keys()), [100])

    def test_command_missing_defaults_empty(self):
        out = "100 1\n"
        procs = mod._parse_ps(out)
        self.assertEqual(procs[100], (1, ''))

    def test_empty_output_returns_empty_dict(self):
        self.assertEqual(mod._parse_ps(""), {})


class FindSessionRootTests(unittest.TestCase):
    def test_walks_through_shell_and_python_wrappers_to_claude(self):
        # serena server(4000, python3) -> zsh(3000) -> claude(2000) -> launchd(1000)
        # The walk starts at 3000 (the server's ppid, i.e. os.getppid() from
        # inside the server process) and must climb past the zsh wrapper to
        # reach claude (2000).
        procs = {
            4000: (3000, "python3 /a/serena_memory_patch.py"),
            3000: (2000, "/bin/zsh -c 'python3 ...'"),
            2000: (1000, "/usr/local/bin/claude"),
            1000: (1, "/sbin/launchd"),
        }
        root = mod._find_session_root(procs, 3000)
        self.assertEqual(root, 2000)

    def test_start_pid_direct_parent_is_claude(self):
        procs = {
            500: (100, "/usr/local/bin/claude"),
            100: (1, "/sbin/launchd"),
        }
        root = mod._find_session_root(procs, 500)
        self.assertEqual(root, 100)

    def test_falls_back_to_start_pid_when_chain_exhausted(self):
        # start_pid's ppid is 1 (reached top) -> fallback to start_pid itself
        procs = {
            10: (1, "/sbin/launchd"),
        }
        root = mod._find_session_root(procs, 10)
        self.assertEqual(root, 10)

    def test_falls_back_when_ppid_missing_from_procs(self):
        procs = {
            10: (999, "/bin/zsh"),  # 999 not in procs
        }
        root = mod._find_session_root(procs, 10)
        self.assertEqual(root, 10)

    def test_pythonw_and_python3_variants_treated_as_wrapper(self):
        # start(50, python3.11) -> parent(40, python) -> parent(30, claude)
        procs = {
            50: (40, "python3.11 /a/b.py"),
            40: (30, "/usr/bin/python"),
            30: (20, "/usr/local/bin/claude"),
            20: (1, "/sbin/launchd"),
        }
        root = mod._find_session_root(procs, 50)
        self.assertEqual(root, 30)


class IsDescendantTests(unittest.TestCase):
    def test_direct_child_is_descendant(self):
        procs = {500: (100, "cmd")}
        self.assertTrue(mod._is_descendant(procs, 500, 100))

    def test_pid_equal_to_root_is_descendant(self):
        procs = {100: (1, "cmd")}
        self.assertTrue(mod._is_descendant(procs, 100, 100))

    def test_multi_hop_ancestor_is_descendant(self):
        procs = {700: (600, "a"), 600: (500, "b"), 500: (100, "c")}
        self.assertTrue(mod._is_descendant(procs, 700, 100))

    def test_unrelated_process_not_descendant(self):
        procs = {700: (600, "a"), 600: (1, "b"), 999: (1, "other-session-claude")}
        self.assertFalse(mod._is_descendant(procs, 700, 999))

    def test_cycle_does_not_hang_and_returns_false(self):
        # Self-referential / cyclic ppid map: 10->20, 20->10
        procs = {10: (20, "a"), 20: (10, "b")}
        self.assertFalse(mod._is_descendant(procs, 10, 999))

    def test_self_referential_ppid_treated_as_cycle(self):
        procs = {10: (10, "weird")}
        self.assertFalse(mod._is_descendant(procs, 10, 999))

    def test_missing_pid_in_map_returns_false(self):
        procs = {}
        self.assertFalse(mod._is_descendant(procs, 42, 1))


class SelectOutdatedPidsTests(unittest.TestCase):
    def test_outdated_daemon_under_session_root_is_not_selected(self):
        # This session's own freshly-launched (old-version) serena server:
        # server(4000) -> python3(3000) -> claude(2000, the session root)
        pid, ppid, command = old_serena(4000, 3000)
        procs = {
            4000: (3000, command),
            3000: (2000, "/usr/bin/python3"),
            2000: (1, "/usr/local/bin/claude"),
        }
        selected = mod._select_outdated_pids(procs, "1.2.81", session_root=2000, my_pid=99999)
        self.assertEqual(selected, [])

    def test_outdated_daemon_under_different_session_is_selected(self):
        # A DIFFERENT claude session's stale daemon (root=8000, not our session)
        pid, ppid, command = old_serena(4000, 3000)
        procs = {
            4000: (3000, command),
            3000: (8000, "/usr/local/bin/claude"),  # other session
            8000: (1, "/sbin/launchd"),
        }
        selected = mod._select_outdated_pids(procs, "1.2.81", session_root=2000, my_pid=99999)
        self.assertEqual(selected, [4000])

    def test_current_version_not_selected(self):
        pid, ppid, command = old_serena(4000, 3000, version="1.2.81")
        procs = {4000: (3000, command), 3000: (1, "other")}
        selected = mod._select_outdated_pids(procs, "1.2.81", session_root=999, my_pid=1)
        self.assertEqual(selected, [])

    def test_newer_version_not_selected(self):
        pid, ppid, command = old_serena(4000, 3000, version="1.3.0")
        procs = {4000: (3000, command), 3000: (1, "other")}
        selected = mod._select_outdated_pids(procs, "1.2.81", session_root=999, my_pid=1)
        self.assertEqual(selected, [])

    def test_non_swe_process_not_selected(self):
        procs = {
            5000: (1, "/usr/bin/python3 /some/other/1.0.0/scripts/foo.py"),
        }
        selected = mod._select_outdated_pids(procs, "1.2.81", session_root=999, my_pid=1)
        self.assertEqual(selected, [])

    def test_my_pid_never_selected_even_if_outdated_and_unrelated(self):
        pid, ppid, command = old_serena(4000, 3000)
        procs = {4000: (3000, command), 3000: (1, "other")}
        selected = mod._select_outdated_pids(procs, "1.2.81", session_root=999, my_pid=4000)
        self.assertEqual(selected, [])

    def test_command_without_version_pattern_not_selected(self):
        procs = {
            4000: (1, "swe_hooks something with 'swe' but no versioned cache path"),
        }
        selected = mod._select_outdated_pids(procs, "1.2.81", session_root=999, my_pid=1)
        self.assertEqual(selected, [])

    def test_multiple_daemons_mixed_session_exemption(self):
        own_pid, own_ppid, own_cmd = old_serena(4000, 3000)
        other_pid, other_ppid, other_cmd = old_serena(5000, 6000)
        procs = {
            4000: (3000, own_cmd),
            3000: (2000, "python3"),
            2000: (1, "claude"),  # session_root
            5000: (6000, other_cmd),
            6000: (1, "claude"),  # different session
        }
        selected = mod._select_outdated_pids(procs, "1.2.81", session_root=2000, my_pid=99999)
        self.assertEqual(selected, [5000])


class VtupleTests(unittest.TestCase):
    def test_parses_dotted_version(self):
        self.assertEqual(mod._vtuple("1.2.81"), (1, 2, 81))

    def test_malformed_returns_zero_tuple(self):
        self.assertEqual(mod._vtuple("not-a-version"), (0,))

    def test_none_returns_zero_tuple(self):
        self.assertEqual(mod._vtuple(None), (0,))

    def test_ordering(self):
        self.assertLess(mod._vtuple("1.2.80"), mod._vtuple("1.2.81"))


class ReapOutdatedDaemonsIntegrationTests(unittest.TestCase):
    """Exercise _reap_outdated_daemons end-to-end with ps/kill/config mocked,
    to confirm the session exemption holds through the full call path."""

    def setUp(self):
        self._orig_run = mod.subprocess.run
        self._orig_kill = mod.os.kill
        self._orig_getppid = mod.os.getppid

    def tearDown(self):
        mod.subprocess.run = self._orig_run
        mod.os.kill = self._orig_kill
        mod.os.getppid = self._orig_getppid

    def test_own_session_daemon_survives_reap_after_self_update(self):
        # Simulate: this session's serena server (4000) launched from the OLD
        # version, descended from claude(2000) via python3(3000). A stale
        # daemon from a different session (5000, under claude 6000) should
        # still be reaped.
        pid, ppid, own_cmd = old_serena(4000, 3000)
        _, _, other_cmd = old_serena(5000, 6000)
        ps_output = (
            "4000 3000 " + own_cmd + "\n"
            "3000 2000 python3\n"
            "2000    1 /usr/local/bin/claude\n"
            "5000 6000 " + other_cmd + "\n"
            "6000    1 /usr/local/bin/claude\n"
        )

        class FakeResult:
            stdout = ps_output

        def fake_run(cmd, **kwargs):
            return FakeResult()

        killed = []

        def fake_kill(pid_, sig):
            killed.append(pid_)

        mod.subprocess.run = fake_run
        mod.os.kill = fake_kill
        mod.os.getppid = lambda: 3000  # our own parent is the python3 wrapper

        import swe_hooks.core.config as config_mod
        orig_resolve = config_mod.resolve_installed_plugin
        config_mod.resolve_installed_plugin = lambda: (None, "1.2.81")
        try:
            reaped = mod._reap_outdated_daemons()
        finally:
            config_mod.resolve_installed_plugin = orig_resolve

        self.assertNotIn(4000, reaped)
        self.assertIn(5000, reaped)
        self.assertEqual(killed, [5000])

    def test_no_installed_version_returns_empty_without_calling_ps(self):
        import swe_hooks.core.config as config_mod
        orig_resolve = config_mod.resolve_installed_plugin
        config_mod.resolve_installed_plugin = lambda: (None, None)
        calls = []
        mod.subprocess.run = lambda *a, **k: calls.append(1) or None
        try:
            reaped = mod._reap_outdated_daemons()
        finally:
            config_mod.resolve_installed_plugin = orig_resolve
        self.assertEqual(reaped, [])
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
