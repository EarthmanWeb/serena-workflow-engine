"""Tests for swe_hooks.core.wm_validator — a fully pure module.

Covers WMFormatValidator.validate_filename / validate_content /
validate_session_ownership, the get_validator() singleton, and the
module-level constants (REQUIRED_SECTIONS, RECOMMENDED_SECTIONS,
FILENAME_PATTERN).
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_core, reset_caches  # noqa: E402

mod = import_core("swe_hooks.core.wm_validator")


class ConstantsTest(unittest.TestCase):
    def test_required_sections_exact(self):
        self.assertEqual(
            mod.WMFormatValidator.REQUIRED_SECTIONS,
            ['Workflow Context', 'Current Task'],
        )

    def test_recommended_sections_exact(self):
        self.assertEqual(
            mod.WMFormatValidator.RECOMMENDED_SECTIONS,
            ['Progress', 'Previous Task'],
        )

    def test_filename_pattern_is_compiled_regex(self):
        # Constant is a pre-compiled pattern object with the documented source.
        self.assertIsInstance(mod.WMFormatValidator.FILENAME_PATTERN, re.Pattern)
        self.assertEqual(
            mod.WMFormatValidator.FILENAME_PATTERN.pattern,
            r'^WM_([a-f0-9]{8})(?:\.md)?$',
        )


class ValidateFilenameTest(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self.v = mod.WMFormatValidator()

    def tearDown(self):
        reset_caches()

    def test_valid_with_md_extension(self):
        ok, err, sid = self.v.validate_filename("WM_abc12345.md")
        self.assertTrue(ok)
        self.assertEqual(err, "")
        self.assertEqual(sid, "abc12345")

    def test_valid_without_md_extension(self):
        ok, err, sid = self.v.validate_filename("WM_abc12345")
        self.assertTrue(ok)
        self.assertEqual(err, "")
        self.assertEqual(sid, "abc12345")

    def test_valid_full_hex_range(self):
        ok, err, sid = self.v.validate_filename("WM_0f9e8d7c.md")
        self.assertTrue(ok)
        self.assertEqual(sid, "0f9e8d7c")

    def test_reject_uppercase_hex(self):
        # Pattern is lowercase-only [a-f0-9]; uppercase must fail.
        ok, err, sid = self.v.validate_filename("WM_ABC12345.md")
        self.assertFalse(ok)
        self.assertIsNone(sid)
        self.assertIn("Invalid filename format", err)

    def test_reject_too_short_session(self):
        ok, err, sid = self.v.validate_filename("WM_abc1234.md")
        self.assertFalse(ok)
        self.assertIsNone(sid)

    def test_reject_too_long_session(self):
        ok, err, sid = self.v.validate_filename("WM_abc123456.md")
        self.assertFalse(ok)
        self.assertIsNone(sid)

    def test_reject_wrong_extension(self):
        ok, err, sid = self.v.validate_filename("WM_abc12345.txt")
        self.assertFalse(ok)
        self.assertIsNone(sid)

    def test_reject_missing_prefix(self):
        ok, err, sid = self.v.validate_filename("abc12345.md")
        self.assertFalse(ok)
        self.assertIsNone(sid)

    def test_reject_non_hex_char(self):
        # 'g' is not in [a-f0-9]
        ok, err, sid = self.v.validate_filename("WM_abc12g45.md")
        self.assertFalse(ok)
        self.assertIsNone(sid)

    def test_reject_empty_string(self):
        ok, err, sid = self.v.validate_filename("")
        self.assertFalse(ok)
        self.assertIsNone(sid)
        self.assertIn("Invalid filename format", err)

    def test_reject_prefix_only(self):
        ok, err, sid = self.v.validate_filename("WM_.md")
        self.assertFalse(ok)
        self.assertIsNone(sid)


class ValidateContentTest(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self.v = mod.WMFormatValidator()

    def tearDown(self):
        reset_caches()

    def _full_valid_content(self):
        return (
            "## Workflow Context\n"
            "Current State: WF_EXECUTE\n"
            "Session ID: abc12345\n"
            "\n"
            "## Current Task\n"
            "Do the thing.\n"
        )

    def test_valid_content_all_sections_and_fields(self):
        ok, errors = self.v.validate_content(self._full_valid_content())
        self.assertTrue(ok)
        self.assertEqual(errors, [])

    def test_valid_with_markdown_bold_fields(self):
        # Field regexes allow trailing ** before the colon.
        content = (
            "## Workflow Context\n"
            "**Current State**: WF_INIT\n"
            "**Session ID**: deadbeef\n"
            "## Current Task\n"
            "task body\n"
        )
        ok, errors = self.v.validate_content(content)
        self.assertTrue(ok)
        self.assertEqual(errors, [])

    def test_h3_header_recognized_for_sections_and_fields(self):
        content = (
            "### Workflow Context\n"
            "Current State: WF_RESEARCH\n"
            "Session ID: 0011aabb\n"
            "### Current Task\n"
            "body\n"
        )
        ok, errors = self.v.validate_content(content)
        self.assertTrue(ok)
        self.assertEqual(errors, [])

    def test_missing_both_required_sections(self):
        ok, errors = self.v.validate_content("just some prose, no sections")
        self.assertFalse(ok)
        self.assertIn("Missing required section: Workflow Context", errors)
        self.assertIn("Missing required section: Current Task", errors)

    def test_missing_current_task_only(self):
        content = (
            "## Workflow Context\n"
            "Current State: WF_INIT\n"
            "Session ID: abc12345\n"
        )
        ok, errors = self.v.validate_content(content)
        self.assertFalse(ok)
        self.assertIn("Missing required section: Current Task", errors)
        self.assertNotIn("Missing required section: Workflow Context", errors)

    def test_bold_section_header_satisfies_required_but_skips_field_checks(self):
        # **Workflow Context** counts as the section (via '**{section}**'),
        # but the field checks only fire for '## ' or '### ' headers, so the
        # missing Current State / Session ID fields are NOT flagged here.
        content = (
            "**Workflow Context**\n"
            "no fields here\n"
            "## Current Task\n"
            "body\n"
        )
        ok, errors = self.v.validate_content(content)
        self.assertTrue(ok)
        self.assertEqual(errors, [])

    def test_workflow_context_present_but_missing_current_state_field(self):
        content = (
            "## Workflow Context\n"
            "Session ID: abc12345\n"
            "## Current Task\n"
            "body\n"
        )
        ok, errors = self.v.validate_content(content)
        self.assertFalse(ok)
        self.assertIn("Workflow Context missing 'Current State:' field", errors)
        self.assertNotIn("Workflow Context missing 'Session ID:' field", errors)

    def test_workflow_context_present_but_missing_session_id_field(self):
        content = (
            "## Workflow Context\n"
            "Current State: WF_EXECUTE\n"
            "## Current Task\n"
            "body\n"
        )
        ok, errors = self.v.validate_content(content)
        self.assertFalse(ok)
        self.assertIn("Workflow Context missing 'Session ID:' field", errors)
        self.assertNotIn("Workflow Context missing 'Current State:' field", errors)

    def test_workflow_context_present_but_missing_both_fields(self):
        content = (
            "## Workflow Context\n"
            "nothing useful\n"
            "## Current Task\n"
            "body\n"
        )
        ok, errors = self.v.validate_content(content)
        self.assertFalse(ok)
        self.assertIn("Workflow Context missing 'Current State:' field", errors)
        self.assertIn("Workflow Context missing 'Session ID:' field", errors)

    def test_empty_content(self):
        ok, errors = self.v.validate_content("")
        self.assertFalse(ok)
        # Both required sections absent; no field checks because header absent.
        self.assertEqual(
            sorted(errors),
            sorted([
                "Missing required section: Workflow Context",
                "Missing required section: Current Task",
            ]),
        )

    def test_session_field_matches_plain_session_word(self):
        # Field regex is Session(?:\s+ID)?\*?\*?: so 'Session:' (no 'ID') satisfies it.
        content = (
            "## Workflow Context\n"
            "Current State: WF_INIT\n"
            "Session: abc12345\n"
            "## Current Task\n"
            "body\n"
        )
        ok, errors = self.v.validate_content(content)
        self.assertTrue(ok)
        self.assertEqual(errors, [])


class ValidateSessionOwnershipTest(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self.v = mod.WMFormatValidator()

    def tearDown(self):
        reset_caches()

    def test_match_session_id_field(self):
        ok, err = self.v.validate_session_ownership("Session ID: abc12345", "abc12345")
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_match_plain_session_field(self):
        ok, err = self.v.validate_session_ownership("Session: abc12345", "abc12345")
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_match_case_insensitive_expected_uppercase(self):
        # Content id is lowercased before compare; expected is lowercased too.
        ok, err = self.v.validate_session_ownership("Session ID: abc12345", "ABC12345")
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_match_case_insensitive_content_uppercase(self):
        # IGNORECASE lets [a-f0-9] match A-F; group is then lowercased.
        ok, err = self.v.validate_session_ownership("Session: DEADBEEF", "deadbeef")
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_mismatch(self):
        ok, err = self.v.validate_session_ownership("Session ID: abc12345", "def67890")
        self.assertFalse(ok)
        self.assertEqual(err, "Session mismatch: content has abc12345, expected def67890")

    def test_missing_session_id_in_content(self):
        ok, err = self.v.validate_session_ownership("no session anywhere", "abc12345")
        self.assertFalse(ok)
        self.assertEqual(err, "No session ID found in content")

    def test_empty_content(self):
        ok, err = self.v.validate_session_ownership("", "abc12345")
        self.assertFalse(ok)
        self.assertEqual(err, "No session ID found in content")

    def test_session_id_extracted_from_larger_document(self):
        content = (
            "# Working Memory\n"
            "## Workflow Context\n"
            "Current State: WF_EXECUTE\n"
            "Session ID: 0a1b2c3d\n"
            "## Current Task\n"
            "stuff\n"
        )
        ok, err = self.v.validate_session_ownership(content, "0a1b2c3d")
        self.assertTrue(ok)
        self.assertEqual(err, "")


class GetValidatorSingletonTest(unittest.TestCase):
    def setUp(self):
        reset_caches()

    def tearDown(self):
        reset_caches()

    def test_returns_wmformatvalidator_instance(self):
        v = mod.get_validator()
        self.assertIsInstance(v, mod.WMFormatValidator)

    def test_returns_same_object_twice(self):
        first = mod.get_validator()
        second = mod.get_validator()
        self.assertIs(first, second)

    def test_reset_caches_clears_singleton(self):
        first = mod.get_validator()
        reset_caches()
        second = mod.get_validator()
        # After clearing _validator, a fresh instance is created.
        self.assertIsNot(first, second)


if __name__ == "__main__":
    unittest.main()
