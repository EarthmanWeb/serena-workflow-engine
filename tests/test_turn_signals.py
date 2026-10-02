"""Tests for swe_hooks.core.turn_signals — pure mid-turn detection helpers
shared by the two Stop hooks (swe_stop_continue_working, swe_stop_response_format).

Stdlib unittest only; deterministic and fully offline. All transcript IO
happens inside a tempfile.TemporaryDirectory.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_core  # noqa: E402

ts = import_core("swe_hooks.core.turn_signals")


# ---------------------------------------------------------------------------
# text_of / is_genuine_user (moved here from the response-format gate)
# ---------------------------------------------------------------------------
class TestTextExtraction(unittest.TestCase):
    def test_text_of_string(self):
        self.assertEqual(ts.text_of("hello"), "hello")

    def test_text_of_block_list(self):
        content = [
            {"type": "text", "text": "a"},
            {"type": "tool_use", "name": "x"},
            {"type": "text", "text": "b"},
        ]
        self.assertEqual(ts.text_of(content), "a\nb")

    def test_text_of_empty(self):
        self.assertEqual(ts.text_of([]), "")

    def test_text_of_none(self):
        self.assertEqual(ts.text_of(None), "")


class TestIsGenuineUser(unittest.TestCase):
    def _user(self, content):
        return {"type": "user", "message": {"content": content}}

    def test_real_user_message(self):
        self.assertTrue(ts.is_genuine_user(self._user("fix the bug")))

    def test_assistant_is_not_user(self):
        self.assertFalse(ts.is_genuine_user(
            {"type": "assistant", "message": {"content": "hi"}}))

    def test_tool_result_only_is_plumbing(self):
        content = [{"type": "tool_result", "content": "output"}]
        self.assertFalse(ts.is_genuine_user(self._user(content)))

    def test_system_reminder_wrapper_is_not_user(self):
        self.assertFalse(ts.is_genuine_user(
            self._user("<system-reminder>do this</system-reminder>")))

    def test_command_wrapper_is_not_user(self):
        self.assertFalse(ts.is_genuine_user(
            self._user("<command-name>/foo</command-name>")))

    def test_local_command_wrapper_is_not_user(self):
        self.assertFalse(ts.is_genuine_user(
            self._user("<local-command-stdout>ok</local-command-stdout>")))

    def test_system_notification_is_not_user(self):
        self.assertFalse(ts.is_genuine_user(
            self._user("[SYSTEM NOTIFICATION] something happened")))

    def test_stop_hook_feedback_is_not_user(self):
        self.assertFalse(ts.is_genuine_user(
            self._user("Stop hook feedback: do not stop yet")))

    def test_empty_text_is_not_user(self):
        self.assertFalse(ts.is_genuine_user(self._user("   ")))


class TestEndsWithQuestion(unittest.TestCase):
    def test_question_mark_ending_true(self):
        self.assertTrue(ts.ends_with_question("Should I proceed with the deploy?"))

    def test_question_with_trailing_punctuation_true(self):
        self.assertTrue(ts.ends_with_question('Should I proceed?"'))

    def test_statement_ending_false(self):
        self.assertFalse(ts.ends_with_question("Fixed the bug."))

    def test_question_mark_mid_reply_not_last_paragraph_false(self):
        self.assertFalse(ts.ends_with_question("Why did this happen? Anyway, fixed it."))

    def test_empty_text_false(self):
        self.assertFalse(ts.ends_with_question(""))
        self.assertFalse(ts.ends_with_question(None))


# ---------------------------------------------------------------------------
# queued_command_prompt_text
# ---------------------------------------------------------------------------
class TestQueuedCommandPromptText(unittest.TestCase):
    def test_human_turn_true_extracts_prompt(self):
        rec = {
            "type": "attachment",
            "attachment": {
                "type": "queued_command",
                "prompt": [{"type": "text", "text": "also fix the parser"}],
                "commandMode": "prompt",
                "origin": {"kind": "human"},
                "humanTurn": True,
            },
        }
        self.assertEqual(ts.queued_command_prompt_text(rec), "also fix the parser")

    def test_origin_kind_human_without_human_turn_flag(self):
        rec = {
            "type": "attachment",
            "attachment": {
                "type": "queued_command",
                "prompt": [{"type": "text", "text": "hello"}],
                "origin": {"kind": "human"},
            },
        }
        self.assertEqual(ts.queued_command_prompt_text(rec), "hello")

    def test_non_human_origin_returns_none(self):
        rec = {
            "type": "attachment",
            "attachment": {
                "type": "queued_command",
                "prompt": [{"type": "text", "text": "hello"}],
                "origin": {"kind": "system"},
                "humanTurn": False,
            },
        }
        self.assertIsNone(ts.queued_command_prompt_text(rec))

    def test_non_queued_command_attachment_returns_none(self):
        rec = {"type": "attachment", "attachment": {"type": "other"}}
        self.assertIsNone(ts.queued_command_prompt_text(rec))

    def test_non_attachment_record_returns_none(self):
        self.assertIsNone(ts.queued_command_prompt_text({"type": "user"}))


# ---------------------------------------------------------------------------
# user_spoke_mid_turn
# ---------------------------------------------------------------------------
class TestUserSpokeMidTurn(unittest.TestCase):
    def _write(self, records):
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8")
        for rec in records:
            tmp.write(json.dumps(rec) + "\n")
        tmp.close()
        self.addCleanup(os.unlink, tmp.name)
        return tmp.name

    def _user(self, text):
        return {"type": "user", "message": {"content": text}}

    def _assistant(self, text):
        return {"type": "assistant", "message": {"content": text}}

    def _queued(self, text="follow up", human_turn=True, origin_kind=None):
        attachment = {
            "type": "queued_command",
            "prompt": [{"type": "text", "text": text}],
            "commandMode": "prompt",
        }
        if human_turn is not None:
            attachment["humanTurn"] = human_turn
        if origin_kind is not None:
            attachment["origin"] = {"kind": origin_kind}
        return {"type": "attachment", "attachment": attachment}

    def _enqueue(self, reason=None):
        rec = {"type": "queue-operation", "operation": "enqueue"}
        if reason is not None:
            rec["reason"] = reason
        return rec

    # --- positive cases ---
    def test_queued_command_human_turn_after_last_user_is_true(self):
        path = self._write([
            self._user("do the task"),
            self._assistant("working on it"),
            self._queued(human_turn=True),
        ])
        self.assertTrue(ts.user_spoke_mid_turn(path))

    def test_queued_command_origin_human_after_last_user_is_true(self):
        path = self._write([
            self._user("do the task"),
            self._assistant("working on it"),
            self._queued(human_turn=None, origin_kind="human"),
        ])
        self.assertTrue(ts.user_spoke_mid_turn(path))

    def test_queue_operation_enqueue_after_last_user_is_true(self):
        path = self._write([
            self._user("do the task"),
            self._assistant("working on it"),
            self._enqueue(),
        ])
        self.assertTrue(ts.user_spoke_mid_turn(path))

    # --- negative cases ---
    def test_queued_command_before_last_genuine_prompt_does_not_count(self):
        # A queued_command that arrived BEFORE the last genuine user record
        # was already consumed by a prior turn — it must not count for THIS
        # turn's mid-turn detection.
        path = self._write([
            self._queued(human_turn=True),
            self._user("now the real prompt for this turn"),
            self._assistant("working on it"),
        ])
        self.assertFalse(ts.user_spoke_mid_turn(path))

    def test_queue_operation_dequeue_does_not_count(self):
        path = self._write([
            self._user("do the task"),
            self._assistant("working"),
            {"type": "queue-operation", "operation": "dequeue", "reason": "delivered_to_agent"},
        ])
        self.assertFalse(ts.user_spoke_mid_turn(path))

    def test_queued_command_non_human_does_not_count(self):
        path = self._write([
            self._user("do the task"),
            self._assistant("working"),
            self._queued(human_turn=False, origin_kind="system"),
        ])
        self.assertFalse(ts.user_spoke_mid_turn(path))

    def test_no_mid_turn_signal_is_false(self):
        path = self._write([
            self._user("do the task"),
            self._assistant("done"),
        ])
        self.assertFalse(ts.user_spoke_mid_turn(path))

    def test_no_genuine_user_record_at_all_is_false(self):
        path = self._write([self._assistant("hello")])
        self.assertFalse(ts.user_spoke_mid_turn(path))

    def test_missing_file_returns_false(self):
        self.assertFalse(ts.user_spoke_mid_turn("/nonexistent/path.jsonl"))

    def test_empty_path_returns_false(self):
        self.assertFalse(ts.user_spoke_mid_turn(""))
        self.assertFalse(ts.user_spoke_mid_turn(None))

    def test_blank_and_malformed_lines_skipped(self):
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8")
        tmp.write("\n")
        tmp.write("{ not valid json\n")
        tmp.write(json.dumps(self._user("do the task")) + "\n")
        tmp.write(json.dumps(self._queued(human_turn=True)) + "\n")
        tmp.close()
        self.addCleanup(os.unlink, tmp.name)
        self.assertTrue(ts.user_spoke_mid_turn(tmp.name))


# ---------------------------------------------------------------------------
# unresolved_items
# ---------------------------------------------------------------------------
class TestUnresolvedItems(unittest.TestCase):
    # --- positives ---
    def test_mid_text_question(self):
        text = "Fixed the bug.\nShould I delete the old file?\nDone for now."
        self.assertIn("Should I delete the old file?", ts.unresolved_items(text))

    def test_indirect_invite_tell_me(self):
        self.assertEqual(
            ts.unresolved_items("Tell me if you want it removed."),
            ["Tell me if you want it removed."],
        )

    def test_indirect_invite_happy_to(self):
        self.assertEqual(
            ts.unresolved_items("Happy to add that too."),
            ["Happy to add that too."],
        )

    def test_pending_heading_before_fixing(self):
        self.assertEqual(
            ts.unresolved_items("Before fixing\nsome details here."),
            ["[section] Before fixing"],
        )

    def test_pending_heading_open_questions_bold(self):
        self.assertEqual(
            ts.unresolved_items("**Open questions:**\nmore text"),
            ["[section] Open questions"],
        )

    def test_pending_heading_markdown(self):
        self.assertEqual(
            ts.unresolved_items("## Pending\nmore text"),
            ["[section] Pending"],
        )

    def test_pending_heading_decisions_for_you(self):
        self.assertEqual(
            ts.unresolved_items("Decisions for you:"),
            ["[section] Decisions for you"],
        )

    def test_bare_offer_i_can_make(self):
        text = "I can make DESCRIPTION use the plain text of event_content."
        self.assertEqual(ts.unresolved_items(text), [text])

    def test_say_the_word(self):
        text = "Say the word and I'll push it."
        self.assertEqual(ts.unresolved_items(text), [text])

    def test_happy_to_wire_that_up(self):
        text = "Happy to wire that up."
        self.assertEqual(ts.unresolved_items(text), [text])

    def test_glad_to_add_that(self):
        text = "Glad to add that."
        self.assertEqual(ts.unresolved_items(text), [text])

    def test_next_step_would_be_to(self):
        text = "Next step would be to run the migration."
        self.assertEqual(ts.unresolved_items(text), [text])

    def test_one_option_is_to(self):
        text = "One option is to switch to ntfy."
        self.assertEqual(ts.unresolved_items(text), [text])

    def test_if_you_want_i_can_add_a_hook(self):
        text = "If you want, I can add a hook for that."
        self.assertEqual(ts.unresolved_items(text), [text])

    def test_two_item_sample_reply_yields_at_least_three_items(self):
        text = (
            "Decisions for you:\n"
            "I can make DESCRIPTION use the plain text of event_content.\n"
            "I can also make TITLE truncate at 80 chars.\n"
        )
        self.assertGreaterEqual(len(ts.unresolved_items(text)), 3)

    # --- negatives ---
    def test_plain_statement_no_items(self):
        self.assertEqual(ts.unresolved_items("Fixed the bug. All tests pass."), [])

    def test_i_can_see_the_file_ignored(self):
        self.assertEqual(ts.unresolved_items("I can see the file."), [])

    def test_i_can_confirm_it_works_ignored(self):
        self.assertEqual(ts.unresolved_items("I can confirm it works."), [])

    def test_fenced_code_question_ignored(self):
        text = "Here is the fix:\n```\nis this right?\n```\nDone."
        self.assertEqual(ts.unresolved_items(text), [])

    def test_inline_code_question_ignored(self):
        text = "Run `is this right?` to check. Done."
        self.assertEqual(ts.unresolved_items(text), [])

    def test_url_with_query_string_ignored(self):
        text = "See https://example.com/path?foo=bar for details."
        self.assertEqual(ts.unresolved_items(text), [])

    def test_blockquote_question_ignored(self):
        text = "> Why did this happen?\nFixed it anyway."
        self.assertEqual(ts.unresolved_items(text), [])

    def test_bare_operator_fragment_ignored(self):
        self.assertEqual(
            ts.unresolved_items("Uses the ?? fallback operator here."), [])

    def test_cant_if_clause_ignored(self):
        self.assertEqual(
            ts.unresolved_items("I can't reproduce it if the flag is unset."), [])

    def test_double_quoted_offer_is_cited_not_asked(self):
        text = 'That\'s the "if you want, I can…" pattern you described.'
        self.assertEqual(ts.unresolved_items(text), [])

    def test_curly_quoted_offer_is_cited_not_asked(self):
        text = "That’s the “Happy to wire that up” line again."
        self.assertEqual(ts.unresolved_items(text), [])

    def test_bold_label_with_trailing_text_not_a_heading(self):
        text = "**Questions:** what in the harness blocks X"
        self.assertEqual(ts.unresolved_items(text), [])

    def test_empty_text_no_items(self):
        self.assertEqual(ts.unresolved_items(""), [])
        self.assertEqual(ts.unresolved_items(None), [])


# ---------------------------------------------------------------------------
# final_reply_text
# ---------------------------------------------------------------------------
class TestFinalReplyText(unittest.TestCase):
    def _write(self, records):
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8")
        for rec in records:
            tmp.write(json.dumps(rec) + "\n")
        tmp.close()
        self.addCleanup(os.unlink, tmp.name)
        return tmp.name

    def _user(self, text):
        return {"type": "user", "message": {"content": text}}

    def _assistant_text(self, text):
        return {"type": "assistant",
                "message": {"content": [{"type": "text", "text": text}]}}

    def _assistant_tool_use(self, name="Bash"):
        return {"type": "assistant",
                "message": {"content": [{"type": "tool_use", "name": name}]}}

    def test_text_after_last_tool_use_only(self):
        path = self._write([
            self._user("do task"),
            self._assistant_text("before"),
            self._assistant_tool_use(),
            self._assistant_text("after"),
        ])
        self.assertEqual(ts.final_reply_text(path), "after")

    def test_text_before_ask_user_question_excluded(self):
        path = self._write([
            self._user("do task"),
            self._assistant_text("pretext"),
            self._assistant_tool_use(name="AskUserQuestion"),
            self._assistant_text("final summary"),
        ])
        self.assertEqual(ts.final_reply_text(path), "final summary")

    def test_resets_at_new_genuine_user_prompt(self):
        path = self._write([
            self._user("task1"),
            self._assistant_text("reply1"),
            self._user("task2"),
            self._assistant_text("reply2"),
        ])
        self.assertEqual(ts.final_reply_text(path), "reply2")

    def test_missing_path_returns_empty(self):
        self.assertEqual(ts.final_reply_text("/nonexistent/path.jsonl"), "")

    def test_empty_path_returns_empty(self):
        self.assertEqual(ts.final_reply_text(""), "")
        self.assertEqual(ts.final_reply_text(None), "")


if __name__ == "__main__":
    unittest.main()
