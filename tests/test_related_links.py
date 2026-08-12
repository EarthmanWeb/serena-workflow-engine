"""Tests for related-links coverage in the docs-first mechanism (sweep v2).

Closes the observed loophole: an agent re-read an already-read memory
(DEV_TESTS) purely to refill the docs-first budget, and the memory's own
Related set (mem:feature/FEATURE_TESTS, mem:dev/DEV_PHP, ...) was never read.

New surfaces under test:
  - post/swe_post_read_state: _related_links (extract mem:/[[...]] links from
    READ memory content, excluding workflow-machinery topics), _unread_related
  - pre/swe_pre_search_docs_gate: FRESH-refill budget (re-reading an
    already-read doc does NOT refill; searches stay refilling), pending
    related docs listed in the deny message

Stdlib unittest only. Deterministic + offline; IO via tempfile.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_hook, import_core  # noqa: E402

stream = import_core("swe_hooks.core.stream")
read_mod = import_hook("post/swe_post_read_state")
gate_mod = import_hook("pre/swe_pre_search_docs_gate")


def _write_stream(path, events):
    with open(path, "w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


# ──────────────────────────────────────────────────────────────────
# post/swe_post_read_state — related-link extraction
# ──────────────────────────────────────────────────────────────────

class TestRelatedLinks(unittest.TestCase):
    def test_extracts_mem_and_wikilink_forms(self):
        text = ("Related: `mem:feature/FEATURE_TESTS` · mem:dev/DEV_PHP · "
                "see [[ref/REF_PLUGIN_REPO_FORMATTING]] for detail")
        links = read_mod._related_links(text)
        self.assertEqual(links, {
            "feature/feature_tests", "dev/dev_php",
            "ref/ref_plugin_repo_formatting"})

    def test_excludes_workflow_machinery_and_non_sweep_topics(self):
        text = ("mem:wf/WF_CLASSIFY mem:claude/CLAUDE_OBLIGATIONS "
                "mem:spec/SPEC_X mem:report/REPORT_Y mem:research/RESEARCH_Z "
                "mem:project/PROJECT_W mem:templates/feedback/FEEDBACK_Q "
                "mem:feature/FEATURE_KEEP")
        self.assertEqual(read_mod._related_links(text),
                         {"feature/feature_keep"})

    def test_plain_names_not_extracted(self):
        # Only explicit link forms count — a bare dir/NAME mention is not a link.
        text = "See feature/FEATURE_TESTS and dev/DEV_PHP for background."
        self.assertEqual(read_mod._related_links(text), set())

    def test_empty_content(self):
        self.assertEqual(read_mod._related_links(""), set())


class TestUnreadRelated(unittest.TestCase):
    def test_unread_is_links_minus_reads_minus_self(self):
        content = "mem:dev/DEV_PHP mem:feature/FEATURE_TESTS mem:ref/REF_X"
        unread = read_mod._unread_related(
            "dev/DEV_TESTS", content,
            {"dev/dev_tests", "feature/feature_tests"})
        self.assertEqual(unread, {"dev/dev_php", "ref/ref_x"})

    def test_self_link_never_pending(self):
        content = "mem:dev/DEV_TESTS mem:ref/REF_X"
        unread = read_mod._unread_related("dev/DEV_TESTS", content, set())
        self.assertEqual(unread, {"ref/ref_x"})

    def test_no_links_no_pending(self):
        self.assertEqual(
            read_mod._unread_related("dev/DEV_TESTS", "no links here", set()),
            set())


# ──────────────────────────────────────────────────────────────────
# pre/swe_pre_search_docs_gate — fresh-refill budget + pending listing
# ──────────────────────────────────────────────────────────────────

class TestFreshRefillBudget(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stream_path = os.path.join(self.tmp.name, "s.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def _spend_budget(self, events):
        events.extend({"type": "gated"}
                      for _ in range(gate_mod.GATED_CALL_BUDGET))
        return events

    def test_fresh_read_refills(self):
        events = self._spend_budget([
            {"type": "session_start"},
            {"type": "docread", "name": "dev/DEV_TESTS"},
        ])
        events.append({"type": "docread", "name": "feature/FEATURE_TESTS"})
        _write_stream(self.stream_path, events)
        self.assertTrue(gate_mod.docs_budget_allows(self.stream_path))

    def test_rereading_same_doc_does_not_refill(self):
        # The observed exploit: re-read DEV_TESTS purely to refill.
        events = self._spend_budget([
            {"type": "session_start"},
            {"type": "docread", "name": "dev/DEV_TESTS"},
        ])
        events.append({"type": "docread", "name": "dev/DEV_TESTS"})
        _write_stream(self.stream_path, events)
        self.assertFalse(gate_mod.docs_budget_allows(self.stream_path))

    def test_search_credit_always_refills(self):
        # A search that earned credit (no unread hits) refills even when
        # repeated — the same-docs-confirmed rule.
        events = self._spend_budget([
            {"type": "session_start"},
            {"type": "docread", "name": "memory-search"},
        ])
        events.append({"type": "docread", "name": "memory-search"})
        _write_stream(self.stream_path, events)
        self.assertTrue(gate_mod.docs_budget_allows(self.stream_path))

    def test_freshness_resets_at_task_start(self):
        # A doc read in a PREVIOUS task is fresh again in the current task.
        events = [
            {"type": "session_start"},
            {"type": "docread", "name": "dev/DEV_TESTS"},
            {"type": "state", "from_s": "WF_DONE", "to_s": "WF_CLASSIFY"},
            {"type": "docread", "name": "dev/DEV_TESTS"},
        ]
        self._spend_budget(events)
        _write_stream(self.stream_path, events)
        # The in-task first read refilled; 5 gated events spent it again.
        self.assertFalse(gate_mod.docs_budget_allows(self.stream_path))
        events.append({"type": "docread", "name": "dev/DEV_TESTS"})
        _write_stream(self.stream_path, events)
        # Re-read within the same task: not fresh, still spent.
        self.assertFalse(gate_mod.docs_budget_allows(self.stream_path))

    def test_budget_not_spent_stays_allowed_after_reread(self):
        # A re-read never REVOKES remaining budget.
        _write_stream(self.stream_path, [
            {"type": "session_start"},
            {"type": "docread", "name": "dev/DEV_TESTS"},
            {"type": "gated"},
            {"type": "docread", "name": "dev/DEV_TESTS"},
        ])
        self.assertTrue(gate_mod.docs_budget_allows(self.stream_path))

    def test_no_docread_no_budget(self):
        _write_stream(self.stream_path, [{"type": "session_start"}])
        self.assertFalse(gate_mod.docs_budget_allows(self.stream_path))


class TestPendingRelatedDocs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stream_path = os.path.join(self.tmp.name, "s.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_pending_is_surfaced_links_minus_reads(self):
        _write_stream(self.stream_path, [
            {"type": "session_start"},
            {"type": "docread", "name": "dev/DEV_TESTS"},
            {"type": "docpending",
             "new": ["feature/feature_tests", "dev/dev_php"]},
            {"type": "docread", "name": "dev/DEV_PHP"},
        ])
        self.assertEqual(
            gate_mod.pending_related_docs(self.stream_path),
            {"feature/feature_tests"})

    def test_pending_resets_at_task_start(self):
        _write_stream(self.stream_path, [
            {"type": "docpending", "new": ["ref/ref_old"]},
            {"type": "state", "from_s": "WF_DONE", "to_s": "WF_CLASSIFY"},
        ])
        self.assertEqual(
            gate_mod.pending_related_docs(self.stream_path), set())

    def test_deny_message_lists_pending(self):
        msg = gate_mod.build_deny_message(
            "Bash", pending={"feature/feature_tests", "dev/dev_php"})
        self.assertIn("dev/dev_php", msg)
        self.assertIn("feature/feature_tests", msg)

    def test_deny_message_without_pending_unchanged_shape(self):
        msg = gate_mod.build_deny_message("Bash")
        self.assertIn("DOCS FIRST", msg)


if __name__ == "__main__":
    unittest.main()
