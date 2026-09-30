"""Regression test for the WF_RESEARCH -> WF_CLASSIFY read-driven deadlock.

Before the readBackward fix, is_forward_read_transition() refused ANY
backward-rank read (WF_RESEARCH is rank 2, WF_CLASSIFY is rank 1), so a
session stuck in WF_RESEARCH could read wf/WF_CLASSIFY over and over and
never actually transition — the FSM was deadlocked even though
WF_RESEARCH.transitions declares needs_implementation -> WF_CLASSIFY as a
valid, matrix-backed exit.

(a) drives hooks/post/swe_post_read_state.py as a REAL subprocess with a
    PostToolUse payload for read_memory("wf/WF_CLASSIFY"), against a tmp
    project seeded at WF_RESEARCH, and asserts the .state file and WM both
    show the completed transition.
(b) drives hooks/swe_hooks/tools/set_state.py as a real subprocess (the
    documented `python3 set_state.py <sid> <state> [--force]` CLI), with and
    without --force.

Both processes run against an isolated tmp project via CLAUDE_PROJECT_DIR —
never the real .serena.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POST_READ_STATE_HOOK = os.path.join(PLUGIN_ROOT, "hooks", "post", "swe_post_read_state.py")
SET_STATE_TOOL = os.path.join(PLUGIN_ROOT, "hooks", "swe_hooks", "tools", "set_state.py")

SID = "abcd1234"
# transcript_path whose UUID's first 8 hex chars are SID — extract_session_id
# takes uuid_match.group(1)[:8] from a full UUID, so the leading 8 hex chars
# of the UUID itself (not just any prefix of the path) must equal SID.
TRANSCRIPT_PATH = f"/home/user/.claude/projects/proj/{SID}-19fa-41d2-8238-13269b9b3ca0.jsonl"


class _TmpProjectBase(unittest.TestCase):
    """Real filesystem tmp project, isolated via CLAUDE_PROJECT_DIR — the
    subprocess resolves its project root the same way a real hook invocation
    would (env var), never touching the real .serena tree."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, ".git"), exist_ok=True)
        self.memories_dir = os.path.join(self.root, ".serena", "memories")
        os.makedirs(self.memories_dir, exist_ok=True)
        self.state_dir = os.path.join(self.root, ".serena", "swe-state")
        os.makedirs(self.state_dir, exist_ok=True)

        self.env = dict(os.environ)
        self.env["CLAUDE_PROJECT_DIR"] = self.root
        self.env.pop("SWE_SESSION_ID", None)
        self.env.pop("CLAUDE_SESSION_ID", None)

    def tearDown(self):
        self.tmp.cleanup()

    def _wm_path(self):
        return os.path.join(self.memories_dir, f"WM_{SID}.md")

    def _write_wm(self, current_state):
        with open(self._wm_path(), "w") as f:
            f.write(
                f"# Working Memory: Session {SID}\n\n"
                "## Current Task\n**[IN_PROGRESS]**: research\n\n"
                "## Workflow Context\n"
                f"**Current State**: {current_state}\n"
                f"**Session ID**: {SID}\n\n"
                "## Progress\n- started\n"
            )

    def _state_path(self, sid=SID):
        return os.path.join(self.state_dir, f"{sid}.state")

    def _write_state(self, current_state, prev_state=None):
        data = {"current_state": current_state, "session_id": SID}
        if prev_state is not None:
            data["prev_state"] = prev_state
        with open(self._state_path(), "w") as f:
            json.dump(data, f)

    def _read_state(self):
        with open(self._state_path()) as f:
            return json.load(f)

    def _read_wm(self):
        with open(self._wm_path()) as f:
            return f.read()


