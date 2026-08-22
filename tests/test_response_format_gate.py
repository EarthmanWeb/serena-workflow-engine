"""Tests for the response-format Stop gate + its config resolution.

Targets:
  - stop/swe_stop_response_format : pure evaluate(), prose_words(),
    is_genuine_user(), text_of(), the banned-pattern and detail-trigger regexes.
  - core.config.get_response_format_config : CLAUDE_PLUGIN_OPTION_* env parsing,
    defaults, and malformed-value fallback.

Stdlib unittest only; deterministic and fully offline. No transcript IO — every
tested surface is a pure function fed explicit args.
"""
import os
import sys
import unittest

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


# ---------------------------------------------------------------------------
# regex constants
# ---------------------------------------------------------------------------
class TestDetailTrigger(unittest.TestCase):
    def test_literal_detail_prefix_matches(self):
        for p in ("DETAIL: explain the flow", "detail - go deep", "  DETAIL:x"):
            self.assertTrue(gate.DETAIL_TRIGGERS.search(p), p)

    def test_natural_language_does_not_trigger(self):
        for p in ("why does this happen", "explain in depth", "be thorough please"):
            self.assertFalse(gate.DETAIL_TRIGGERS.search(p), p)

    def test_detail_word_midsentence_does_not_trigger(self):
        self.assertFalse(gate.DETAIL_TRIGGERS.search("give me the detail here"))


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


if __name__ == "__main__":
    unittest.main()
