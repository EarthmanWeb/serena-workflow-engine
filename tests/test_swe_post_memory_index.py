"""Tests for hooks/post/swe_post_memory_index.py.

Covers the terse-index enforcement considerations:
  - SKIP_PREFIXES matches ONLY the non-indexed categories (and nothing else).
  - NON_INDEXED_CATEGORIES / leaked-category detection.
  - Size budget (lines + bytes) warnings.
  - Over-long index-entry warnings.
  - memory_name_in_index basename matching.
  - A clean, in-budget index produces NO warnings (no false positives).

Also covers (Change Set H) hooks/pre/swe_pre_memory_index_gate.py's obligations-
digest enforcement (missing_obligations_reason / obligations_denial_for_write):
that check is unrelated to this file's namesake hook, but is grouped here per
the Change Set H file-ownership split (see TestObligationsDigestGate below).

Stdlib unittest only.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_hook  # noqa: E402

mod = import_hook("post/swe_post_memory_index")
gate_mod = import_hook("pre/swe_pre_memory_index_gate")


# A minimal, healthy index used as the "clean" baseline.
CLEAN_INDEX = """## Response & Style
- [Response Format](feedback/FEEDBACK_RESPONSE_FORMAT.md) — functional phrasing only

## Features
- [Feature Index](index/INDEX_FEATURES.md) — feature registry
- [CRM](feature/FEATURE_CRM.md) — CRM core

