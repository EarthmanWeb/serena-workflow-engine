"""Tests for swe_hooks.core.orphan_reaper.

Covers parsing canned `ps -axo pid=,ppid=,uid=,command=` output to find
orphaned VS-Code-extension Claude Code sessions (ppid == 1, executable under
a `.vscode*/.cursor` extension's native-binary/claude path, owned by the
current user) — and that the kill step signals SIGTERM only for matches.

Stdlib unittest only; no real processes are ever touched (kill is injected).
"""
import os
import signal
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_core, reset_caches  # noqa: E402

orphan_reaper = import_core("swe_hooks.core.orphan_reaper")


MY_UID = 501
OTHER_UID = 502

VSCODE_ORPHAN_CMD = (
    "/Users/webdev/.vscode/extensions/anthropic.claude-code-1.2.3-darwin-arm64/"
    "resources/native-binary/claude --output-format stream-json --verbose "
    "--input-format stream-json"
)
VSCODE_INSIDERS_ORPHAN_CMD = (
    "/Users/webdev/.vscode-insiders/extensions/anthropic.claude-code-1.2.3-darwin-arm64/"
    "resources/native-binary/claude --output-format stream-json --verbose"
)
CURSOR_ORPHAN_CMD = (
    "/Users/webdev/.cursor/extensions/anthropic.claude-code-1.2.3-darwin-arm64/"
    "resources/native-binary/claude --output-format stream-json --verbose"
)

CANNED_PS_OUTPUT = "\n".join([
    # header-like leading whitespace variance is realistic for `ps`
    f"  100   1  {MY_UID}  {VSCODE_ORPHAN_CMD}",           # 1. orphaned VS Code claude -> MATCH
    f"  101  555  {MY_UID}  {VSCODE_ORPHAN_CMD}",          # 2. parented VS Code claude -> no match (ppid != 1)
    f"  102    1  {MY_UID}  /usr/local/bin/claude --resume",  # 3. terminal claude w/ ppid 1 -> no match (not vscode path)
    f"  103    1  {OTHER_UID}  {VSCODE_ORPHAN_CMD}",       # 4. another user's orphan -> no match (uid)
    f"  104    1  {MY_UID}  /sbin/launchd",                # 5. unrelated ppid-1 process -> no match
])


class ParsePsOutputTests(unittest.TestCase):
    def test_selects_only_the_orphaned_vscode_claude(self):
        matches = orphan_reaper.find_orphaned_vscode_claude_sessions(
            CANNED_PS_OUTPUT, my_uid=MY_UID
        )
        self.assertEqual([m["pid"] for m in matches], [100])

    def test_matches_vscode_insiders_extension_dir(self):
        ps_out = f"  200   1  {MY_UID}  {VSCODE_INSIDERS_ORPHAN_CMD}"
        matches = orphan_reaper.find_orphaned_vscode_claude_sessions(ps_out, my_uid=MY_UID)
        self.assertEqual([m["pid"] for m in matches], [200])

    def test_matches_cursor_extension_dir(self):
        ps_out = f"  300   1  {MY_UID}  {CURSOR_ORPHAN_CMD}"
        matches = orphan_reaper.find_orphaned_vscode_claude_sessions(ps_out, my_uid=MY_UID)
        self.assertEqual([m["pid"] for m in matches], [300])

    def test_ignores_parented_vscode_claude(self):
        ps_out = f"  101  555  {MY_UID}  {VSCODE_ORPHAN_CMD}"
        matches = orphan_reaper.find_orphaned_vscode_claude_sessions(ps_out, my_uid=MY_UID)
        self.assertEqual(matches, [])

    def test_ignores_terminal_claude_even_with_ppid_1(self):
        ps_out = f"  102    1  {MY_UID}  /usr/local/bin/claude --resume"
        matches = orphan_reaper.find_orphaned_vscode_claude_sessions(ps_out, my_uid=MY_UID)
        self.assertEqual(matches, [])

    def test_ignores_other_users_orphan(self):
        ps_out = f"  103    1  {OTHER_UID}  {VSCODE_ORPHAN_CMD}"
        matches = orphan_reaper.find_orphaned_vscode_claude_sessions(ps_out, my_uid=MY_UID)
        self.assertEqual(matches, [])

    def test_ignores_unrelated_ppid_one_process(self):
        ps_out = f"  104    1  {MY_UID}  /sbin/launchd"
        matches = orphan_reaper.find_orphaned_vscode_claude_sessions(ps_out, my_uid=MY_UID)
        self.assertEqual(matches, [])

    def test_never_matches_own_pid(self):
        ps_out = f"  100   1  {MY_UID}  {VSCODE_ORPHAN_CMD}"
        matches = orphan_reaper.find_orphaned_vscode_claude_sessions(
            ps_out, my_uid=MY_UID, exclude_pids={100}
        )
        self.assertEqual(matches, [])

    def test_empty_input_returns_empty(self):
        self.assertEqual(
            orphan_reaper.find_orphaned_vscode_claude_sessions("", my_uid=MY_UID), []
        )

    def test_malformed_lines_are_skipped_not_fatal(self):
        ps_out = "\n".join([
            "garbage line with no columns",
            f"  100   1  {MY_UID}  {VSCODE_ORPHAN_CMD}",
            "1 2",  # too few fields
        ])
        matches = orphan_reaper.find_orphaned_vscode_claude_sessions(ps_out, my_uid=MY_UID)
        self.assertEqual([m["pid"] for m in matches], [100])


