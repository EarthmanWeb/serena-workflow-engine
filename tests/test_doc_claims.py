"""Tests for hooks/swe_hooks/core/doc_claims.py and its two hook consumers.

Covers:
  - parse_claims / pending_claims — row grammar (→ and ->), section
    isolation, corrected true values, malformed-row tolerance.
  - find_wm_claims — WM location under .serena/memories/, absent = [].
  - claim_in_args — exact-containment matcher (C5).
  - near_match — dumb substitution matcher (C6): compound near-miss and
    prefix-stem cases, exact-use and unrelated non-matches.
  - stream_has_event_key — the per-session dedupe primitive.
  - post/swe_post_doc_claims main() — substitution attachment, per-(claim,
    used) dedupe, corrected-row exclusion, silent no-ledger path.
  - post/swe_post_tool_failure C5 branch — is_claim_bearing_tool, the
    reconciliation attachment, per-claim dedupe.

Stdlib unittest only.
"""
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_core, import_hook, reset_caches  # noqa: E402

dc = import_core("swe_hooks.core.doc_claims")
claims_hook_mod = import_hook("post/swe_post_doc_claims")
failure_mod = import_hook("post/swe_post_tool_failure")


WM_LEDGER = """# WM_abc12345

## Workflow Context
**Current State**: WF_EXECUTE

## Doc Claims Used

- mem:feature/FEATURE_WPMS → sps-wpms.local → pending
- mem:ref/REF_DEPLOY -> /srv/deploy.sh -> confirmed
- mem:dom/DOM_CACHE → redis:6379 → corrected → redis:6380

## Next Steps
- mem:not/A_CLAIM → outside-section → pending
"""


# ---------------------------------------------------------------------------
# parse_claims / pending_claims
# ---------------------------------------------------------------------------
class TestParseClaims(unittest.TestCase):
    def test_parses_all_rows_in_section_only(self):
        claims = dc.parse_claims(WM_LEDGER)
        self.assertEqual(len(claims), 3)
        self.assertEqual([c["name"] for c in claims],
                         ["feature/FEATURE_WPMS", "ref/REF_DEPLOY", "dom/DOM_CACHE"])

    def test_unicode_arrow_row_fields(self):
        claim = dc.parse_claims(WM_LEDGER)[0]
        self.assertEqual(claim["claim"], "sps-wpms.local")
        self.assertEqual(claim["status"], "pending")
        self.assertIsNone(claim["true_value"])

    def test_ascii_arrow_row_tolerated(self):
        claim = dc.parse_claims(WM_LEDGER)[1]
        self.assertEqual(claim["claim"], "/srv/deploy.sh")
        self.assertEqual(claim["status"], "confirmed")
        self.assertIsNone(claim["true_value"])

    def test_corrected_row_carries_true_value(self):
        claim = dc.parse_claims(WM_LEDGER)[2]
        self.assertEqual(claim["status"], "corrected")
        self.assertEqual(claim["true_value"], "redis:6380")

    def test_rows_outside_section_ignored(self):
        names = [c["name"] for c in dc.parse_claims(WM_LEDGER)]
        self.assertNotIn("not/A_CLAIM", names)

    def test_section_at_eof_parses(self):
        content = "# WM\n\n## Doc Claims Used\n- mem:ref/REF_X → v=1 → pending\n"
        self.assertEqual(len(dc.parse_claims(content)), 1)

    def test_malformed_rows_skipped(self):
        content = (
            "## Doc Claims Used\n"
            "- mem:ref/REF_A → only-two-parts\n"          # no status
            "- not-a-mem-row → x → pending\n"             # no mem: lead
            "- mem:ref/REF_B → x → bogus-status\n"        # unknown status
            "- mem:ref/REF_C → keep → confirmed\n"        # valid
        )
        claims = dc.parse_claims(content)
        self.assertEqual([c["name"] for c in claims], ["ref/REF_C"])

    def test_star_bullets_accepted(self):
        content = "## Doc Claims Used\n* mem:ref/REF_X → v=1 → pending\n"
        self.assertEqual(len(dc.parse_claims(content)), 1)

    def test_empty_and_none_content(self):
        self.assertEqual(dc.parse_claims(""), [])
        self.assertEqual(dc.parse_claims(None), [])

    def test_pending_claims_filters_status(self):
        pending = dc.pending_claims(WM_LEDGER)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["name"], "feature/FEATURE_WPMS")

    def test_blocking_claims_includes_valueless_corrected(self):
        content = (
            "## Doc Claims Used\n"
            "- mem:ref/REF_A → url=a.local → pending\n"
            "- mem:ref/REF_B → url=b.local → confirmed\n"
            "- mem:ref/REF_C → url=c.local → corrected\n"
            "- mem:ref/REF_D → url=d.local → corrected → url=dd.local\n")
        blocked = dc.blocking_claims(content)
        self.assertEqual([c["name"] for c in blocked],
                         ["ref/REF_A", "ref/REF_C"])