## Reference
- [Dev Standards](ref/REF_DEV_STANDARDS.md) — coding conventions
"""


class TestSkipPrefixes(unittest.TestCase):
    """SKIP_PREFIXES must match exactly the never-indexed names — no more, no less."""

    def _is_skipped(self, name):
        return any(name.startswith(p) for p in mod.SKIP_PREFIXES)

    def test_session_workflow_obligation_prefixes_are_skipped(self):
        for name in ("WM_abc123", "wf/WF_INIT", "claude/CLAUDE_OBLIGATIONS"):
            self.assertTrue(self._is_skipped(name), f"{name} should be skipped")

    def test_browsable_topic_prefixes_are_skipped_both_stylings(self):
        # Both the topic-path form and the bare-basename form must be skipped.
        for name in (
            "spec/SPEC_FOO", "SPEC_FOO",
            "report/REPORT_FOO", "REPORT_FOO",
            "research/RESEARCH_FOO", "RESEARCH_FOO",
            "project/PROJECT_FOO", "PROJECT_FOO",
        ):
            self.assertTrue(self._is_skipped(name), f"{name} should be skipped")

    def test_indexable_categories_are_NOT_skipped(self):
        # These MUST still get an index reminder.
        for name in (
            "feature/FEATURE_CRM", "FEATURE_CRM",
            "ref/REF_DEPLOY", "REF_DEPLOY",
            "dom/DOM_CHECKOUT", "DOM_CHECKOUT",
            "arch/ARCH_INDEX",
            "feedback/FEEDBACK_X",
            "index/INDEX_FEATURES",
            "sys/SYS_API",
            "dev/DEV_PHP",
        ):
            self.assertFalse(self._is_skipped(name), f"{name} should NOT be skipped")

    def test_no_accidental_substring_matches(self):
        # A name that merely CONTAINS a skip token but doesn't start with it
        # must not be skipped (startswith semantics).
        for name in ("feature/FEATURE_REPORT_BUILDER", "ref/REF_SPEC_NOTES"):
            self.assertFalse(self._is_skipped(name), f"{name} should NOT be skipped")

    def test_non_indexed_categories_constant_matches_skip_set(self):
        # The four browsable categories are consistent between the two constants.
        for cat in mod.NON_INDEXED_CATEGORIES:
            self.assertIn(f"{cat}/", mod.SKIP_PREFIXES)
            self.assertIn(cat.upper() + "_", mod.SKIP_PREFIXES)


class TestMemoryNameInIndex(unittest.TestCase):
    def test_matches_by_basename_with_and_without_topic(self):
        content = "- [CRM](feature/FEATURE_CRM.md) — core\n"
        self.assertTrue(mod.memory_name_in_index("feature/FEATURE_CRM", content))
        self.assertTrue(mod.memory_name_in_index("FEATURE_CRM", content))

    def test_absent_name_returns_false(self):
        self.assertFalse(mod.memory_name_in_index("feature/FEATURE_MISSING", CLEAN_INDEX))


class TestHealthCheckClean(unittest.TestCase):
    def test_clean_index_has_no_warnings(self):
        self.assertEqual(mod.check_memory_md_health(CLEAN_INDEX), [])


class TestHealthCheckSizeBudget(unittest.TestCase):
    def test_too_many_lines_warns(self):
        big = "\n".join(f"- [E{i}](ref/REF_{i}.md) — hook" for i in range(mod.MEMORY_MD_MAX_LINES + 5))
        warnings = mod.check_memory_md_health(big)
        self.assertTrue(any("budget" in w for w in warnings))

    def test_too_many_bytes_warns(self):
        # Few lines, but each just under the per-entry cap → blows the byte budget.
        pad = "x" * (mod.INDEX_ENTRY_MAX_CHARS - 30)
        entries = [f"- [E{i}](ref/REF_{i}.md) — {pad}" for i in range(200)]
        content = "\n".join(entries)
        warnings = mod.check_memory_md_health(content)
        self.assertTrue(any("budget" in w for w in warnings))

    def test_at_budget_no_size_warning(self):
        # Exactly at the line ceiling, small bytes → no size warning.
        content = "\n".join("- [x](ref/REF_x.md) — h" for _ in range(mod.MEMORY_MD_MAX_LINES))
        warnings = mod.check_memory_md_health(content)
        self.assertFalse(any("budget" in w for w in warnings))


class TestHealthCheckLongEntries(unittest.TestCase):
    def test_overlong_bullet_warns(self):
        long_hook = "d" * (mod.INDEX_ENTRY_MAX_CHARS + 50)
        content = f"## Features\n- [Big](feature/FEATURE_BIG.md) — {long_hook}\n"
        warnings = mod.check_memory_md_health(content)
        self.assertTrue(any("exceed" in w and "chars" in w for w in warnings))

    def test_short_bullet_no_long_entry_warning(self):
        content = "- [Small](ref/REF_S.md) — short\n"
        warnings = mod.check_memory_md_health(content)
        self.assertFalse(any("exceed" in w for w in warnings))

    def test_only_markdown_bullets_are_measured(self):
        # A long prose line that is NOT an index bullet must not trip the check.
        long_prose = "z" * (mod.INDEX_ENTRY_MAX_CHARS + 100)
        content = f"Some narrative paragraph {long_prose}\n- [Ok](ref/REF_OK.md) — hook\n"
        warnings = mod.check_memory_md_health(content)
        self.assertFalse(any("exceed" in w for w in warnings))


class TestHealthCheckLeakedCategories(unittest.TestCase):
    def test_report_link_flagged(self):
        content = "## Reports\n- [R](report/REPORT_X.md) — x\n"
        warnings = mod.check_memory_md_health(content)
        self.assertTrue(any("report" in w and "NOT indexed" in w for w in warnings))

    def test_all_four_categories_flagged_together(self):
        content = (
            "- [a](report/REPORT_A.md) — a\n"
            "- [b](spec/SPEC_B.md) — b\n"
            "- [c](research/RESEARCH_C.md) — c\n"
            "- [d](project/PROJECT_D.md) — d\n"
        )
        warnings = mod.check_memory_md_health(content)
        joined = " ".join(warnings)
        for cat in ("report", "spec", "research", "project"):
            self.assertIn(cat, joined)

    def test_indexable_links_not_flagged_as_leaked(self):
        content = (
            "- [f](feature/FEATURE_F.md) — f\n"
            "- [r](ref/REF_R.md) — r\n"
            "- [d](dom/DOM_D.md) — d\n"
        )
        warnings = mod.check_memory_md_health(content)
        self.assertFalse(any("NOT indexed" in w for w in warnings))


WITH_OBLIGATIONS = """---
name: DOM_X
description: something
obligations:
  - Do the thing concretely.
---

# DOM_X
"""

NO_OBLIGATIONS = """---
name: DOM_X
description: something
metadata:
  type: domain
---

# DOM_X
"""

EMPTY_OBLIGATIONS = """---
name: REF_X
description: something
obligations: []
---