class KillMatchesTests(unittest.TestCase):
    def test_sigterm_sent_to_each_match(self):
        calls = []

        def fake_kill(pid, sig):
            calls.append((pid, sig))

        matches = [{"pid": 100, "ppid": 1, "uid": MY_UID, "command": VSCODE_ORPHAN_CMD}]
        reaped = orphan_reaper.kill_matches(matches, kill_fn=fake_kill, grace_seconds=0)
        self.assertEqual(calls, [(100, signal.SIGTERM)])
        self.assertEqual(reaped, [100])

    def test_no_matches_sends_no_signals(self):
        calls = []
        reaped = orphan_reaper.kill_matches([], kill_fn=lambda p, s: calls.append((p, s)))
        self.assertEqual(calls, [])
        self.assertEqual(reaped, [])

    def test_kill_errors_are_swallowed_per_pid(self):
        def fake_kill(pid, sig):
            if pid == 100:
                raise ProcessLookupError()

        matches = [
            {"pid": 100, "ppid": 1, "uid": MY_UID, "command": VSCODE_ORPHAN_CMD},
            {"pid": 200, "ppid": 1, "uid": MY_UID, "command": VSCODE_ORPHAN_CMD},
        ]
        reaped = orphan_reaper.kill_matches(matches, kill_fn=fake_kill, grace_seconds=0)
        # 100 failed to signal (already gone) -> not reported reaped; 200 succeeded.
        self.assertEqual(reaped, [200])

    def test_escalates_to_sigkill_after_grace_period_if_still_alive(self):
        calls = []

        def fake_kill(pid, sig):
            calls.append((pid, sig))

        def fake_alive(pid):
            return True  # still alive after SIGTERM -> must escalate

        matches = [{"pid": 100, "ppid": 1, "uid": MY_UID, "command": VSCODE_ORPHAN_CMD}]
        orphan_reaper.kill_matches(
            matches, kill_fn=fake_kill, grace_seconds=0, is_alive_fn=fake_alive, sleep_fn=lambda s: None
        )
        self.assertIn((100, signal.SIGTERM), calls)
        self.assertIn((100, signal.SIGKILL), calls)

    def test_no_escalation_when_process_exits_before_grace_expires(self):
        calls = []

        def fake_kill(pid, sig):
            calls.append((pid, sig))

        def fake_alive(pid):
            return False  # gone after SIGTERM -> no escalation

        matches = [{"pid": 100, "ppid": 1, "uid": MY_UID, "command": VSCODE_ORPHAN_CMD}]
        orphan_reaper.kill_matches(
            matches, kill_fn=fake_kill, grace_seconds=0, is_alive_fn=fake_alive, sleep_fn=lambda s: None
        )
        self.assertEqual(calls, [(100, signal.SIGTERM)])


class ReapOrphansTests(unittest.TestCase):
    """End-to-end pure-function wiring: ps text -> matches -> kill, via
    injected fetch/kill functions so no real process is ever touched."""

    def test_reap_orphans_dry_run_lists_without_killing(self):
        calls = []
        result = orphan_reaper.reap_orphans(
            ps_output_fn=lambda: CANNED_PS_OUTPUT,
            my_uid=MY_UID,
            kill_fn=lambda p, s: calls.append((p, s)),
            dry_run=True,
        )
        self.assertEqual(calls, [])
        self.assertEqual([m["pid"] for m in result["matches"]], [100])
        self.assertEqual(result["reaped"], [])

    def test_reap_orphans_apply_kills_matches(self):
        calls = []
        result = orphan_reaper.reap_orphans(
            ps_output_fn=lambda: CANNED_PS_OUTPUT,
            my_uid=MY_UID,
            kill_fn=lambda p, s: calls.append((p, s)),
            dry_run=False,
            grace_seconds=0,
        )
        self.assertEqual(calls, [(100, signal.SIGTERM)])
        self.assertEqual(result["reaped"], [100])

    def test_reap_orphans_errors_in_ps_fetch_are_reported_not_raised(self):
        def boom():
            raise OSError("ps not found")

        result = orphan_reaper.reap_orphans(
            ps_output_fn=boom, my_uid=MY_UID, kill_fn=lambda p, s: None, dry_run=True
        )
        self.assertIn("error", result)
        self.assertEqual(result["matches"], [])
        self.assertEqual(result["reaped"], [])


if __name__ == "__main__":
    unittest.main()
