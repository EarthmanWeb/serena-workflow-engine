"""Tests for the response-format Stop gate + its config resolution.

Targets:
  - stop/swe_stop_response_format : pure evaluate(), prose_words(),
    is_genuine_user(), text_of(), detail_requested() (literal DETAIL: prefix
    AND natural-language triggers), strip_diagnosis_verification() (the G4
    word-budget exemption), and the banned-pattern regexes.
  - core.config.get_response_format_config : CLAUDE_PLUGIN_OPTION_* env parsing,
    defaults, and malformed-value fallback.

Stdlib unittest only; deterministic and fully offline. Most tested surfaces
are pure functions fed explicit args; the _MainHarness classes drive main()
end-to-end against a real transcript file to cover behavior main() itself is
responsible for: stop_hook_active never blocks, WF_DONE never blocks, and at
most one block per user turn (second overage warns instead).
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_hook, import_core, reset_caches  # noqa: E402

gate = import_hook("stop/swe_stop_response_format")


# ---------------------------------------------------------------------------
# text_of / is_genuine_user
# ---------------------------------------------------------------------------
class TestTextExtraction(unittest.TestCase):
    def test_text_of_string(self):
        self.assertEqual(gate.text_of("hello"), "hello")

    def test_text_of_block_list(self):
        content = [
            {"type": "text", "text": "a"},
            {"type": "tool_use", "name": "x"},
            {"type": "text", "text": "b"},
        ]
        self.assertEqual(gate.text_of(content), "a\nb")

    def test_text_of_empty(self):
        self.assertEqual(gate.text_of([]), "")


class TestIsGenuineUser(unittest.TestCase):
    def _user(self, content):
        return {"type": "user", "message": {"content": content}}

    def test_real_user_message(self):
        self.assertTrue(gate.is_genuine_user(self._user("fix the bug")))

    def test_assistant_is_not_user(self):
        self.assertFalse(gate.is_genuine_user(
            {"type": "assistant", "message": {"content": "hi"}}))

    def test_tool_result_only_is_plumbing(self):
        content = [{"type": "tool_result", "content": "output"}]
        self.assertFalse(gate.is_genuine_user(self._user(content)))

    def test_system_reminder_wrapper_is_not_user(self):
        self.assertFalse(gate.is_genuine_user(
            self._user("<system-reminder>do this</system-reminder>")))

    def test_command_wrapper_is_not_user(self):
        self.assertFalse(gate.is_genuine_user(
            self._user("<command-name>/foo</command-name>")))

    def test_empty_text_is_not_user(self):
        self.assertFalse(gate.is_genuine_user(self._user("   ")))


# ---------------------------------------------------------------------------
# prose_words
# ---------------------------------------------------------------------------
class TestProseWords(unittest.TestCase):
    def test_plain_prose_full_weight(self):
        self.assertEqual(gate.prose_words("one two three four"), 4)

    def test_code_fence_excluded(self):
        text = "before\n```\nlots of code words here inside fence\n```\nafter"
        self.assertEqual(gate.prose_words(text), 2)  # before + after

    def test_bullets_half_weight(self):
        # 4 words on a bullet line -> counted via the half bucket (4//2 == 2)
        self.assertEqual(gate.prose_words("- one two three four"), 2)

    def test_table_rows_half_weight(self):
        # "| a | b | c | d |".split() -> 9 tokens (pipes are tokens); 9//2 == 4
        self.assertEqual(gate.prose_words("| a | b | c | d |"), 4)

    def test_blank_lines_ignored(self):
        self.assertEqual(gate.prose_words("\n\nword\n\n"), 1)

    def test_file_reference_line_excluded(self):
        text = "Fixed the bug.\n/Users/dev/project/hooks/pre/swe_pre_tool_init_gate.py"
        self.assertEqual(gate.prose_words(text), 3)  # "Fixed the bug." only

    def test_bulleted_file_reference_list_excluded(self):
        text = (
            "Changed:\n"
            "- hooks/pre/swe_pre_tool_init_gate.py\n"
            "- hooks/post/swe_post_tool_failure.py: added a check\n"
        )
        self.assertEqual(gate.prose_words(text), 1)  # only "Changed:"

    def test_relative_file_reference_line_excluded(self):
        text = "tests/test_response_format_gate.py"
        self.assertEqual(gate.prose_words(text), 0)

    def test_prose_mentioning_a_word_that_looks_like_extension_still_counts(self):
        # A genuine prose sentence (no leading path-like token) still counts.
        self.assertEqual(gate.prose_words("The fix touches three files today"), 6)


class TestEndsWithQuestion(unittest.TestCase):
    def test_question_mark_ending_true(self):
        self.assertTrue(gate.ends_with_question("Should I proceed with the deploy?"))

    def test_question_with_trailing_punctuation_true(self):
        self.assertTrue(gate.ends_with_question('Should I proceed?"'))

    def test_statement_ending_false(self):
        self.assertFalse(gate.ends_with_question("Fixed the bug."))

    def test_question_mark_mid_reply_not_last_paragraph_false(self):
        self.assertFalse(gate.ends_with_question("Why did this happen? Anyway, fixed it."))

    def test_empty_text_false(self):
        self.assertFalse(gate.ends_with_question(""))
        self.assertFalse(gate.ends_with_question(None))


# ---------------------------------------------------------------------------
# regex constants
# ---------------------------------------------------------------------------
class TestDetailRequested(unittest.TestCase):
    """detail_requested(): literal DETAIL: prefix OR natural-language asks.
    The old literal-prefix-ONLY contract is gone by design (F1)."""

    def test_literal_detail_prefix_matches(self):
        for p in ("DETAIL: explain the flow", "detail - go deep", "  DETAIL:x"):
            self.assertTrue(gate.detail_requested(p), p)

    def test_each_natural_trigger_matches(self):
        for p in (
            "please review the hook changes",
            "give me a report on the failures",
            "explain the failure mode",
            "run an analysis of the stream layer",
            "a summary of the changes so far",
            "provide me with a total review of token usage",  # the A/B failure
            "walk me through the init flow",
            "why does this happen",
        ):
            self.assertTrue(gate.detail_requested(p), p)

    def test_unrelated_words_do_not_trigger(self):
        for p in ("fix the login bug", "give me the detail here",
                  "run the tests and commit", "be thorough please"):
            self.assertFalse(gate.detail_requested(p), p)

    def test_word_boundary_substrings_do_not_trigger(self):
        # "preview" contains "review", "totally" contains "total",
        # "reporting" contains "report" — none at a word boundary.
        for p in ("preview the page", "totally broken build",
                  "reporting is disabled", "the previewer crashed"):
            self.assertFalse(gate.detail_requested(p), p)

    def test_empty_text_does_not_trigger(self):
        self.assertFalse(gate.detail_requested(""))
        self.assertFalse(gate.detail_requested(None))


class TestBannedPatterns(unittest.TestCase):
    def _labels(self, text):
        return [label for pat, label in gate.BANNED_PATTERNS if pat.search(text)]

    def test_summary_heading_blocked(self):
        self.assertIn("recap/summary heading", self._labels("## Summary\nfoo"))

    def test_next_steps_heading_blocked(self):
        self.assertIn("recap/summary heading", self._labels("### Next Steps"))

    def test_bold_status_block_blocked(self):
        self.assertIn("recap/summary bold-label block", self._labels("**Status**: done"))

    def test_narrating_next_action_blocked(self):
        self.assertIn("narrating the next action", self._labels("Let me fix that"))

    def test_unsolicited_closing_offer_blocked(self):
        self.assertIn("unsolicited closing offer",
                      self._labels("Want me to also update the docs?"))

    def test_clean_result_not_flagged(self):
        self.assertEqual(self._labels("Fixed: off-by-one in the loop bound."), [])


# ---------------------------------------------------------------------------
# evaluate — the block decision
# ---------------------------------------------------------------------------
class TestEvaluate(unittest.TestCase):
    def test_terse_reply_passes(self):
        reason, _, _ = gate.evaluate(["Fixed the bug."], "fix it", 40, 600, False)
        self.assertIsNone(reason)

    def test_over_budget_blocks(self):
        essay = " ".join(["word"] * 60)
        reason, _, words = gate.evaluate([essay], "fix it", 40, 600, False)
        self.assertIsNotNone(reason)
        self.assertIn("prose words", reason)
        self.assertGreater(words, 40)

    def test_detail_prefix_raises_budget(self):
        essay = " ".join(["word"] * 60)
        reason, _, _ = gate.evaluate([essay], "DETAIL: explain everything", 40, 600, False)
        self.assertIsNone(reason)  # 60 < 600

    def test_each_natural_trigger_raises_budget(self):
        essay = " ".join(["word"] * 60)
        for prompt in (
            "please review the hook changes",
            "give me a report on the failures",
            "explain the failure mode",
            "run an analysis of the stream layer",
            "a summary of the changes so far",
            "provide me with a total review of token usage",
            "walk me through the init flow",
            "why does this happen",
        ):
            reason, _, _ = gate.evaluate([essay], prompt, 40, 600, False)
            self.assertIsNone(reason, prompt)  # 60 < 600

    def test_unrelated_prompt_keeps_terse_budget(self):
        essay = " ".join(["word"] * 60)
        for prompt in ("fix the login bug", "preview the page", "totally broken"):
            reason, _, _ = gate.evaluate([essay], prompt, 40, 600, False)
            self.assertIsNotNone(reason, prompt)

    def test_banned_pattern_blocks_even_when_terse(self):
        reason, _, _ = gate.evaluate(["## Summary\nall done"], "ok", 40, 600, False)
        self.assertIsNotNone(reason)
        self.assertIn("emitted", reason)

    def test_multi_message_cumulative_blocks(self):
        # Two messages that individually pass but together exceed the budget.
        half = " ".join(["w"] * 25)
        reason, _, words = gate.evaluate([half, half], "ok", 40, 600, False)
        self.assertIsNotNone(reason)
        self.assertGreater(words, 40)

    def test_retry_only_judges_newest_message(self):
        # First msg has the pre-block essay; newest (retry) is clean -> pass.
        essay = " ".join(["word"] * 60)
        reason, scanned, _ = gate.evaluate([essay, "Fixed."], "ok", 40, 600, True)
        self.assertIsNone(reason)
        self.assertEqual(scanned, "Fixed.")

    def test_retry_still_blocks_fresh_violation_in_newest(self):
        reason, _, _ = gate.evaluate(["clean", "## Summary\nx"], "ok", 40, 600, True)
        self.assertIsNotNone(reason)

    def test_empty_reply_passes(self):
        reason, _, _ = gate.evaluate([], "ok", 40, 600, False)
        self.assertIsNone(reason)

    def test_over_budget_reply_ending_in_question_passes(self):
        # Must-not-fire: a long reply whose final paragraph asks a question
        # is not forced into a rewrite by the length budget.
        essay = " ".join(["word"] * 60) + "\n\nWhich database migration applies first?"
        reason, _, _ = gate.evaluate([essay], "fix it", 40, 600, False)
        self.assertIsNone(reason)

    def test_over_budget_reply_not_ending_in_question_still_blocks(self):
        # Must-fire: a mid-reply question mark does not exempt an over-budget
        # reply whose final paragraph is a statement.
        essay = " ".join(["word"] * 60) + "\n\nWhy did this happen? Anyway, fixed it."
        reason, _, _ = gate.evaluate([essay], "fix it", 40, 600, False)
        self.assertIsNotNone(reason)

    def test_banned_pattern_still_blocks_even_ending_in_question(self):
        # Must-fire: the question exemption only covers the length budget, not
        # recap/scaffolding violations.
        reason, _, _ = gate.evaluate(
            ["## Summary\nall done\n\nWant me to continue?"], "ok", 40, 600, False)
        self.assertIsNotNone(reason)

    def test_duplicate_answer_blocks(self):
        # Long original + a condensed near-duplicate restatement -> block.
        original = (
            "The cache key was built from the raw request path which dropped the "
            "query string so two distinct requests collided in the store and "
            "returned each other's payload."
        )
        restated = (
            "The cache key used the raw request path and dropped the query string, "
            "so two distinct requests collided in the store and returned the wrong "
            "payload."
        )
        reason, _, _ = gate.evaluate([original, restated], "why?", 600, 600, False)
        self.assertIsNotNone(reason)
        self.assertIn("repeated", reason)

    def test_short_ack_plus_answer_passes(self):
        # A short ack under the min-words guard does not count as a duplicate.
        answer = (
            "The bug was an off-by-one in the loop bound that skipped the final "
            "element of the batch during flush."
        )
        reason, _, _ = gate.evaluate(["Done.", answer], "fix it", 600, 600, False)
        self.assertIsNone(reason)

    def test_distinct_followup_passes(self):
        # Two substantial messages that share few tokens -> not a duplicate.
        first = (
            "The parser rejected the header because the boundary token contained "
            "an unescaped semicolon inside its quoted value."
        )
        second = (
            "Separately, timezone conversion drifted by an hour whenever daylight "
            "saving flipped mid-render on the calendar widget."
        )
        reason, _, _ = gate.evaluate([first, second], "anything else?", 600, 600, False)
        self.assertIsNone(reason)

    def test_retry_with_duplicate_preblock_passes(self):
        # Duplicate lives in the pre-block text; newest msg is clean -> pass.
        dup = ("alpha beta gamma delta epsilon zeta eta theta iota kappa "
               "lambda mu nu xi omicron")
        reason, _, _ = gate.evaluate([dup, dup, "Fixed."], "ok", 600, 600, True)
        self.assertIsNone(reason)


# ---------------------------------------------------------------------------
# G4 — the DIAGNOSIS VERIFICATION block is budget-exempt
# ---------------------------------------------------------------------------
class TestDiagnosisVerificationExemption(unittest.TestCase):
    DIAG = (
        "DIAGNOSIS VERIFICATION:\n"
        "- MECHANISM: " + " ".join(["m"] * 30) + "\n"
        "- TIMING: " + " ".join(["t"] * 30) + "\n"
        "- COUNTERFACTUAL: " + " ".join(["c"] * 30) + "\n"
        "candidate — unverified: timing\n"
    )

    def test_strip_removes_block_and_unverified_line(self):
        text = "Root cause found.\n" + self.DIAG + "Fix applied."
        stripped = gate.strip_diagnosis_verification(text)
        self.assertNotIn("MECHANISM", stripped)
        self.assertNotIn("TIMING", stripped)
        self.assertNotIn("COUNTERFACTUAL", stripped)
        self.assertNotIn("unverified", stripped)
        self.assertIn("Root cause found.", stripped)
        self.assertIn("Fix applied.", stripped)

    def test_strip_ends_at_first_non_item_line(self):
        # The block runs only through CONSECUTIVE item lines; a blank line
        # ends it, and later lines survive.
        text = "DIAGNOSIS VERIFICATION:\n- MECHANISM: x\n\nafter the block"
        stripped = gate.strip_diagnosis_verification(text)
        self.assertNotIn("MECHANISM", stripped)
        self.assertIn("after the block", stripped)

    def test_item_lines_without_header_are_kept(self):
        text = "- MECHANISM: kept because no header precedes it"
        self.assertEqual(gate.strip_diagnosis_verification(text), text)

    def test_unverified_label_dropped_anywhere(self):
        text = "before\ncandidate — unverified: mechanism\nafter"
        self.assertEqual(gate.strip_diagnosis_verification(text), "before\nafter")

    def test_empty_and_none_safe(self):
        self.assertEqual(gate.strip_diagnosis_verification(""), "")
        self.assertEqual(gate.strip_diagnosis_verification(None), "")

    def test_reply_whose_only_overage_is_diagnosis_block_passes(self):
        reply = "Root cause found.\n" + self.DIAG
        # Sanity: unstripped, the reply is over the terse budget.
        self.assertGreater(gate.prose_words(reply), 40)
        reason, _, words = gate.evaluate([reply], "fix it", 40, 600, False)
        self.assertIsNone(reason)
        self.assertLess(words, 40)

    def test_same_volume_as_plain_prose_still_blocks(self):
        # Control: the same word volume OUTSIDE the diagnosis shape blocks.
        prose = " ".join(["m"] * 90)
        reason, _, _ = gate.evaluate([prose], "fix it", 40, 600, False)
        self.assertIsNotNone(reason)


# ---------------------------------------------------------------------------
# duplicate_answer / similarity / word_bag
# ---------------------------------------------------------------------------
class TestDuplicateAnswer(unittest.TestCase):
    def test_similarity_identical_is_one(self):
        bag = gate.word_bag("the quick brown fox")
        self.assertEqual(gate.similarity(bag, bag), 1.0)

    def test_similarity_disjoint_is_zero(self):
        a = gate.word_bag("alpha beta gamma")
        b = gate.word_bag("delta epsilon zeta")
        self.assertEqual(gate.similarity(a, b), 0.0)

    def test_similarity_empty_is_zero(self):
        self.assertEqual(gate.similarity(set(), gate.word_bag("word")), 0.0)
        self.assertEqual(gate.similarity(gate.word_bag("word"), set()), 0.0)

    def test_word_bag_excludes_code_fences(self):
        bag = gate.word_bag("hello\n```\nsecret code words\n```\nworld")
        self.assertEqual(bag, {"hello", "world"})

    def test_word_bag_lowercases_and_tokenizes(self):
        self.assertEqual(gate.word_bag("Foo, BAR-baz 42!"),
                         {"foo", "bar", "baz", "42"})

    def test_near_duplicate_detected(self):
        a = ("the deploy failed because the ssh host secret was stale and pointed "
             "at the old server address after the migration")
        b = ("the deploy failed because the ssh host secret was stale and pointed "
             "at an old server address following the migration")
        self.assertTrue(gate.duplicate_answer([a, b]))

    def test_short_messages_ignored(self):
        self.assertFalse(gate.duplicate_answer(["Done.", "Done."]))

    def test_distinct_messages_not_duplicate(self):
        a = ("the parser rejected the header because the boundary token had an "
             "unescaped semicolon inside its quoted value string")
        b = ("timezone conversion drifted by one hour whenever daylight saving "
             "flipped mid render inside the calendar widget component")
        self.assertFalse(gate.duplicate_answer([a, b]))


# ---------------------------------------------------------------------------
# config resolution (CLAUDE_PLUGIN_OPTION_* env)
# ---------------------------------------------------------------------------
class TestResponseFormatConfig(unittest.TestCase):
    ENV_KEYS = (
        "CLAUDE_PLUGIN_OPTION_RESPONSE_FORMAT_ENABLED",
        "CLAUDE_PLUGIN_OPTION_RESPONSE_FORMAT_TERSE_LIMIT",
        "CLAUDE_PLUGIN_OPTION_RESPONSE_FORMAT_DETAIL_LIMIT",
    )

    def setUp(self):
        reset_caches()
        self.config = import_core("swe_hooks.core.config")
        self._saved = {k: os.environ.get(k) for k in self.ENV_KEYS}
        for k in self.ENV_KEYS:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_defaults_when_env_unset(self):
        cfg = self.config.get_response_format_config()
        self.assertEqual(cfg, {"enabled": True, "terse_limit": 40, "detail_limit": 600})

    def test_disabled_via_env(self):
        os.environ["CLAUDE_PLUGIN_OPTION_RESPONSE_FORMAT_ENABLED"] = "false"
        self.assertFalse(self.config.get_response_format_config()["enabled"])

    def test_enabled_truthy_variants(self):
        for v in ("1", "true", "YES", "on"):
            os.environ["CLAUDE_PLUGIN_OPTION_RESPONSE_FORMAT_ENABLED"] = v
            self.assertTrue(self.config.get_response_format_config()["enabled"], v)

    def test_custom_limits(self):
        os.environ["CLAUDE_PLUGIN_OPTION_RESPONSE_FORMAT_TERSE_LIMIT"] = "150"
        os.environ["CLAUDE_PLUGIN_OPTION_RESPONSE_FORMAT_DETAIL_LIMIT"] = "800"
        cfg = self.config.get_response_format_config()
        self.assertEqual(cfg["terse_limit"], 150)
        self.assertEqual(cfg["detail_limit"], 800)

    def test_malformed_limit_falls_back_to_default(self):
        os.environ["CLAUDE_PLUGIN_OPTION_RESPONSE_FORMAT_TERSE_LIMIT"] = "notanint"
        self.assertEqual(self.config.get_response_format_config()["terse_limit"], 40)

    def test_malformed_bool_falls_back_to_default(self):
        os.environ["CLAUDE_PLUGIN_OPTION_RESPONSE_FORMAT_ENABLED"] = "maybe"
        self.assertTrue(self.config.get_response_format_config()["enabled"])


# ---------------------------------------------------------------------------
# main() end-to-end harness — real transcript file, patched config/state/IO
# ---------------------------------------------------------------------------
def _stub_state_manager(state):
    """A StateManager stand-in reporting a fixed workflow state."""
    class _Stub:
        def __init__(self, *args, **kwargs):
            pass

        def get_current_state(self):
            return state
    return _Stub


class _MainHarness(unittest.TestCase):
    """Shared fixture: drives gate.main() against a real transcript file with
    config, setup state, stream dir, and workflow state all patched. The
    transcript basename is 'session', so the session id is 'session'."""

    TERSE_LIMIT = 5

    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        self.transcript_path = os.path.join(self.tmp.name, "session.jsonl")
        self.streams = os.path.join(self.tmp.name, "streams")
        os.makedirs(self.streams, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()
        reset_caches()

    def _write_transcript(self, assistant_text, user_text="fix it"):
        lines = [
            {"type": "user", "message": {"content": user_text}},
            {"type": "assistant", "message": {"content": assistant_text}},
        ]
        with open(self.transcript_path, "w") as f:
            for rec in lines:
                f.write(json.dumps(rec) + "\n")

    def _run_main(self, stop_hook_active=False, state="WF_EXECUTE"):
        payload = {
            "transcript_path": self.transcript_path,
            "stop_hook_active": stop_hook_active,
        }
        buf = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
             mock.patch.object(gate, "get_project_root", return_value=self.tmp.name), \
             mock.patch.object(gate, "resolve_setup_state",
                                return_value={"bypassed": False, "initialized": True}), \
             mock.patch.object(gate, "get_response_format_config",
                                return_value={"enabled": True,
                                               "terse_limit": self.TERSE_LIMIT,
                                               "detail_limit": 600}), \
             mock.patch.object(gate, "get_stream_dir", return_value=self.streams), \
             mock.patch.object(gate, "StateManager", _stub_state_manager(state)), \
             redirect_stdout(buf):
            try:
                gate.main()
            except SystemExit:
                pass
        return buf.getvalue()

    def _sentinel(self):
        return os.path.join(self.streams, ".format-gate-block-session")

    def _read_sentinel(self):
        with open(self._sentinel(), encoding="utf-8") as f:
            return json.load(f)


class TestMainStopHookActive(_MainHarness):
    """stop_hook_active must never block (deadlock/ping-pong prevention)."""

    def test_stop_hook_active_never_blocks_even_on_violation(self):
        # A response with a banned recap heading would normally block; with
        # stop_hook_active=True, main() must exit clean with no output.
        self._write_transcript("## Summary\nAll done and verified.")
        out = self._run_main(stop_hook_active=True)
        self.assertEqual(out.strip(), "")

    def test_fresh_turn_still_blocks_on_violation(self):
        # Same content, but stop_hook_active=False (a fresh turn) -> blocks.
        self._write_transcript("## Summary\nAll done and verified.")
        out = self._run_main(stop_hook_active=False)
        self.assertIn('"decision": "block"', out)


class TestMainWfDone(_MainHarness):
    """F3: WF_DONE (final deliverable turn) never blocks."""

    def test_wf_done_never_blocks_even_on_violation(self):
        self._write_transcript("## Summary\nAll done and verified.")
        out = self._run_main(state="WF_DONE")
        self.assertEqual(out.strip(), "")
        self.assertFalse(os.path.exists(self._sentinel()))

    def test_other_state_still_blocks(self):
        self._write_transcript("## Summary\nAll done and verified.")
        out = self._run_main(state="WF_VERIFY")
        self.assertIn('"decision": "block"', out)


class TestMainOneBlockPerTurn(_MainHarness):
    """F2: at most one format block per user turn; second overage warns."""

    ESSAY = " ".join(["word"] * 60)

    def test_first_overage_blocks_and_records_turn(self):
        self._write_transcript(self.ESSAY)
        out = self._run_main()
        self.assertIn('"decision": "block"', out)
        rec = self._read_sentinel()
        self.assertEqual(rec["count"], 1)
        self.assertEqual(rec["fp"], gate.turn_fingerprint("fix it"))

    def test_second_overage_same_turn_warns_not_blocks(self):
        self._write_transcript(self.ESSAY)
        self._run_main()               # first overage: block
        out = self._run_main()         # same user turn: WARN attachment
        self.assertNotIn('"decision": "block"', out)
        self.assertIn("additionalContext", out)
        self.assertIn("RESPONSE FORMAT WARN", out)
        self.assertEqual(self._read_sentinel()["count"], 2)

    def test_new_user_turn_blocks_again(self):
        self._write_transcript(self.ESSAY)
        self._run_main()
        # A NEW genuine user message -> new fingerprint -> full block again.
        self._write_transcript(self.ESSAY, user_text="now fix the parser")
        out = self._run_main()
        self.assertIn('"decision": "block"', out)
        self.assertEqual(self._read_sentinel()["fp"],
                         gate.turn_fingerprint("now fix the parser"))

    def test_legacy_sentinel_content_blocks_again(self):
        # A pre-F2 sentinel held the bare word 'blocked' — it cannot identify
        # the turn, so it must not suppress a block (treated as no record).
        with open(self._sentinel(), "w") as f:
            f.write("blocked")
        self._write_transcript(self.ESSAY)
        out = self._run_main()
        self.assertIn('"decision": "block"', out)


if __name__ == "__main__":
    unittest.main()
