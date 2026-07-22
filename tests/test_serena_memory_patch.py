"""Tests for scripts/serena_memory_patch.py pure helpers.

Loaded via load_serena_patch() which stubs serena.* and neutralizes top_level so
no MCP server starts. Only the four pure helpers and module-level constants are
exercised:
  - _derive_prefix
  - _derive_type
  - _normalize_name
  - _ensure_front_matter
plus the _PREFIX_TO_TYPE and _MEMORIES_DIR_PREFIXES constants.

All behavior asserted here was verified against the actual source.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import load_serena_patch  # noqa: E402

# Load once at module import — the patch module has no path-resolving side effects
# in its pure helpers, so a single shared instance is safe and deterministic.
mod = load_serena_patch()


class SmokeImportTest(unittest.TestCase):
    def test_module_loads_and_exposes_helpers(self):
        # load_serena_patch must succeed without launching a server.
        self.assertTrue(callable(mod._derive_prefix))
        self.assertTrue(callable(mod._derive_type))
        self.assertTrue(callable(mod._normalize_name))
        self.assertTrue(callable(mod._ensure_front_matter))
        self.assertIsInstance(mod._PREFIX_TO_TYPE, dict)
        self.assertIsInstance(mod._MEMORIES_DIR_PREFIXES, frozenset)


class ConstantsTest(unittest.TestCase):
    def test_prefix_to_type_mapping(self):
        m = mod._PREFIX_TO_TYPE
        # Targeted asserts on documented mappings (not exhaustive).
        self.assertEqual(m["ref"], "reference")
        self.assertEqual(m["feature"], "feature")
        self.assertEqual(m["dom"], "domain")
        self.assertEqual(m["sys"], "system")
        self.assertEqual(m["arch"], "architecture")
        self.assertEqual(m["spec"], "spec")
        self.assertEqual(m["wf"], "workflow")
        self.assertEqual(m["feedback"], "feedback")
        self.assertEqual(m["project"], "project")
        self.assertEqual(m["report"], "report")
        self.assertEqual(m["research"], "research")
        self.assertEqual(m["content"], "content")

    def test_memories_dir_prefixes(self):
        # WM_ and LITE_ live flat in .serena/memories/ (no swe/ subdir).
        self.assertEqual(mod._MEMORIES_DIR_PREFIXES, frozenset(["wm", "lite"]))
        self.assertIn("wm", mod._MEMORIES_DIR_PREFIXES)
        self.assertIn("lite", mod._MEMORIES_DIR_PREFIXES)
        self.assertNotIn("dom", mod._MEMORIES_DIR_PREFIXES)

    def test_no_frontmatter_prefixes(self):
        # Documented exemptions from auto front-matter on save.
        self.assertEqual(
            mod._NO_FRONTMATTER_PREFIXES, frozenset(["wm", "lite", "wf", "claude"])
        )


class DerivePrefixTest(unittest.TestCase):
    def test_standard_prefixes(self):
        self.assertEqual(mod._derive_prefix("DOM_X"), "dom")
        self.assertEqual(mod._derive_prefix("FEATURE_SWE"), "feature")
        self.assertEqual(mod._derive_prefix("SYS_BUILDER_WYSIWYG"), "sys")
        self.assertEqual(mod._derive_prefix("SPEC_EMAIL"), "spec")

    def test_prefix_taken_from_base_not_directory(self):
        # A path prefix is stripped; the base name's first segment decides.
        self.assertEqual(mod._derive_prefix("feature/DOM_X"), "dom")
        self.assertEqual(mod._derive_prefix("dom/DOM_X"), "dom")
        self.assertEqual(mod._derive_prefix("ref/REF_WM"), "ref")

    def test_md_suffix_stripped(self):
        self.assertEqual(mod._derive_prefix("WM_abc123.md"), "wm")
        self.assertEqual(mod._derive_prefix("dom/DOM_X.md"), "dom")

    def test_no_underscore_returns_none(self):
        self.assertIsNone(mod._derive_prefix("MEMORY"))
        self.assertIsNone(mod._derive_prefix("nounderscoreatall"))

    def test_leading_underscore_private_returns_none(self):
        self.assertIsNone(mod._derive_prefix("_private"))
        self.assertIsNone(mod._derive_prefix("_HIDDEN_X"))

    def test_lowercase_result(self):
        # First segment is lowercased regardless of source casing.
        self.assertEqual(mod._derive_prefix("Dom_X"), "dom")
        self.assertEqual(mod._derive_prefix("lite_MODE_x"), "lite")


class DeriveTypeTest(unittest.TestCase):
    def test_known_prefix_maps_to_type(self):
        self.assertEqual(mod._derive_type("DOM_X"), "domain")
        self.assertEqual(mod._derive_type("FEATURE_SWE"), "feature")
        self.assertEqual(mod._derive_type("SPEC_X"), "spec")
        self.assertEqual(mod._derive_type("ref/REF_WM"), "reference")
        self.assertEqual(mod._derive_type("SYS_X"), "system")
        self.assertEqual(mod._derive_type("wf/WF_INIT"), "workflow")

    def test_unlisted_prefix_passes_through_lowercased(self):
        # A prefix not in _PREFIX_TO_TYPE uses itself (lowercased) as the type.
        self.assertEqual(mod._derive_type("UNKNOWNPFX_Y"), "unknownpfx")
        # wm is a valid derived prefix but is NOT in _PREFIX_TO_TYPE -> passthrough.
        self.assertEqual(mod._derive_type("WM_abc"), "wm")
        self.assertEqual(mod._derive_type("LITE_X"), "lite")

    def test_unclassifiable_name_returns_none(self):
        self.assertIsNone(mod._derive_type("MEMORY"))
        self.assertIsNone(mod._derive_type("_private"))


class NormalizeNameTest(unittest.TestCase):
    def test_missing_prefix_gets_swe_subdir(self):
        self.assertEqual(mod._normalize_name("DOM_X"), "dom/DOM_X")
        self.assertEqual(mod._normalize_name("FEATURE_SWE"), "feature/FEATURE_SWE")

    def test_wrong_prefix_corrected(self):
        self.assertEqual(mod._normalize_name("feature/DOM_X"), "dom/DOM_X")

    def test_already_correct_unchanged(self):
        self.assertEqual(mod._normalize_name("dom/DOM_X"), "dom/DOM_X")
        self.assertEqual(mod._normalize_name("ref/REF_WM"), "ref/REF_WM")

    def test_wm_and_lite_stay_flat(self):
        # WM_ and LITE_ live flat in .serena/memories/ — base name only, no subdir.
        self.assertEqual(mod._normalize_name("WM_abc123"), "WM_abc123")
        self.assertEqual(mod._normalize_name("LITE_MODE_abc123"), "LITE_MODE_abc123")

    def test_md_suffix_stripped(self):
        self.assertEqual(mod._normalize_name("LITE_MODE_abc123.md"), "LITE_MODE_abc123")
        self.assertEqual(mod._normalize_name("MEMORY.md"), "MEMORY")
        self.assertEqual(mod._normalize_name("dom/DOM_X.md"), "dom/DOM_X")

    def test_unclassifiable_passthrough(self):
        # No derivable prefix -> return the cleaned name unchanged (minus .md).
        self.assertEqual(mod._normalize_name("MEMORY"), "MEMORY")
        self.assertEqual(mod._normalize_name("_private"), "_private")
        self.assertEqual(mod._normalize_name("nounderscoreatall"), "nounderscoreatall")


class EnsureFrontMatterTest(unittest.TestCase):
    def test_no_front_matter_injects_block_with_h1_name(self):
        content = "# My Title\n\nSome body content."
        result = mod._ensure_front_matter("DOM_X", content)
        self.assertTrue(result.startswith("---\n"))
        self.assertIn("name: My Title", result)
        self.assertIn(
            "description: TODO — one sentence describing what this memory is about.",
            result,
        )
        self.assertIn("metadata:\n  type: domain", result)
        # Original body preserved at the end.
        self.assertTrue(result.endswith(content))

    def test_no_front_matter_no_h1_uses_base_name(self):
        content = "just body no heading"
        result = mod._ensure_front_matter("DOM_X", content)
        self.assertIn("name: DOM_X", result)
        self.assertIn("metadata:\n  type: domain", result)
        self.assertTrue(result.endswith(content))

    def test_no_front_matter_base_name_strips_path_and_md(self):
        content = "plain body"
        result = mod._ensure_front_matter("feature/FEATURE_SWE.md", content)
        # Base name is FEATURE_SWE (path + .md stripped), type from prefix.
        self.assertIn("name: FEATURE_SWE", result)
        self.assertIn("metadata:\n  type: feature", result)

    def test_existing_front_matter_missing_type_gets_type_appended(self):
        content = "---\nname: Foo\ndescription: bar\n---\n\nbody"
        result = mod._ensure_front_matter("DOM_X", content)
        # Author's name/description untouched.
        self.assertIn("name: Foo", result)
        self.assertIn("description: bar", result)
        # Nested metadata.type injected before the closing fence.
        self.assertIn("metadata:\n  type: domain", result)
        # Body preserved.
        self.assertTrue(result.rstrip().endswith("body"))
        self.assertNotEqual(result, content)

    def test_existing_front_matter_with_flat_type_unchanged(self):
        content = "---\nname: Foo\ntype: domain\n---\n\nbody"
        result = mod._ensure_front_matter("DOM_X", content)
        self.assertEqual(result, content)

    def test_existing_front_matter_with_nested_type_unchanged(self):
        content = "---\nname: Foo\nmetadata:\n  type: domain\n---\n\nbody"
        result = mod._ensure_front_matter("DOM_X", content)
        self.assertEqual(result, content)

    def test_unclassifiable_name_passthrough(self):
        content = "anything here"
        result = mod._ensure_front_matter("MEMORY", content)
        self.assertEqual(result, content)

    def test_malformed_unterminated_front_matter_left_alone(self):
        # Starts with --- but has no closing "\n---" fence -> don't risk mangling.
        content = "---\nname: Foo\nno closing fence"
        result = mod._ensure_front_matter("DOM_X", content)
        self.assertEqual(result, content)

    def test_bare_triple_dash_left_alone(self):
        # "---" alone has no "\n---" separator -> malformed guard leaves it as-is.
        result = mod._ensure_front_matter("DOM_X", "---")
        self.assertEqual(result, "---")

    def test_empty_content_classifiable_name_injects_block(self):
        result = mod._ensure_front_matter("DOM_X", "")
        self.assertTrue(result.startswith("---\n"))
        self.assertIn("name: DOM_X", result)
        self.assertIn("metadata:\n  type: domain", result)

    def test_empty_content_unclassifiable_name_passthrough(self):
        result = mod._ensure_front_matter("MEMORY", "")
        self.assertEqual(result, "")

    def test_unlisted_prefix_uses_prefix_as_type(self):
        # Type falls back to the lowercased prefix for names not in _PREFIX_TO_TYPE.
        content = "body"
        result = mod._ensure_front_matter("UNKNOWNPFX_Y", content)
        self.assertIn("metadata:\n  type: unknownpfx", result)


if __name__ == "__main__":
    unittest.main()