# ---------------------------------------------------------------------------
# find_wm_claims
# ---------------------------------------------------------------------------
class TestFindWmClaims(unittest.TestCase):
    SESSION = "abc12345"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write_wm(self, content=WM_LEDGER):
        mem = os.path.join(self.cwd, ".serena", "memories")
        os.makedirs(mem, exist_ok=True)
        with open(os.path.join(mem, f"WM_{self.SESSION}.md"), "w") as f:
            f.write(content)

    def test_reads_and_parses_ledger(self):
        self._write_wm()
        claims = dc.find_wm_claims(self.cwd, self.SESSION)
        self.assertEqual(len(claims), 3)

    def test_absent_wm_returns_empty(self):
        self.assertEqual(dc.find_wm_claims(self.cwd, self.SESSION), [])

    def test_none_session_returns_empty(self):
        self._write_wm()
        self.assertEqual(dc.find_wm_claims(self.cwd, None), [])


# ---------------------------------------------------------------------------
# claim_in_args
# ---------------------------------------------------------------------------
class TestClaimInArgs(unittest.TestCase):
    CLAIMS = dc.parse_claims(WM_LEDGER)

    def test_first_matching_claim_returned(self):
        hit = dc.claim_in_args(self.CLAIMS, "curl -I http://sps-wpms.local/")
        self.assertEqual(hit["name"], "feature/FEATURE_WPMS")

    def test_claim_inside_json_args_matches(self):
        text = json.dumps({"command": "bash /srv/deploy.sh --dry-run"})
        hit = dc.claim_in_args(self.CLAIMS, text)
        self.assertEqual(hit["name"], "ref/REF_DEPLOY")

    def test_no_match_returns_none(self):
        self.assertIsNone(dc.claim_in_args(self.CLAIMS, "ls -la /tmp"))

    def test_empty_claims_and_args(self):
        self.assertIsNone(dc.claim_in_args([], "anything"))
        self.assertIsNone(dc.claim_in_args(self.CLAIMS, ""))
        self.assertIsNone(dc.claim_in_args(None, None))


# ---------------------------------------------------------------------------
# near_match
# ---------------------------------------------------------------------------
class TestNearMatch(unittest.TestCase):
    HOST_CLAIM = [{"name": "feature/FEATURE_WPMS", "claim": "sps-wpms.local",
                   "status": "pending", "true_value": None}]
    PATH_CLAIM = [{"name": "ref/REF_DEPLOY", "claim": "/srv/deploy.sh",
                   "status": "pending", "true_value": None}]

    def test_compound_substitution_detected(self):
        # The canonical case: documented host vs a longer sibling host.
        hit = dc.near_match(self.HOST_CLAIM,
                            "curl -I http://sps-wpms-master.local/")
        self.assertIsNotNone(hit)
        claim, used = hit
        self.assertEqual(claim["name"], "feature/FEATURE_WPMS")
        self.assertIn("sps-wpms-master.local", used)

    def test_prefix_stem_substitution_detected(self):
        hit = dc.near_match(self.PATH_CLAIM, "bash /srv/deployment.sh")
        self.assertIsNotNone(hit)
        _claim, used = hit
        self.assertIn("deployment", used)

    def test_exact_use_is_not_a_substitution(self):
        self.assertIsNone(dc.near_match(
            self.HOST_CLAIM, "curl -I http://sps-wpms.local/health"))

    def test_unrelated_command_no_match(self):
        self.assertIsNone(dc.near_match(self.HOST_CLAIM, "git status && ls -la"))

    def test_empty_inputs_no_match(self):
        self.assertIsNone(dc.near_match([], "curl x"))
        self.assertIsNone(dc.near_match(self.HOST_CLAIM, ""))
        self.assertIsNone(dc.near_match(None, None))

    def test_empty_claim_value_skipped(self):
        claims = [{"name": "ref/REF_X", "claim": "", "status": "pending",
                   "true_value": None}]
        self.assertIsNone(dc.near_match(claims, "anything at all"))


