"""Tests for skills/swe-memory-size-audit/scripts/validate-memory-graph.py.

Pure-function tests against synthetic memory trees, plus an integration
assertion that the real memories/ tree (+ .serena/memory, where present)
has zero dangling link errors.
"""
import json
import os
import shutil
import tempfile
import unittest

from _hookutil import PLUGIN_ROOT, load_script

vmg = load_script("skills/swe-memory-size-audit/scripts/validate-memory-graph.py")


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

    def test_mem_style_strips_trailing_sentence_punctuation(self):
        links = vmg.extract_links("see mem:dom/DOM_X.")
        self.assertIn("dom/DOM_X", links)
        self.assertNotIn("dom/DOM_X.", links)

    def test_mem_style_stops_at_comma_no_trailing_dash(self):
        links = vmg.extract_links("mem:ref/REF_A-B,")
        self.assertIn("ref/REF_A-B", links)
        self.assertNotIn("ref/REF_A-B,", links)


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

    def test_aliased_root_prefixes_name(self):
        root = os.path.join(self.tmp, "ext")
        write(root, "feature/FEATURE_Y.md", "# Y\n")
        result = vmg.validate([("em", root)])
        self.assertIn("em/feature/FEATURE_Y", result["word_counts"])

    def test_aliased_root_link_resolves_with_alias_prefix(self):
        root = os.path.join(self.tmp, "ext")
        write(root, "feature/FEATURE_Y.md", "# Y\nSee `mem:em/feature/FEATURE_Y2` next.\n")
        write(root, "feature/FEATURE_Y2.md", "# Y2\n")
        result = vmg.validate([("em", root)])
        self.assertEqual(result["dangling"], [])

    def test_mixed_plain_and_aliased_roots(self):
        root_a = os.path.join(self.tmp, "a")
        root_b = os.path.join(self.tmp, "b")
        write(root_a, "wf/WF_A.md", "# A\nSee `mem:em/feature/FEATURE_Y` next.\n")
        write(root_b, "feature/FEATURE_Y.md", "# Y\n")
        result = vmg.validate([root_a, ("em", root_b)])
        self.assertEqual(result["dangling"], [])


class TestRootParityCLI(unittest.TestCase):
    """CLI-level root parity with scripts/memory-size-audit.py: aliased
    --root, .serena/memory-paths.conf default, and --plugin-root."""

    SCRIPT_PATH = os.path.join(
        PLUGIN_ROOT, "skills", "swe-memory-size-audit", "scripts", "validate-memory-graph.py"
    )

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="memgraph_cli_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, args, cwd):
        import subprocess
        import sys as _sys
        return subprocess.run(
            [_sys.executable, self.SCRIPT_PATH] + args,
            cwd=cwd, capture_output=True, text=True,
        )

    def test_cli_aliased_root(self):
        root = os.path.join(self.tmp, "ext")
        write(root, "feature/FEATURE_Y.md", "# Y\n")
        proc = self._run(["--root", f"em={root}", "--json"], cwd=self.tmp)
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertIn("em/feature/FEATURE_Y", data["word_counts"])

    def test_cli_conf_default_when_no_root_flag(self):
        os.makedirs(os.path.join(self.tmp, ".serena"))
        memdir = os.path.join(self.tmp, ".serena", "memory")
        write(memdir, "dom/DOM_X.md", "# X\n")
        with open(os.path.join(self.tmp, ".serena", "memory-paths.conf"), "w") as f:
            f.write("./.serena/memory\n")
        proc = self._run(["--json"], cwd=self.tmp)
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertIn("dom/DOM_X", data["word_counts"])

    def test_cli_plugin_root_adds_extra_unaliased_root(self):
        proj_root = os.path.join(self.tmp, "proj_memories")
        plugin_root = os.path.join(self.tmp, "plugin_memories")
        write(proj_root, "wf/WF_A.md", "# A\nSee `mem:DOM_SHARED` next.\n")
        write(plugin_root, "dom/DOM_SHARED.md", "# Shared\n")
        proc = self._run(
            ["--root", proj_root, "--plugin-root", plugin_root, "--json"], cwd=self.tmp
        )
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data["dangling"], [])

    def test_cli_extra_root_appends_to_conf_default(self):
        """--extra-root adds a root ON TOP OF the conf-derived default roots
        (unlike a bare --root, which replaces them) — e.g. adding the plugin
        source repo's own memories/ tree alongside .serena/memory-paths.conf
        roots in one invocation."""
        os.makedirs(os.path.join(self.tmp, ".serena"))
        conf_memdir = os.path.join(self.tmp, ".serena", "memory")
        write(conf_memdir, "wf/WF_A.md", "# A\nSee `mem:DOM_SHARED` next.\n")
        with open(os.path.join(self.tmp, ".serena", "memory-paths.conf"), "w") as f:
            f.write("./.serena/memory\n")

        extra_root = os.path.join(self.tmp, "plugin_memories")
        write(extra_root, "dom/DOM_SHARED.md", "# Shared\n")

        proc = self._run(["--extra-root", extra_root, "--json"], cwd=self.tmp)
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        # Both the conf-derived root and the extra root are present.
        self.assertIn("wf/WF_A", data["word_counts"])
        self.assertIn("dom/DOM_SHARED", data["word_counts"])
        self.assertEqual(data["dangling"], [])

    def test_cli_extra_root_appends_to_explicit_root(self):
        """--extra-root also appends when --root is explicit (not just the
        conf-default path), and supports an alias."""
        root = os.path.join(self.tmp, "proj_memories")
        extra_root = os.path.join(self.tmp, "plugin_memories")
        write(root, "wf/WF_A.md", "# A\n")
        write(extra_root, "dom/DOM_B.md", "# B\n")
        proc = self._run(
            ["--root", root, "--extra-root", f"plug={extra_root}", "--json"], cwd=self.tmp
        )
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertIn("wf/WF_A", data["word_counts"])
        self.assertIn("plug/dom/DOM_B", data["word_counts"])


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