# REF_X
"""


class TestMissingObligationsReason(unittest.TestCase):
    """Change Set H — hooks/pre/swe_pre_memory_index_gate.missing_obligations_reason."""

    def test_rule_bearing_prefix_missing_field_denied(self):
        for name in ("dom/DOM_X", "ref/REF_X", "dev/DEV_X", "feature/FEATURE_X"):
            reason = gate_mod.missing_obligations_reason(name, NO_OBLIGATIONS)
            self.assertIsNotNone(reason, name)
            self.assertIn("obligations:", reason)
            self.assertIn("obligations: []", reason)

    def test_rule_bearing_prefix_with_field_passes(self):
        for name in ("dom/DOM_X", "ref/REF_X", "dev/DEV_X", "feature/FEATURE_X"):
            self.assertIsNone(
                gate_mod.missing_obligations_reason(name, WITH_OBLIGATIONS), name)

    def test_conscious_none_empty_list_passes(self):
        self.assertIsNone(
            gate_mod.missing_obligations_reason("ref/REF_X", EMPTY_OBLIGATIONS))

    def test_non_rule_bearing_prefixes_never_denied(self):
        for name in ("arch/ARCH_X", "spec/SPEC_X", "wf/WF_X", "index/INDEX_X",
                     "sys/SYS_X", "feedback/FEEDBACK_X"):
            self.assertIsNone(
                gate_mod.missing_obligations_reason(name, NO_OBLIGATIONS), name)

    def test_no_dir_segment_never_denied(self):
        self.assertIsNone(gate_mod.missing_obligations_reason("MEMORY", NO_OBLIGATIONS))


class TestObligationsDenialForWrite(unittest.TestCase):
    """obligations_denial_for_write: write_memory + direct Write wiring."""

    def test_write_memory_create_missing_denied(self):
        denial = gate_mod.obligations_denial_for_write(
            "mcp__serena__write_memory",
            {"memory_name": "dom/DOM_NEW", "content": NO_OBLIGATIONS},
        )
        self.assertIsNotNone(denial)

    def test_write_memory_overwrite_missing_denied(self):
        # Overwrites of EXISTING memories carry the same requirement — a full
        # rewrite is fresh authoring, same as a create.
        denial = gate_mod.obligations_denial_for_write(
            "mcp__serena__write_memory",
            {"memory_name": "ref/REF_EXISTING", "content": NO_OBLIGATIONS},
        )
        self.assertIsNotNone(denial)

    def test_write_memory_with_field_passes(self):
        denial = gate_mod.obligations_denial_for_write(
            "mcp__serena__write_memory",
            {"memory_name": "dom/DOM_NEW", "content": WITH_OBLIGATIONS},
        )
        self.assertIsNone(denial)

    def test_direct_write_under_serena_memory_denied(self):
        denial = gate_mod.obligations_denial_for_write(
            "Write",
            {"file_path": "/proj/.serena/memory/dom/DOM_X.md", "content": NO_OBLIGATIONS},
        )
        self.assertIsNotNone(denial)

    def test_direct_write_under_serena_memory_with_field_passes(self):
        denial = gate_mod.obligations_denial_for_write(
            "Write",
            {"file_path": "/proj/.serena/memory/dom/DOM_X.md", "content": WITH_OBLIGATIONS},
        )
        self.assertIsNone(denial)

    def test_direct_write_outside_serena_memory_never_denied(self):
        denial = gate_mod.obligations_denial_for_write(
            "Write",
            {"file_path": "/proj/some/other/dom/DOM_X.md", "content": NO_OBLIGATIONS},
        )
        self.assertIsNone(denial)

    def test_direct_write_non_md_never_denied(self):
        denial = gate_mod.obligations_denial_for_write(
            "Write",
            {"file_path": "/proj/.serena/memory/dom/DOM_X.py", "content": NO_OBLIGATIONS},
        )
        self.assertIsNone(denial)

    def test_edit_memory_never_denied(self):
        # edit_memory (partial edits) is exempt — tool_name doesn't match the
        # write_memory or Write branches at all.
        denial = gate_mod.obligations_denial_for_write(
            "mcp__serena__edit_memory",
            {"memory_name": "dom/DOM_X", "repl": NO_OBLIGATIONS},
        )
        self.assertIsNone(denial)

    def test_non_rule_bearing_write_memory_never_denied(self):
        denial = gate_mod.obligations_denial_for_write(
            "mcp__serena__write_memory",
            {"memory_name": "spec/SPEC_X", "content": NO_OBLIGATIONS},
        )
        self.assertIsNone(denial)


class TestObligationsGateMainWiring(unittest.TestCase):
    """main()-level wiring: the obligations check fires for non-index targets,
    in addition to (not instead of) the existing B4 dedupe check."""

    def test_targets_memory_index_excludes_obligations_named_memories(self):
        # A write to MEMORY.md itself is never subject to the obligations
        # check (it has its own leaked-category check) — confirm the routing
        # predicate used by main() correctly separates the two paths.
        self.assertTrue(gate_mod.targets_memory_index({"memory_name": "MEMORY"}))
        self.assertFalse(gate_mod.targets_memory_index({"memory_name": "dom/DOM_X"}))


if __name__ == "__main__":
    unittest.main()
