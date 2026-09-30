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

    def tearDown(self):
        doc_requirements._INDEX_CACHE.clear()
        self.tmp.cleanup()


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