class ReadDrivenDeadlockIntegrationTest(_TmpProjectBase):
    """(a): the exact deadlock scenario, via the real post-read hook process."""

    def setUp(self):
        super().setUp()
        self._write_wm("WF_RESEARCH")
        self._write_state("WF_RESEARCH", prev_state="WF_CLASSIFY")

    def _run_post_read_hook(self, memory_name):
        payload = {
            "cwd": self.root,
            "tool_name": "mcp__plugin_swe_serena__read_memory",
            "tool_input": {"memory_name": memory_name},
            "tool_result": "",
            "transcript_path": TRANSCRIPT_PATH,
        }
        result = subprocess.run(
            [sys.executable, POST_READ_STATE_HOOK],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=self.env,
            timeout=30,
        )
        return result

    def test_reading_wf_classify_from_research_completes_the_declared_exit(self):
        result = self._run_post_read_hook("wf/WF_CLASSIFY")
        self.assertEqual(result.returncode, 0, result.stderr)

        # Hook always emits valid JSON to stdout, exit 0 (never exit 1).
        output = json.loads(result.stdout)
        self.assertIn("hookSpecificOutput", output)

        state = self._read_state()
        self.assertEqual(state["current_state"], "WF_CLASSIFY")
        self.assertEqual(state["prev_state"], "WF_RESEARCH")

        wm_content = self._read_wm()
        self.assertIn("### Transitions", wm_content)
        self.assertIn("WF_RESEARCH → WF_CLASSIFY", wm_content)

    def test_second_read_is_a_no_op_not_a_crash(self):
        # First read completes the transition to WF_CLASSIFY; reading
        # wf/WF_CLASSIFY again from WF_CLASSIFY itself (same-state) must not
        # error or oscillate.
        self._run_post_read_hook("wf/WF_CLASSIFY")
        result = self._run_post_read_hook("wf/WF_CLASSIFY")
        self.assertEqual(result.returncode, 0, result.stderr)
        state = self._read_state()
        self.assertEqual(state["current_state"], "WF_CLASSIFY")


class SetStateCliSubprocessTest(_TmpProjectBase):
    """(b): the documented `python3 set_state.py <sid> <state> [--force]` CLI."""

    def setUp(self):
        super().setUp()
        self._write_wm("WF_RESEARCH")
        self._write_state("WF_RESEARCH", prev_state="WF_CLASSIFY")

    def _run_set_state(self, target_state, force=False):
        cmd = [sys.executable, SET_STATE_TOOL, SID, target_state]
        if force:
            cmd.append("--force")
        return subprocess.run(cmd, capture_output=True, text=True, env=self.env, timeout=30)

    def test_declared_transition_without_force_succeeds(self):
        result = self._run_set_state("WF_CLASSIFY")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output["success"], output)
        self.assertEqual(output["previous_state"], "WF_RESEARCH")
        self.assertEqual(output["new_state"], "WF_CLASSIFY")
        self.assertFalse(output["forced"])

        state = self._read_state()
        self.assertEqual(state["current_state"], "WF_CLASSIFY")
        self.assertEqual(state["prev_state"], "WF_RESEARCH")

    def test_undeclared_transition_without_force_fails(self):
        # WF_RESEARCH -> WF_EXECUTE is not a declared matrix edge.
        result = self._run_set_state("WF_EXECUTE")
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertFalse(output["success"])
        self.assertIn("error", output)

        state = self._read_state()
        self.assertEqual(state["current_state"], "WF_RESEARCH")  # unchanged

    def test_undeclared_transition_with_force_succeeds(self):
        result = self._run_set_state("WF_EXECUTE", force=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output["success"], output)
        self.assertTrue(output["forced"])
        self.assertEqual(output["new_state"], "WF_EXECUTE")

        state = self._read_state()
        self.assertEqual(state["current_state"], "WF_EXECUTE")

    def test_subflow_target_rejected_via_cli(self):
        result = self._run_set_state("WF_INIT", force=True)
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertFalse(output["success"])
        self.assertIn("subflow", output["error"])


if __name__ == "__main__":
    unittest.main()