# ---------------------------------------------------------------------------
# stream_has_event_key
# ---------------------------------------------------------------------------
class TestStreamHasEventKey(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stream = os.path.join(self.tmp.name, "sess.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_present_key_found(self):
        with open(self.stream, "w") as f:
            f.write(json.dumps({"type": "claim_flag", "k": "a::b"}) + "\n")
            f.write("not json\n")
        self.assertTrue(dc.stream_has_event_key(self.stream, "claim_flag", "a::b"))

    def test_wrong_type_or_key_not_found(self):
        with open(self.stream, "w") as f:
            f.write(json.dumps({"type": "claim_flag", "k": "a::b"}) + "\n")
        self.assertFalse(dc.stream_has_event_key(self.stream, "claim_subst", "a::b"))
        self.assertFalse(dc.stream_has_event_key(self.stream, "claim_flag", "a::c"))

    def test_missing_stream_not_found(self):
        self.assertFalse(dc.stream_has_event_key(
            os.path.join(self.tmp.name, "nope.jsonl"), "claim_flag", "a::b"))


# ---------------------------------------------------------------------------
# post/swe_post_doc_claims — C6 hook main()
# ---------------------------------------------------------------------------
class TestPostDocClaimsMain(unittest.TestCase):
    SESSION = "abcd1234"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name
        self.stream = os.path.join(self.cwd, f"{self.SESSION}.jsonl")
        self._orig_stream = claims_hook_mod.get_stream_path
        claims_hook_mod.get_stream_path = lambda sid: self.stream

    def tearDown(self):
        claims_hook_mod.get_stream_path = self._orig_stream
        self.tmp.cleanup()

    def _write_wm(self, ledger):
        mem = os.path.join(self.cwd, ".serena", "memories")
        os.makedirs(mem, exist_ok=True)
        with open(os.path.join(mem, f"WM_{self.SESSION}.md"), "w") as f:
            f.write("# WM\n\n## Doc Claims Used\n" + ledger)

    def _run_main(self, command, tool_name="Bash"):
        import contextlib
        payload = {
            "tool_name": tool_name,
            "tool_input": {"command": command},
            "transcript_path":
                f"/x/{self.SESSION}-0000-0000-0000-000000000000.jsonl",
            "cwd": self.cwd,
        }
        orig = claims_hook_mod.read_stdin_safe
        claims_hook_mod.read_stdin_safe = lambda **kw: payload
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                with self.assertRaises(SystemExit):
                    claims_hook_mod.main()
        finally:
            claims_hook_mod.read_stdin_safe = orig
        return json.loads(buf.getvalue())

    def test_substitution_emits_attachment(self):
        self._write_wm("- mem:feature/FEATURE_WPMS → sps-wpms.local → pending\n")
        result = self._run_main("curl -I http://sps-wpms-master.local/")
        context = result["hookSpecificOutput"]["additionalContext"]
        self.assertIn("You substituted", context)
        self.assertIn("sps-wpms-master.local", context)
        self.assertIn("documented 'sps-wpms.local'", context)
        self.assertIn("mem:feature/FEATURE_WPMS", context)

    def test_same_pair_emitted_once_per_session(self):
        self._write_wm("- mem:feature/FEATURE_WPMS → sps-wpms.local → pending\n")
        self._run_main("curl -I http://sps-wpms-master.local/")
        second = self._run_main("curl -I http://sps-wpms-master.local/")
        self.assertEqual(second, {})
        with open(self.stream) as f:
            substs = [line for line in f if '"claim_subst"' in line]
        self.assertEqual(len(substs), 1)

    def test_exact_documented_use_silent(self):
        self._write_wm("- mem:feature/FEATURE_WPMS → sps-wpms.local → pending\n")
        self.assertEqual(self._run_main("curl -I http://sps-wpms.local/"), {})

    def test_corrected_row_exception_not_flagged(self):
        # The sanctioned exception: the ledger already corrected the claim to
        # the value being used — flagging it would punish reconciliation.
        self._write_wm("- mem:feature/FEATURE_WPMS → sps-wpms.local → "
                       "corrected → sps-wpms-master.local\n")
        self.assertEqual(self._run_main("curl -I http://sps-wpms-master.local/"), {})

    def test_no_ledger_silent(self):
        self.assertEqual(self._run_main("curl -I http://sps-wpms-master.local/"), {})

    def test_non_bash_tool_silent(self):
        self._write_wm("- mem:feature/FEATURE_WPMS → sps-wpms.local → pending\n")
        self.assertEqual(
            self._run_main("sps-wpms-master.local", tool_name="Grep"), {})


# ---------------------------------------------------------------------------
# post/swe_post_tool_failure — C5 claim reconciliation
# ---------------------------------------------------------------------------
class TestClaimBearingTool(unittest.TestCase):
    def test_bash_and_web_tools_are_claim_bearing(self):
        for name in ("Bash", "WebFetch", "WebSearch"):
            self.assertTrue(failure_mod.is_claim_bearing_tool(name), name)

    def test_browser_and_wp_cli_shaped_mcp_tools_are_claim_bearing(self):
        for name in ("mcp__playwright__browser_navigate",
                     "mcp__claude_in_chrome__navigate",
                     "mcp__wp_cli__run_command",
                     "mcp__wordpress__wp"):
            self.assertTrue(failure_mod.is_claim_bearing_tool(name), name)

    def test_other_tools_are_not(self):
        for name in ("Edit", "Grep", "Read",
                     "mcp__plugin_swe_serena__read_memory", ""):
            self.assertFalse(failure_mod.is_claim_bearing_tool(name), name)


class TestToolFailureClaimReconciliation(unittest.TestCase):
    """main() end-to-end: a failed claim-bearing call whose args contain a
    ledger claim value gets ONE reconciliation attachment per claim per
    session; the fix routes through the source memory."""

    SESSION = "cafe4321"

    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.tmp.name, ".git"), exist_ok=True)
        self._orig_env = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = self.tmp.name
        mem = os.path.join(self.tmp.name, ".serena", "memories")
        os.makedirs(mem, exist_ok=True)
        with open(os.path.join(mem, f"WM_{self.SESSION}.md"), "w") as f:
            f.write("## Doc Claims Used\n"
                    "- mem:feature/FEATURE_WPMS → sps-wpms.local → pending\n")
        self.stream_core = import_core("swe_hooks.core.stream")

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = self._orig_env
        self.tmp.cleanup()
        reset_caches()

    def _run_main(self, tool_name, tool_input, tool_error):
        from unittest import mock
        payload = {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_error": tool_error,
            "transcript_path":
                f"/x/{self.SESSION}-0000-0000-0000-000000000000.jsonl",
            "cwd": self.tmp.name,
        }
        buf = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
             mock.patch("select.select", return_value=([sys.stdin], [], [])), \
             mock.patch("sys.stdout", buf):
            try:
                failure_mod.main()
            except SystemExit:
                pass
        return json.loads(buf.getvalue() or "{}")

    def test_failed_bash_with_claim_value_emits_reconciliation(self):
        result = self._run_main(
            "Bash", {"command": "curl -I http://sps-wpms.local/"},
            "curl: (6) Could not resolve host: sps-wpms.local")
        context = result["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Failing value 'sps-wpms.local'", context)
        self.assertIn("mem:feature/FEATURE_WPMS", context)
        self.assertIn("correct the source memory", context)
        self.assertIn("Do NOT retry with a guessed substitute", context)

    def test_claim_attachment_deduped_per_session(self):
        self._run_main(
            "Bash", {"command": "curl -I http://sps-wpms.local/"},
            "Could not resolve host")
        # Different claim-bearing tool, same claim: the streak resets (no
        # flail) but the claim was already flagged — silent.
        second = self._run_main(
            "WebFetch", {"url": "http://sps-wpms.local/"},
            "getaddrinfo ENOTFOUND")
        self.assertEqual(second, {})
        stream_path = self.stream_core.get_stream_path(self.SESSION)
        with open(stream_path) as f:
            flags = [line for line in f if '"claim_flag"' in line]
        self.assertEqual(len(flags), 1)

    def test_failure_without_claim_value_stays_silent(self):
        result = self._run_main(
            "Bash", {"command": "curl -I http://other-host.example/"},
            "Could not resolve host")
        self.assertEqual(result, {})

    def test_non_claim_bearing_tool_untouched(self):
        result = self._run_main(
            "Edit", {"file_path": "/x/sps-wpms.local.conf"}, "no such file")
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
