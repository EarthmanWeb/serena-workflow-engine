"""Tests for swe_hooks.core.delegation_sweep — per-subagent doc-sweep
computation: WM parsing, prompt path extraction, test-work detection,
required_reading ordering/dedupe/cap, and required_reading_block format.

Stdlib unittest only, temp-dir fixtures (mirrors test_doc_requirements.py).
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_core, reset_caches  # noqa: E402

delegation_sweep = import_core("swe_hooks.core.delegation_sweep")
doc_requirements = import_core("swe_hooks.core.doc_requirements")


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


class DelegationSweepTestCase(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        self.project_root = self.tmp.name
        doc_requirements._INDEX_CACHE.clear()

    def tearDown(self):
        doc_requirements._INDEX_CACHE.clear()
        self.tmp.cleanup()


# ──────────────────────────────────────────────────────────────────
# wm_memories
# ──────────────────────────────────────────────────────────────────

class WmMemoriesTests(unittest.TestCase):
    def test_memories_loaded_line_parsed(self):
        wm = "- **Memories loaded**: feature/FEATURE_X, dom/DOM_Y\n"
        self.assertEqual(
            delegation_sweep.wm_memories(wm), ["feature/FEATURE_X", "dom/DOM_Y"])

    def test_rules_planned_line_parsed(self):
        wm = "- **Rules planned**: ref/REF_A, dom/DOM_B\n"
        self.assertEqual(
            delegation_sweep.wm_memories(wm), ["ref/REF_A", "dom/DOM_B"])

    def test_compliance_checklist_mem_citations_parsed(self):
        wm = (
            "## Compliance Checklist\n"
            "- [ ] do the thing (mem:dom/DOM_X)\n"
            "- [ ] do another (mem:ref/REF_Y)\n"
        )
        result = delegation_sweep.wm_memories(wm)
        self.assertIn("dom/DOM_X", result)
        self.assertIn("ref/REF_Y", result)

    def test_annotations_and_backticks_stripped(self):
        wm = "- **Memories loaded**: `feature/FEATURE_X` — used for routing\n"
        self.assertEqual(delegation_sweep.wm_memories(wm), ["feature/FEATURE_X"])

    def test_wf_prefix_excluded(self):
        wm = "- **Memories loaded**: wf/WF_CLASSIFY, feature/FEATURE_X\n"
        self.assertEqual(delegation_sweep.wm_memories(wm), ["feature/FEATURE_X"])

    def test_claude_prefix_excluded(self):
        wm = "- **Memories loaded**: claude/CLAUDE_OBLIGATIONS, feature/FEATURE_X\n"
        self.assertEqual(delegation_sweep.wm_memories(wm), ["feature/FEATURE_X"])

    def test_wm_name_excluded(self):
        wm = "- **Memories loaded**: WM_abc12345, feature/FEATURE_X\n"
        self.assertEqual(delegation_sweep.wm_memories(wm), ["feature/FEATURE_X"])

    def test_spec_report_research_project_excluded(self):
        wm = ("- **Memories loaded**: spec/SPEC_A, report/REPORT_B, "
              "research/RESEARCH_C, project/PROJECT_D, feature/FEATURE_X\n")
        self.assertEqual(delegation_sweep.wm_memories(wm), ["feature/FEATURE_X"])

    def test_no_feature_token_excluded(self):
        wm = "- **Memories loaded**: no-feature\n"
        self.assertEqual(delegation_sweep.wm_memories(wm), [])

    def test_dedupe_across_sources(self):
        wm = (
            "- **Memories loaded**: feature/FEATURE_X\n"
            "- **Rules planned**: feature/FEATURE_X, dom/DOM_Y\n"
        )
        self.assertEqual(
            delegation_sweep.wm_memories(wm), ["feature/FEATURE_X", "dom/DOM_Y"])

    def test_empty_wm_text_returns_empty(self):
        self.assertEqual(delegation_sweep.wm_memories(""), [])
        self.assertEqual(delegation_sweep.wm_memories(None), [])


# ──────────────────────────────────────────────────────────────────
# prompt_paths
# ──────────────────────────────────────────────────────────────────

class PromptPathsTests(unittest.TestCase):
    def test_relative_path_extracted(self):
        result = delegation_sweep.prompt_paths(
            "Fix hooks/pre/swe_pre_agent_model_gate.py", "/repo")
        self.assertIn("hooks/pre/swe_pre_agent_model_gate.py", result)

    def test_backticked_path_extracted(self):
        result = delegation_sweep.prompt_paths(
            "Fix `hooks/pre/swe_pre_agent_model_gate.py` now.", "/repo")
        self.assertIn("hooks/pre/swe_pre_agent_model_gate.py", result)

    def test_quoted_path_extracted(self):
        result = delegation_sweep.prompt_paths(
            'Edit "tests/test_scope_guard.py" please.', "/repo")
        self.assertIn("tests/test_scope_guard.py", result)

    def test_trailing_punctuation_stripped(self):
        result = delegation_sweep.prompt_paths(
            "See hooks/pre/swe_pre_agent_model_gate.py, then fix it.", "/repo")
        self.assertIn("hooks/pre/swe_pre_agent_model_gate.py", result)

    def test_absolute_path_under_project_root_relativized(self):
        result = delegation_sweep.prompt_paths(
            "Fix /repo/hooks/pre/swe_pre_agent_model_gate.py", "/repo")
        self.assertIn("hooks/pre/swe_pre_agent_model_gate.py", result)

    def test_absolute_path_outside_project_root_kept_as_is(self):
        result = delegation_sweep.prompt_paths(
            "Fix /other/place/file.py", "/repo")
        self.assertIn("/other/place/file.py", result)

    def test_bare_extension_token_without_slash_extracted(self):
        result = delegation_sweep.prompt_paths("Update config.json now.", "/repo")
        self.assertIn("config.json", result)

    def test_glob_token_kept_verbatim(self):
        result = delegation_sweep.prompt_paths("Update hooks/post/*.", "/repo")
        self.assertIn("hooks/post/*", result)

    def test_no_path_tokens_returns_empty(self):
        result = delegation_sweep.prompt_paths("Implement the feature.", "/repo")
        self.assertEqual(result, [])

    def test_dedupe_preserves_order(self):
        result = delegation_sweep.prompt_paths(
            "Fix src/a.py then src/a.py again then src/b.py", "/repo")
        self.assertEqual(result, ["src/a.py", "src/b.py"])

    def test_url_not_treated_as_path(self):
        result = delegation_sweep.prompt_paths(
            "See https://example.com/foo.py for reference.", "/repo")
        self.assertEqual(result, [])


# ──────────────────────────────────────────────────────────────────
# is_test_work
# ──────────────────────────────────────────────────────────────────

class IsTestWorkTests(unittest.TestCase):
    def test_mentions_tests_dir(self):
        self.assertTrue(delegation_sweep.is_test_work("Fix tests/test_foo.py"))

    def test_mentions_test_word(self):
        self.assertTrue(delegation_sweep.is_test_work("Write a test for this"))

    def test_mentions_unittest(self):
        self.assertTrue(delegation_sweep.is_test_work("Run unittest discover"))

    def test_mentions_pytest(self):
        self.assertTrue(delegation_sweep.is_test_work("Run pytest now"))

    def test_mentions_spec(self):
        self.assertTrue(delegation_sweep.is_test_work("Write a gherkin spec"))

    def test_no_test_mention_false(self):
        self.assertFalse(delegation_sweep.is_test_work("Implement the login flow"))

    def test_empty_prompt_false(self):
        self.assertFalse(delegation_sweep.is_test_work(""))
        self.assertFalse(delegation_sweep.is_test_work(None))


# ──────────────────────────────────────────────────────────────────
# required_reading
# ──────────────────────────────────────────────────────────────────

class RequiredReadingTests(DelegationSweepTestCase):
    def test_path_based_doc_included(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_X.md"),
               '---\nname: X\npaths:\n  - "hooks/**/*.py"\n---\nbody')
        result = delegation_sweep.required_reading(
            "Fix hooks/pre/foo.py", "", self.project_root)
        self.assertIn("feature/FEATURE_X", result)

    def test_test_work_adds_feature_tests(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_TESTS.md"), "# tests")
        result = delegation_sweep.required_reading(
            "Fix tests/test_foo.py", "", self.project_root)
        self.assertIn("feature/FEATURE_TESTS", result)

    def test_missing_dev_tests_not_added(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_TESTS.md"), "# tests")
        result = delegation_sweep.required_reading(
            "Fix tests/test_foo.py", "", self.project_root)
        self.assertNotIn("dev/DEV_TESTS", result)

    def test_wm_memories_included(self):
        wm = "- **Memories loaded**: dom/DOM_X\n"
        result = delegation_sweep.required_reading("Implement X.", wm, self.project_root)
        self.assertIn("dom/DOM_X", result)

    def test_ordering_paths_then_tests_then_wm(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_X.md"),
               '---\nname: X\npaths:\n  - "hooks/**/*.py"\n---\nbody')
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_TESTS.md"), "# tests")
        wm = "- **Memories loaded**: dom/DOM_Z\n"
        result = delegation_sweep.required_reading(
            "Fix hooks/foo.py and tests/test_foo.py", wm, self.project_root)
        self.assertEqual(
            result.index("feature/FEATURE_X") < result.index("feature/FEATURE_TESTS"),
            True)
        self.assertEqual(
            result.index("feature/FEATURE_TESTS") < result.index("dom/DOM_Z"), True)

    def test_dedupe_across_sources(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_X.md"),
               '---\nname: X\npaths:\n  - "hooks/**/*.py"\n---\nbody')
        wm = "- **Memories loaded**: feature/FEATURE_X\n"
        result = delegation_sweep.required_reading(
            "Fix hooks/foo.py", wm, self.project_root)
        self.assertEqual(result.count("feature/FEATURE_X"), 1)

    def test_cap_truncates(self):
        wm_lines = ", ".join(f"dom/DOM_{i}" for i in range(20))
        wm = f"- **Memories loaded**: {wm_lines}\n"
        result = delegation_sweep.required_reading(
            "Implement X.", wm, self.project_root, cap=3)
        self.assertEqual(len(result), 3)

    def test_no_matches_returns_empty(self):
        result = delegation_sweep.required_reading("Implement X.", "", self.project_root)
        self.assertEqual(result, [])

    def test_glob_token_expanded(self):
        _write(os.path.join(self.project_root, "hooks", "post", "a.py"), "# a")
        _write(os.path.join(self.project_root, "hooks", "post", "b.py"), "# b")
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_POST.md"),
               '---\nname: POST\npaths:\n  - "hooks/post/*.py"\n---\nbody')
        result = delegation_sweep.required_reading(
            "Update hooks/post/*.py", "", self.project_root)
        self.assertIn("feature/FEATURE_POST", result)


# ──────────────────────────────────────────────────────────────────
# required_reading_block
# ──────────────────────────────────────────────────────────────────

class RequiredReadingBlockTests(DelegationSweepTestCase):
    def test_empty_names_returns_empty_string(self):
        self.assertEqual(delegation_sweep.required_reading_block([], self.project_root), "")
        self.assertEqual(delegation_sweep.required_reading_block(None, self.project_root), "")

    def test_block_format_with_read_memory_lines(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_X.md"), "---\nname: X\n---\nbody")
        block = delegation_sweep.required_reading_block(
            ["feature/FEATURE_X"], self.project_root)
        self.assertIn("[swe-required-reading]", block)
        self.assertIn('read_memory("feature/FEATURE_X")', block)

    def test_obligations_included_indented(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_X.md"),
               "---\nname: X\nobligations:\n  - Do the thing\n---\nbody")
        block = delegation_sweep.required_reading_block(
            ["feature/FEATURE_X"], self.project_root)
        self.assertIn("• Do the thing", block)

    def test_no_obligations_no_bullet_lines(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_Y.md"), "---\nname: Y\nobligations: []\n---\nbody")
        block = delegation_sweep.required_reading_block(
            ["feature/FEATURE_Y"], self.project_root)
        self.assertIn('read_memory("feature/FEATURE_Y")', block)
        self.assertNotIn("•", block)

    def test_multiple_names_each_get_a_line(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_A.md"), "---\nname: A\n---\nbody")
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_B.md"), "---\nname: B\n---\nbody")
        block = delegation_sweep.required_reading_block(
            ["feature/FEATURE_A", "feature/FEATURE_B"], self.project_root)
        self.assertIn('read_memory("feature/FEATURE_A")', block)
        self.assertIn('read_memory("feature/FEATURE_B")', block)


if __name__ == "__main__":
    unittest.main()
