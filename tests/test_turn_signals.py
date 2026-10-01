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


if __name__ == "__main__":
    unittest.main()
