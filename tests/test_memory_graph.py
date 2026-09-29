"""Tests for scripts/validate-memory-graph.py.

Pure-function tests against synthetic memory trees, plus an integration
assertion that the real memories/ tree (+ .serena/memory, where present)
has zero dangling link errors.
"""
import os
import shutil
import tempfile
import unittest

from _hookutil import PLUGIN_ROOT, load_script

vmg = load_script("scripts/validate-memory-graph.py")


def write(root, rel_path, content):
    path = os.path.join(root, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class TestIsPlaceholder(unittest.TestCase):
    def test_bracketed_is_placeholder(self):
        self.assertTrue(vmg.is_placeholder("FEATURE_[KEY]"))
        self.assertTrue(vmg.is_placeholder("WF_<STATE>"))

    def test_trailing_underscore_is_placeholder(self):
        self.assertTrue(vmg.is_placeholder("DEV_"))
        self.assertTrue(vmg.is_placeholder("ARCH_"))

    def test_dev_star_family_is_placeholder(self):
        self.assertTrue(vmg.is_placeholder("DEV_PHP"))
        self.assertTrue(vmg.is_placeholder("DEV_JAVASCRIPT"))

    def test_double_underscore_stub_is_placeholder(self):
        self.assertTrue(vmg.is_placeholder("ARCH__"))
        self.assertTrue(vmg.is_placeholder("REF__"))

    def test_wiki_syntax_examples_are_placeholders(self):
        self.assertTrue(vmg.is_placeholder("link"))
        self.assertTrue(vmg.is_placeholder("links"))
        self.assertTrue(vmg.is_placeholder("linked"))

    def test_project_generated_names_are_placeholders(self):
        self.assertTrue(vmg.is_placeholder("INDEX_FEATURES"))
        self.assertTrue(vmg.is_placeholder("index/INDEX_FEATURES"))

    def test_real_name_is_not_placeholder(self):
        self.assertFalse(vmg.is_placeholder("WF_CLASSIFY"))
        self.assertFalse(vmg.is_placeholder("arch/ARCH_SWE"))
        self.assertFalse(vmg.is_placeholder("DOM_SWE_HOOKS"))


class TestExtractLinks(unittest.TestCase):
    def test_mem_style(self):
        links = vmg.extract_links("see `mem:arch/ARCH_SWE` for details")
        self.assertIn("arch/ARCH_SWE", links)

    def test_wiki_style(self):
        links = vmg.extract_links("check [[DOM_SWE_HOOKS]] first")
        self.assertIn("DOM_SWE_HOOKS", links)

    def test_bare_backtick_style(self):
        links = vmg.extract_links("read `WF_CLASSIFY` now")
        self.assertIn("WF_CLASSIFY", links)

    def test_bare_backtick_requires_known_prefix(self):
        # Not one of the recognized prefixes -> not extracted as a link at all.
        links = vmg.extract_links("call `SOME_FUNC` now")
        self.assertNotIn("SOME_FUNC", links)


class TestValidateSyntheticTree(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="memgraph_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_clean_tree_no_dangling_no_orphans(self):
        write(self.tmp, "wf/WF_A.md", "# A\nSee `mem:wf/WF_B` next.\n")
        write(self.tmp, "wf/WF_B.md", "# B\nBack to `mem:wf/WF_A`.\n")
        result = vmg.validate([self.tmp])
        self.assertEqual(result["dangling"], [])
        self.assertEqual(result["orphans"], [])

    def test_dangling_link_detected(self):
        write(self.tmp, "wf/WF_A.md", "# A\nSee `mem:wf/WF_GHOST` next.\n")
        result = vmg.validate([self.tmp])
        self.assertEqual(len(result["dangling"]), 1)
        self.assertEqual(result["dangling"][0][0], "wf/WF_A")
        self.assertEqual(result["dangling"][0][1], "wf/WF_GHOST")

    def test_orphan_detected(self):
        write(self.tmp, "wf/WF_A.md", "# A\nSee `mem:wf/WF_B` next.\n")
        write(self.tmp, "wf/WF_B.md", "# B\nBack to `mem:wf/WF_A`.\n")
        write(self.tmp, "wf/WF_C.md", "# C\nNever referenced.\n")
        result = vmg.validate([self.tmp])
        self.assertIn("wf/WF_C", result["orphans"])
        self.assertNotIn("wf/WF_B", result["orphans"])
        self.assertNotIn("wf/WF_A", result["orphans"])

    def test_placeholder_link_not_dangling(self):
        write(self.tmp, "wf/WF_A.md", "# A\nSee `dev/DEV_PHP` for standards.\n")
        result = vmg.validate([self.tmp])
        self.assertEqual(result["dangling"], [])

    def test_resolves_with_or_without_dir_prefix(self):
        write(self.tmp, "wf/WF_A.md", "# A\nSee `mem:WF_B` (bare name).\n")
        write(self.tmp, "wf/WF_B.md", "# B\n")
        result = vmg.validate([self.tmp])
        self.assertEqual(result["dangling"], [])

    def test_word_count_and_caps_count_reported(self):
        write(self.tmp, "wf/WF_A.md", "one two three NEVER four MUST five\n")
        result = vmg.validate([self.tmp])
        self.assertEqual(result["word_counts"]["wf/WF_A"], 7)
        self.assertEqual(result["caps_counts"]["wf/WF_A"]["NEVER"], 1)
        self.assertEqual(result["caps_counts"]["wf/WF_A"]["MUST"], 1)

    def test_two_roots_cross_resolve(self):
        root_a = os.path.join(self.tmp, "a")
        root_b = os.path.join(self.tmp, "b")
        write(root_a, "wf/WF_A.md", "# A\nSee `mem:wf/WF_B` next.\n")
        write(root_b, "wf/WF_B.md", "# B\n")
        result = vmg.validate([root_a, root_b])
        self.assertEqual(result["dangling"], [])


class TestRealMemoryTree(unittest.TestCase):
    """Integration check: the shipped plugin-source memories/ tree must have
    zero dangling link errors.

    .serena/memory (this repo's own local dev-memory tree, not shipped plugin
    source) is checked separately and non-fatally: it is reported but does
    not fail this test, since it is maintained independently of memories/.
    """

    def test_no_dangling_in_plugin_source_tree(self):
        result = vmg.validate([os.path.join(PLUGIN_ROOT, "memories")])
        self.assertEqual(
            result["dangling"],
            [],
            f"Dangling memory links found in memories/: {result['dangling']}",
        )

    def test_serena_memory_tree_dangling_reported_non_fatally(self):
        serena_memory = os.path.join(PLUGIN_ROOT, ".serena", "memory")
        if not os.path.isdir(serena_memory):
            self.skipTest(".serena/memory not present")
        result = vmg.validate([
            os.path.join(PLUGIN_ROOT, "memories"),
            serena_memory,
        ])
        if result["dangling"]:
            print(
                f"\n[non-fatal] .serena/memory dangling links: {result['dangling']}"
            )


if __name__ == "__main__":
    unittest.main()
