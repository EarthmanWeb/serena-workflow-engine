"""Tests for swe_hooks.core.doc_requirements — path -> required-memory API.

Stage 1 of "per-subagent doc enforcement": pure path/front-matter -> memory
mapping, no gate wiring yet. Covers memory_roots/memory_exists (plain +
aliased conf), parse_paths_frontmatter (block list, inline list, nested
metadata.paths, no front-matter), required_docs_for_path (** globs, test
artifacts, missing DEV_TESTS filtered out), and unread_required_docs.

Stdlib unittest only, temp-dir fixtures.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_core, reset_caches  # noqa: E402

doc_requirements = import_core("swe_hooks.core.doc_requirements")


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


class DocRequirementsTestCase(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        self.project_root = self.tmp.name
        doc_requirements._INDEX_CACHE.clear()
        # Isolate from the real dev-checkout memories/ dir: _hookutil.py sets
        # CLAUDE_PLUGIN_ROOT to this repo's root (so `import swe_hooks...`
        # resolves), which would otherwise make _shipped_memories_root()
        # resolve to THIS repo's real memories/ and leak its shipped
        # FEATURE_*/DEV_* memories into tests that don't expect them. Point
        # it at an empty temp dir unless a test explicitly overrides it
        # (see ShippedMemoriesRootTests).
        self._plugin_root_env_backup = os.environ.get("CLAUDE_PLUGIN_ROOT")
        self._empty_plugin_root = tempfile.mkdtemp()
        os.environ["CLAUDE_PLUGIN_ROOT"] = self._empty_plugin_root

    def tearDown(self):
        doc_requirements._INDEX_CACHE.clear()
        self.tmp.cleanup()
        if self._plugin_root_env_backup is None:
            os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
        else:
            os.environ["CLAUDE_PLUGIN_ROOT"] = self._plugin_root_env_backup


class MemoryRootsTests(DocRequirementsTestCase):
    def test_no_conf_falls_back_to_default_memory_dir(self):
        roots = doc_requirements.memory_roots(self.project_root)
        self.assertEqual(
            roots, [(None, os.path.join(self.project_root, ".serena", "memory"))])

    def test_conf_with_plain_and_aliased_root(self):
        other_dir = tempfile.mkdtemp()
        conf_path = os.path.join(self.project_root, ".serena", "memory-paths.conf")
        _write(conf_path, f"./.serena/memory\nem={other_dir}\n")
        roots = doc_requirements.memory_roots(self.project_root)
        root_map = {alias: os.path.realpath(path) for alias, path in roots}
        self.assertEqual(
            root_map[None],
            os.path.realpath(os.path.join(self.project_root, ".serena", "memory")))
        self.assertEqual(root_map["em"], os.path.realpath(other_dir))

    def test_conf_relative_path_resolves_against_project_root_not_cwd(self):
        conf_path = os.path.join(self.project_root, ".serena", "memory-paths.conf")
        _write(conf_path, "./.serena/memory\n")
        other_cwd = tempfile.mkdtemp()
        cwd_before = os.getcwd()
        try:
            os.chdir(other_cwd)
            roots = doc_requirements.memory_roots(self.project_root)
        finally:
            os.chdir(cwd_before)
        self.assertEqual(len(roots), 1)
        alias, path = roots[0]
        self.assertIsNone(alias)
        self.assertEqual(
            os.path.realpath(path),
            os.path.realpath(os.path.join(self.project_root, ".serena", "memory")))
        # Must NOT have resolved against the OTHER cwd.
        self.assertNotEqual(
            os.path.realpath(path),
            os.path.realpath(os.path.join(other_cwd, ".serena", "memory")))


class ShippedMemoriesRootTests(DocRequirementsTestCase):
    # Base setUp() already points CLAUDE_PLUGIN_ROOT at an isolated empty
    # temp dir; each test below overrides it further to exercise a specific
    # shipped-root resolution path. tearDown() (inherited) restores it.

    def test_shipped_root_from_claude_plugin_root_env(self):
        plugin_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(plugin_dir, "memories"), exist_ok=True)
        os.environ["CLAUDE_PLUGIN_ROOT"] = plugin_dir
        roots = doc_requirements.memory_roots(self.project_root)
        root_dirs = [os.path.realpath(p) for _, p in roots]
        self.assertIn(os.path.realpath(os.path.join(plugin_dir, "memories")), root_dirs)

    def test_shipped_root_is_last_lowest_precedence(self):
        plugin_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(plugin_dir, "memories"), exist_ok=True)
        os.environ["CLAUDE_PLUGIN_ROOT"] = plugin_dir
        roots = doc_requirements.memory_roots(self.project_root)
        self.assertEqual(
            os.path.realpath(roots[-1][1]),
            os.path.realpath(os.path.join(plugin_dir, "memories")))
        self.assertIsNone(roots[-1][0])  # unaliased

    def test_shipped_root_deduped_when_equal_to_conf_root(self):
        os.environ["CLAUDE_PLUGIN_ROOT"] = self.project_root
        os.makedirs(os.path.join(self.project_root, "memories"), exist_ok=True)
        conf_path = os.path.join(self.project_root, ".serena", "memory-paths.conf")
        _write(conf_path, os.path.join(self.project_root, "memories") + "\n")
        roots = doc_requirements.memory_roots(self.project_root)
        dirs = [os.path.realpath(p) for _, p in roots]
        self.assertEqual(len(dirs), len(set(dirs)))

    def test_shipped_root_missing_dir_not_added(self):
        os.environ["CLAUDE_PLUGIN_ROOT"] = os.path.join(self.project_root, "nonexistent")
        roots = doc_requirements.memory_roots(self.project_root)
        root_dirs = [os.path.realpath(p) for _, p in roots]
        self.assertNotIn(
            os.path.realpath(os.path.join(self.project_root, "nonexistent", "memories")),
            root_dirs)

    def test_shipped_memory_makes_feature_visible_to_path_matching(self):
        # Shipped-root globs apply when project_root IS the plugin source
        # repo (same .claude-plugin/plugin.json `name` as the shipped
        # plugin's own) — see ShippedRootPluginScopingTests for the
        # excluded (non-plugin-repo) case.
        plugin_dir = tempfile.mkdtemp()
        _write(os.path.join(plugin_dir, "memories", "feature", "FEATURE_SWE.md"),
               '---\nname: SWE\npaths:\n  - "hooks/**/*.py"\n---\nbody')
        _write(os.path.join(plugin_dir, ".claude-plugin", "plugin.json"), '{"name": "swe"}')
        os.environ["CLAUDE_PLUGIN_ROOT"] = plugin_dir
        _write(os.path.join(self.project_root, ".claude-plugin", "plugin.json"),
               '{"name": "swe"}')
        required = doc_requirements.required_docs_for_path(
            "hooks/pre/swe_pre_agent_model_gate.py", self.project_root)
        self.assertIn("feature/FEATURE_SWE", required)


class ReadObligationsTests(DocRequirementsTestCase):
    def test_block_list_obligations(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_X.md"),
               "---\nname: X\nobligations:\n  - Do the thing\n  - Do another thing\n---\nbody")
        self.assertEqual(
            doc_requirements.read_obligations("feature/FEATURE_X", self.project_root),
            ["Do the thing", "Do another thing"])

    def test_inline_list_obligations(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_Y.md"),
               '---\nobligations: ["Rule A", "Rule B"]\n---\nbody')
        self.assertEqual(
            doc_requirements.read_obligations("feature/FEATURE_Y", self.project_root),
            ["Rule A", "Rule B"])

    def test_empty_obligations_list(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_Z.md"),
               "---\nobligations: []\n---\nbody")
        self.assertEqual(
            doc_requirements.read_obligations("feature/FEATURE_Z", self.project_root), [])

    def test_no_obligations_field_returns_empty(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_NOOB.md"), "---\nname: X\n---\nbody")
        self.assertEqual(
            doc_requirements.read_obligations("feature/FEATURE_NOOB", self.project_root), [])

    def test_missing_memory_returns_empty(self):
        self.assertEqual(
            doc_requirements.read_obligations("feature/NOPE", self.project_root), [])

    def test_no_frontmatter_returns_empty(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_NOFM.md"), "# no front matter")
        self.assertEqual(
            doc_requirements.read_obligations("feature/FEATURE_NOFM", self.project_root), [])


class MemoryExistsTests(DocRequirementsTestCase):
    def test_plain_root_memory_exists(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_TESTS.md"), "# x")
        self.assertTrue(
            doc_requirements.memory_exists("feature/FEATURE_TESTS", self.project_root))

    def test_missing_memory_does_not_exist(self):
        self.assertFalse(
            doc_requirements.memory_exists("dev/DEV_TESTS", self.project_root))

    def test_aliased_root_memory_exists_with_alias_prefix(self):
        other_dir = tempfile.mkdtemp()
        _write(os.path.join(other_dir, "feature", "FEATURE_TESTS.md"), "# x")
        conf_path = os.path.join(self.project_root, ".serena", "memory-paths.conf")
        _write(conf_path, f"em={other_dir}\n")
        self.assertTrue(
            doc_requirements.memory_exists("em/feature/FEATURE_TESTS", self.project_root))
        # Unaliased name must NOT resolve against the aliased root.
        self.assertFalse(
            doc_requirements.memory_exists("feature/FEATURE_TESTS", self.project_root))


class ParsePathsFrontmatterTests(unittest.TestCase):
    def test_no_frontmatter_returns_empty(self):
        self.assertEqual(doc_requirements.parse_paths_frontmatter("# just a heading"), [])

    def test_frontmatter_with_no_paths_key_returns_empty(self):
        text = "---\nname: X\ndescription: something\n---\nbody"
        self.assertEqual(doc_requirements.parse_paths_frontmatter(text), [])

    def test_top_level_block_list(self):
        text = (
            "---\n"
            "name: FEATURE_X\n"
            "paths:\n"
            '  - "feature/**/*.py"\n'
            "  - foo/*.md\n"
            "---\n"
            "body"
        )
        self.assertEqual(
            doc_requirements.parse_paths_frontmatter(text),
            ["feature/**/*.py", "foo/*.md"])

    def test_top_level_inline_list(self):
        text = '---\npaths: ["a/*.py", "b/*.md"]\n---\nbody'
        self.assertEqual(
            doc_requirements.parse_paths_frontmatter(text), ["a/*.py", "b/*.md"])

    def test_nested_metadata_paths_block_list(self):
        text = (
            "---\n"
            "name: X\n"
            "metadata:\n"
            "  type: feature\n"
            "  paths:\n"
            "    - x/*.py\n"
            "    - y/**/*.js\n"
            "---\n"
            "body"
        )
        self.assertEqual(
            doc_requirements.parse_paths_frontmatter(text), ["x/*.py", "y/**/*.js"])

    def test_nested_metadata_paths_inline_list(self):
        text = (
            "---\n"
            "metadata:\n"
            '  paths: ["x/*.py"]\n'
            "---\n"
            "body"
        )
        self.assertEqual(doc_requirements.parse_paths_frontmatter(text), ["x/*.py"])

    def test_top_level_and_nested_combined(self):
        text = (
            "---\n"
            "paths:\n"
            "  - a/*.py\n"
            "metadata:\n"
            "  paths:\n"
            "    - b/*.py\n"
            "---\n"
            "body"
        )
        self.assertEqual(
            sorted(doc_requirements.parse_paths_frontmatter(text)), ["a/*.py", "b/*.py"])

    def test_unterminated_frontmatter_returns_empty(self):
        text = "---\npaths:\n  - a/*.py\nno closing fence"
        self.assertEqual(doc_requirements.parse_paths_frontmatter(text), [])


class GlobMatchingTests(DocRequirementsTestCase):
    def test_double_star_matches_zero_or_more_dirs(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_X.md"),
               '---\nname: X\npaths:\n  - "hooks/**/*.py"\n---\nbody')
        required = doc_requirements.required_docs_for_path(
            "hooks/core/foo.py", self.project_root)
        self.assertIn("feature/FEATURE_X", required)
        required2 = doc_requirements.required_docs_for_path(
            "hooks/foo.py", self.project_root)
        self.assertIn("feature/FEATURE_X", required2)

    def test_single_star_does_not_cross_directories(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_Y.md"),
               '---\nname: Y\npaths:\n  - "hooks/*.py"\n---\nbody')
        required = doc_requirements.required_docs_for_path(
            "hooks/core/foo.py", self.project_root)
        self.assertNotIn("feature/FEATURE_Y", required)
        required2 = doc_requirements.required_docs_for_path(
            "hooks/foo.py", self.project_root)
        self.assertIn("feature/FEATURE_Y", required2)

    def test_absolute_path_made_relative_to_project_root(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_Z.md"),
               '---\nname: Z\npaths:\n  - "src/*.py"\n---\nbody')
        abs_path = os.path.join(self.project_root, "src", "mod.py")
        required = doc_requirements.required_docs_for_path(abs_path, self.project_root)
        self.assertIn("feature/FEATURE_Z", required)


class RequiredDocsForPathTests(DocRequirementsTestCase):
    def test_no_matching_memory_returns_empty(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_X.md"),
               '---\nname: X\npaths:\n  - "other/*.py"\n---\nbody')
        self.assertEqual(
            doc_requirements.required_docs_for_path("src/mod.py", self.project_root), [])

    def test_memory_without_frontmatter_never_required(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_NOFM.md"), "# No front matter here\nbody text")
        self.assertEqual(
            doc_requirements.required_docs_for_path("anything.py", self.project_root), [])

    def test_test_artifact_adds_test_docs_when_present(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_TESTS.md"), "# tests")
        _write(os.path.join(self.project_root, ".serena", "memory", "dev",
                             "DEV_TESTS.md"), "# dev tests")
        required = doc_requirements.required_docs_for_path(
            "tests/test_foo.py", self.project_root)
        self.assertIn("feature/FEATURE_TESTS", required)
        self.assertIn("dev/DEV_TESTS", required)

    def test_missing_dev_tests_filtered_out(self):
        # Only FEATURE_TESTS exists; DEV_TESTS must NOT be demanded.
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_TESTS.md"), "# tests")
        required = doc_requirements.required_docs_for_path(
            "tests/test_foo.py", self.project_root)
        self.assertIn("feature/FEATURE_TESTS", required)
        self.assertNotIn("dev/DEV_TESTS", required)

    def test_non_test_path_does_not_add_test_docs(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_TESTS.md"), "# tests")
        required = doc_requirements.required_docs_for_path(
            "src/mod.py", self.project_root)
        self.assertNotIn("feature/FEATURE_TESTS", required)

    def test_result_sorted_and_deduplicated(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_B.md"),
               '---\npaths:\n  - "src/*.py"\n---\nbody')
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_A.md"),
               '---\npaths:\n  - "src/*.py"\n---\nbody')
        required = doc_requirements.required_docs_for_path("src/mod.py", self.project_root)
        self.assertEqual(required, sorted(set(required)))
        self.assertEqual(required, ["feature/FEATURE_A", "feature/FEATURE_B"])

    def test_index_is_cached_per_project_root(self):
        mem_path = os.path.join(self.project_root, ".serena", "memory", "feature",
                                 "FEATURE_X.md")
        _write(mem_path, '---\npaths:\n  - "src/*.py"\n---\nbody')
        first = doc_requirements.required_docs_for_path("src/mod.py", self.project_root)
        self.assertIn("feature/FEATURE_X", first)
        # Mutate the memory after first scan — cached index must NOT pick it up.
        _write(mem_path, '---\npaths:\n  - "other/*.py"\n---\nbody')
        second = doc_requirements.required_docs_for_path("src/mod.py", self.project_root)
        self.assertEqual(first, second)


class UnreadRequiredDocsTests(DocRequirementsTestCase):
    def test_unread_returns_required_minus_read(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_TESTS.md"), "# tests")
        _write(os.path.join(self.project_root, ".serena", "memory", "dev",
                             "DEV_TESTS.md"), "# dev tests")
        unread = doc_requirements.unread_required_docs(
            "tests/test_foo.py", self.project_root, {"feature/feature_tests"})
        self.assertEqual(unread, ["dev/DEV_TESTS"])

    def test_all_read_returns_empty(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_TESTS.md"), "# tests")
        unread = doc_requirements.unread_required_docs(
            "tests/test_foo.py", self.project_root, {"feature/feature_tests"})
        self.assertEqual(unread, [])

    def test_none_read_returns_all_required(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_TESTS.md"), "# tests")
        unread = doc_requirements.unread_required_docs(
            "tests/test_foo.py", self.project_root, set())
        self.assertEqual(unread, ["feature/FEATURE_TESTS"])

    def test_empty_read_names_arg(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_TESTS.md"), "# tests")
        unread = doc_requirements.unread_required_docs(
            "tests/test_foo.py", self.project_root, None)
        self.assertEqual(unread, ["feature/FEATURE_TESTS"])


class FallbackDevDocsTests(DocRequirementsTestCase):
    def test_php_fallback_fires_when_dev_php_exists(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "dev",
                             "DEV_PHP.md"), "# php standards")
        result = doc_requirements.fallback_dev_docs("src/App.php", self.project_root)
        self.assertEqual(result, ["dev/DEV_PHP"])

    def test_unknown_extension_returns_nothing(self):
        result = doc_requirements.fallback_dev_docs("src/main.xyz", self.project_root)
        self.assertEqual(result, [])

    def test_known_extension_no_memories_present_returns_nothing(self):
        result = doc_requirements.fallback_dev_docs("src/App.php", self.project_root)
        self.assertEqual(result, [])

    def test_blade_php_picks_bladeone_and_php_when_both_exist(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "dev",
                             "DEV_BLADEONE.md"), "# bladeone")
        _write(os.path.join(self.project_root, ".serena", "memory", "dev",
                             "DEV_PHP.md"), "# php")
        result = doc_requirements.fallback_dev_docs("views/home.blade.php", self.project_root)
        self.assertEqual(result, ["dev/DEV_BLADEONE", "dev/DEV_PHP"])

    def test_blade_php_only_php_exists_falls_through_candidates(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "dev",
                             "DEV_PHP.md"), "# php")
        result = doc_requirements.fallback_dev_docs("views/home.blade.php", self.project_root)
        self.assertEqual(result, ["dev/DEV_PHP"])

    def test_feature_dev_standards_added_only_when_it_exists(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "dev",
                             "DEV_PYTHON.md"), "# python")
        result_without = doc_requirements.fallback_dev_docs("src/main.py", self.project_root)
        self.assertEqual(result_without, ["dev/DEV_PYTHON"])

        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_DEV_STANDARDS.md"), "# standards")
        result_with = doc_requirements.fallback_dev_docs("src/main.py", self.project_root)
        self.assertEqual(result_with, ["dev/DEV_PYTHON", "feature/FEATURE_DEV_STANDARDS"])

    def test_feature_dev_standards_not_added_when_no_dev_candidate_exists(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_DEV_STANDARDS.md"), "# standards")
        result = doc_requirements.fallback_dev_docs("src/main.py", self.project_root)
        self.assertEqual(result, [])

    def test_js_variants_use_javascript_candidates(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "dev",
                             "DEV_JAVASCRIPT.md"), "# js")
        for fname in ("a.js", "a.jsx", "a.mjs", "a.cjs"):
            result = doc_requirements.fallback_dev_docs(fname, self.project_root)
            self.assertEqual(result, ["dev/DEV_JAVASCRIPT"], fname)


class RequiredDocsForPathFallbackTests(DocRequirementsTestCase):
    def test_fallback_fires_when_no_paths_matched_dev_memory(self):
        # DEV_PHP has NO paths: front-matter -> would never be required
        # without the extension fallback.
        _write(os.path.join(self.project_root, ".serena", "memory", "dev",
                             "DEV_PHP.md"), "# php standards, no paths: block")
        required = doc_requirements.required_docs_for_path(
            "src/App.php", self.project_root)
        self.assertIn("dev/DEV_PHP", required)

    def test_fallback_does_not_fire_when_paths_matched_dev_already_present(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "dev",
                             "DEV_PHP.md"),
               '---\npaths:\n  - "src/*.php"\n---\n# php standards')
        # A second dev memory exists for the SAME extension via the
        # fallback map but must NOT be added, since a paths:-matched dev/*
        # memory already covers this file.
        _write(os.path.join(self.project_root, ".serena", "memory", "dev",
                             "DEV_OTHERPHP.md"), "# irrelevant, never a fallback candidate")
        required = doc_requirements.required_docs_for_path(
            "src/App.php", self.project_root)
        self.assertEqual(required, ["dev/DEV_PHP"])

    def test_blade_php_end_to_end_picks_bladeone_and_php(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "dev",
                             "DEV_BLADEONE.md"), "# bladeone")
        _write(os.path.join(self.project_root, ".serena", "memory", "dev",
                             "DEV_PHP.md"), "# php")
        required = doc_requirements.required_docs_for_path(
            "views/home.blade.php", self.project_root)
        self.assertIn("dev/DEV_BLADEONE", required)
        self.assertIn("dev/DEV_PHP", required)

    def test_feature_dev_standards_added_only_when_exists_end_to_end(self):
        _write(os.path.join(self.project_root, ".serena", "memory", "dev",
                             "DEV_PYTHON.md"), "# python")
        required_without = doc_requirements.required_docs_for_path(
            "src/mod.py", self.project_root)
        self.assertNotIn("feature/FEATURE_DEV_STANDARDS", required_without)

        doc_requirements._INDEX_CACHE.clear()
        _write(os.path.join(self.project_root, ".serena", "memory", "feature",
                             "FEATURE_DEV_STANDARDS.md"), "# standards")
        required_with = doc_requirements.required_docs_for_path(
            "src/mod.py", self.project_root)
        self.assertIn("feature/FEATURE_DEV_STANDARDS", required_with)

    def test_unknown_extension_adds_nothing(self):
        required = doc_requirements.required_docs_for_path(
            "src/mod.xyz", self.project_root)
        self.assertEqual(required, [])


class ShippedRootPluginScopingTests(DocRequirementsTestCase):
    def _write_shipped_feature_swe(self, plugin_dir):
        _write(os.path.join(plugin_dir, "memories", "feature", "FEATURE_SWE.md"),
               '---\nname: SWE\npaths:\n  - "hooks/**/*.py"\n---\nbody')

    def _write_plugin_json(self, repo_dir, name):
        _write(os.path.join(repo_dir, ".claude-plugin", "plugin.json"),
               f'{{"name": "{name}"}}')

    def test_shipped_globs_ignored_in_non_plugin_project(self):
        plugin_dir = tempfile.mkdtemp()
        self._write_shipped_feature_swe(plugin_dir)
        self._write_plugin_json(plugin_dir, "swe")
        os.environ["CLAUDE_PLUGIN_ROOT"] = plugin_dir

        # self.project_root is an unrelated project with NO plugin.json —
        # must NOT be told it needs FEATURE_SWE for a hooks/ file.
        required = doc_requirements.required_docs_for_path(
            "hooks/anything.py", self.project_root)
        self.assertNotIn("feature/FEATURE_SWE", required)

    def test_shipped_globs_honored_when_project_is_the_plugin_repo(self):
        plugin_dir = tempfile.mkdtemp()
        self._write_shipped_feature_swe(plugin_dir)
        self._write_plugin_json(plugin_dir, "swe")
        os.environ["CLAUDE_PLUGIN_ROOT"] = plugin_dir

        # project_root IS the plugin source repo: same plugin.json name.
        self._write_plugin_json(self.project_root, "swe")
        doc_requirements._INDEX_CACHE.clear()
        required = doc_requirements.required_docs_for_path(
            "hooks/anything.py", self.project_root)
        self.assertIn("feature/FEATURE_SWE", required)

    def test_mismatched_plugin_name_does_not_scope_in(self):
        plugin_dir = tempfile.mkdtemp()
        self._write_shipped_feature_swe(plugin_dir)
        self._write_plugin_json(plugin_dir, "swe")
        os.environ["CLAUDE_PLUGIN_ROOT"] = plugin_dir

        # project_root has A plugin.json, but a DIFFERENT name.
        self._write_plugin_json(self.project_root, "some-other-plugin")
        doc_requirements._INDEX_CACHE.clear()
        required = doc_requirements.required_docs_for_path(
            "hooks/anything.py", self.project_root)
        self.assertNotIn("feature/FEATURE_SWE", required)


class IsTestTargetTests(unittest.TestCase):
    def test_tests_dir_detected(self):
        self.assertTrue(doc_requirements.is_test_target("tests/test_foo.py"))

    def test_e2e_dir_detected(self):
        self.assertTrue(doc_requirements.is_test_target("e2e/spec.js"))

    def test_test_prefixed_py_detected(self):
        self.assertTrue(doc_requirements.is_test_target("test_something.py"))

    def test_dot_test_js_detected(self):
        self.assertTrue(doc_requirements.is_test_target("component.test.tsx"))

    def test_feature_file_detected(self):
        self.assertTrue(doc_requirements.is_test_target("specs/login.feature"))

    def test_non_test_source_not_detected(self):
        self.assertFalse(doc_requirements.is_test_target("src/main.py"))


if __name__ == "__main__":
    unittest.main()
