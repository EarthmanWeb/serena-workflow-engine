"""Tests for related-links coverage in the docs-first mechanism (sweep v2).

Closes the observed loophole: an agent re-read an already-read memory
(DEV_TESTS) purely to refill the docs-first budget, and the memory's own
Related set (mem:feature/FEATURE_TESTS, mem:dev/DEV_PHP, ...) was never read.

New surfaces under test:
  - post/swe_post_read_state: _related_links (extract mem:/[[...]] links from
    READ memory content, excluding workflow-machinery topics), _unread_related

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


class TestSearchCreditExcludesSweepTopics(unittest.TestCase):
    """_search_credit (docs-first budget credit for search_memories calls)
    must never withhold credit, or demand a read, for an unread spec/,
    report/, research/, or project/ hit — USER DECISION (2026-09): those
    topics are fully excluded from the sweep, including as SEARCH-surfaced
    obligations."""

    def test_unread_spec_hit_alone_still_grants_credit(self):
        credit, new_names = read_mod._search_credit(
            {"spec/SPEC_COLD"}, set())
        self.assertTrue(credit)
        self.assertEqual(new_names, set())

    def test_unread_report_hit_alone_still_grants_credit(self):
        credit, new_names = read_mod._search_credit(
            {"report/REPORT_OLD"}, set())
        self.assertTrue(credit)
        self.assertEqual(new_names, set())

    def test_unread_research_hit_alone_still_grants_credit(self):
        credit, new_names = read_mod._search_credit(
            {"research/RESEARCH_COLD"}, set())
        self.assertTrue(credit)
        self.assertEqual(new_names, set())

    def test_unread_project_hit_alone_still_grants_credit(self):
        credit, new_names = read_mod._search_credit(
            {"project/PROJECT_OLD"}, set())
        self.assertTrue(credit)
        self.assertEqual(new_names, set())

    def test_mixed_hits_spec_excluded_other_still_demanded(self):
        # A genuine unread feature/dom hit alongside a spec hit still
        # withholds credit — only the spec/report portion is excluded.
        # _search_credit's inputs are already-normalized names (its callers
        # normalize via _extract_memory_names before calling it).
        credit, new_names = read_mod._search_credit(
            {"spec/spec_cold", "dom/dom_x"}, set())
        self.assertFalse(credit)
        self.assertEqual(new_names, {"dom/dom_x"})

    def test_mixed_hits_research_project_excluded_other_still_demanded(self):
        credit, new_names = read_mod._search_credit(
            {"research/research_cold", "project/project_cold", "dom/dom_x"},
            set())
        self.assertFalse(credit)
        self.assertEqual(new_names, {"dom/dom_x"})

    def test_aliased_spec_hit_excluded(self):
        # Alias form (em/spec/SPEC_X) is excluded the same as spec/SPEC_X.
        credit, new_names = read_mod._search_credit(
            {"em/spec/spec_aliased"}, set())
        self.assertTrue(credit)
        self.assertEqual(new_names, set())

    def test_aliased_research_hit_excluded(self):
        credit, new_names = read_mod._search_credit(
            {"em/research/research_aliased"}, set())
        self.assertTrue(credit)
        self.assertEqual(new_names, set())


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


if __name__ == "__main__":
    unittest.main()
