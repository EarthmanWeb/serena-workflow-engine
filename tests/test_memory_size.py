"""Tests for hooks/swe_hooks/core/memory_size.py and scripts/memory-size-audit.py.

Covers:
  - measure_memory: chars/bytes/words/tokens_est, section parsing (##/###/####,
    preamble, fenced-code headings ignored).
  - classify_size: boundary behavior at warn/split/unreadable.
  - size_advisory: None when ok, one-line message otherwise.
  - scripts/memory-size-audit.py: --root (plain + aliased), conf-file loading
    (with alias + :ro), --topic filtering, --json shape, WM_* skip, exit codes
    0/1/2.

Stdlib unittest only. Deterministic + offline. IO uses tempfile.TemporaryDirectory.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_core, PLUGIN_ROOT  # noqa: E402

size_mod = import_core("swe_hooks.core.memory_size")

SCRIPT_PATH = os.path.join(PLUGIN_ROOT, "scripts", "memory-size-audit.py")


# ---------------------------------------------------------------------------
# measure_memory
# ---------------------------------------------------------------------------
class TestMeasureMemory(unittest.TestCase):
    def test_basic_counts(self):
        text = "hello world foo"
        m = size_mod.measure_memory(text)
        self.assertEqual(m["chars"], len(text))
        self.assertEqual(m["bytes"], len(text.encode("utf-8")))
        self.assertEqual(m["words"], 3)
        self.assertEqual(m["tokens_est"], len(text) // 4)

    def test_bytes_differ_from_chars_for_multibyte(self):
        text = "café 📏"
        m = size_mod.measure_memory(text)
        self.assertEqual(m["chars"], len(text))
        self.assertGreater(m["bytes"], m["chars"])

    def test_empty_text(self):
        m = size_mod.measure_memory("")
        self.assertEqual(m["chars"], 0)
        self.assertEqual(m["bytes"], 0)
        self.assertEqual(m["words"], 0)
        self.assertEqual(m["sections"], [])

    def test_preamble_counted_when_content_before_first_heading(self):
        text = "intro text\n\n## Heading One\nbody\n"
        m = size_mod.measure_memory(text)
        self.assertEqual(m["sections"][0]["heading"], size_mod.PREAMBLE_HEADING)
        self.assertEqual(m["sections"][0]["level"], 0)
        self.assertEqual(m["sections"][1]["heading"], "Heading One")
        self.assertEqual(m["sections"][1]["level"], 2)

    def test_no_preamble_when_text_starts_with_heading(self):
        text = "## Heading One\nbody\n"
        m = size_mod.measure_memory(text)
        self.assertEqual(len(m["sections"]), 1)
        self.assertEqual(m["sections"][0]["heading"], "Heading One")

    def test_section_chars_span_to_next_heading_of_any_level(self):
        text = "## A\nAAAA\n### B\nBB\n## C\nC\n"
        m = size_mod.measure_memory(text)
        headings = [(s["heading"], s["level"]) for s in m["sections"]]
        self.assertEqual(headings, [("A", 2), ("B", 3), ("C", 2)])
        # section A spans from "## A\n" up to (not incl) "### B\n"
        a_section = m["sections"][0]
        expected_a_chars = len("## A\nAAAA\n")
        self.assertEqual(a_section["chars"], expected_a_chars)

    def test_h4_recognized(self):
        text = "#### Deep\ncontent\n"
        m = size_mod.measure_memory(text)
        self.assertEqual(m["sections"][0]["level"], 4)

    def test_atx_closing_hashes_stripped_from_heading(self):
        text = "## Foo ##\ncontent\n"
        m = size_mod.measure_memory(text)
        self.assertEqual(m["sections"][0]["heading"], "Foo")

    def test_hash_without_preceding_space_not_treated_as_closer(self):
        # A '#' immediately following non-space text (no whitespace before
        # it) is not an ATX closing sequence and stays part of the heading.
        text = "## C# tips\ncontent\n"
        m = size_mod.measure_memory(text)
        self.assertEqual(m["sections"][0]["heading"], "C# tips")

    def test_h1_not_treated_as_section_boundary(self):
        # Only ##/###/#### count per spec; a single # is not a section heading.
        text = "# Title\nintro\n## Real Section\nbody\n"
        m = size_mod.measure_memory(text)
        headings = [s["heading"] for s in m["sections"]]
        self.assertNotIn("Title", headings)
        self.assertEqual(m["sections"][0]["heading"], size_mod.PREAMBLE_HEADING)

    def test_fenced_code_headings_ignored(self):
        text = (
            "## Real\n"
            "before\n"
            "```\n"
            "## not a heading\n"
            "### also not\n"
            "```\n"
            "after\n"
            "## Real2\n"
        )
        m = size_mod.measure_memory(text)
        headings = [s["heading"] for s in m["sections"]]
        self.assertEqual(headings, ["Real", "Real2"])

    def test_tilde_fenced_code_headings_ignored(self):
        text = "## Real\n~~~\n## fake\n~~~\nafter\n"
        m = size_mod.measure_memory(text)
        headings = [s["heading"] for s in m["sections"]]
        self.assertEqual(headings, ["Real"])

    def test_sections_sum_to_total_chars(self):
        text = "pre\n## A\nfoo\n### B\nbar\n## C\nbaz\n"
        m = size_mod.measure_memory(text)
        total = sum(s["chars"] for s in m["sections"])
        self.assertEqual(total, len(text))


# ---------------------------------------------------------------------------
# classify_size
# ---------------------------------------------------------------------------
class TestClassifySize(unittest.TestCase):
    def test_ok_at_and_below_warn(self):
        self.assertEqual(size_mod.classify_size(0), "ok")
        self.assertEqual(size_mod.classify_size(size_mod.WARN_CHARS), "ok")

    def test_warn_just_above_warn(self):
        self.assertEqual(size_mod.classify_size(size_mod.WARN_CHARS + 1), "warn")

    def test_warn_at_split_boundary_is_split(self):
        # split: chars < unreadable, and NOT ok — spec says warn is "<= split"
        self.assertEqual(size_mod.classify_size(size_mod.SPLIT_CHARS), "warn")

    def test_split_just_above_split(self):
        self.assertEqual(size_mod.classify_size(size_mod.SPLIT_CHARS + 1), "split")

    def test_split_just_below_unreadable(self):
        self.assertEqual(size_mod.classify_size(size_mod.UNREADABLE_CHARS - 1), "split")

    def test_unreadable_at_threshold(self):
        self.assertEqual(size_mod.classify_size(size_mod.UNREADABLE_CHARS), "unreadable")

    def test_unreadable_above_threshold(self):
        self.assertEqual(size_mod.classify_size(size_mod.UNREADABLE_CHARS + 1000), "unreadable")

    def test_measured_boundary_49999_is_split(self):
        self.assertEqual(size_mod.UNREADABLE_CHARS, 50000)
        self.assertEqual(size_mod.classify_size(49999), "split")

    def test_measured_boundary_50000_is_unreadable(self):
        self.assertEqual(size_mod.classify_size(50000), "unreadable")

    def test_custom_thresholds(self):
        self.assertEqual(size_mod.classify_size(50, warn=10, split=100, unreadable=200), "warn")
        self.assertEqual(size_mod.classify_size(150, warn=10, split=100, unreadable=200), "split")
        self.assertEqual(size_mod.classify_size(200, warn=10, split=100, unreadable=200), "unreadable")


# ---------------------------------------------------------------------------
# is_excluded_memory
# ---------------------------------------------------------------------------
class TestIsExcludedMemory(unittest.TestCase):
    def test_spec_topic_excluded(self):
        self.assertTrue(size_mod.is_excluded_memory("spec/SPEC_X"))

    def test_aliased_spec_topic_excluded(self):
        self.assertTrue(size_mod.is_excluded_memory("em/spec/SPEC_X"))

    def test_report_topic_excluded(self):
        self.assertTrue(size_mod.is_excluded_memory("report/REPORT_Y"))

    def test_dom_topic_not_excluded(self):
        self.assertFalse(size_mod.is_excluded_memory("dom/DOM_SPECIAL"))

    def test_ref_spec_parser_not_excluded(self):
        # Basename "REF_SPEC_PARSER" does not start with SPEC_/REPORT_, and
        # no path segment other than the basename is an excluded topic.
        self.assertFalse(size_mod.is_excluded_memory("ref/REF_SPEC_PARSER"))

    def test_bare_spec_name_no_topic_excluded(self):
        self.assertTrue(size_mod.is_excluded_memory("SPEC_Z"))

    def test_bare_report_name_no_topic_excluded(self):
        self.assertTrue(size_mod.is_excluded_memory("REPORT_Q"))

    def test_research_topic_excluded(self):
        self.assertTrue(size_mod.is_excluded_memory("research/RESEARCH_X"))

    def test_project_topic_excluded(self):
        self.assertTrue(size_mod.is_excluded_memory("project/PROJECT_Y"))

    def test_aliased_research_topic_excluded(self):
        self.assertTrue(size_mod.is_excluded_memory("em/research/RESEARCH_Z"))

    def test_bare_project_name_no_topic_excluded(self):
        self.assertTrue(size_mod.is_excluded_memory("PROJECT_Q"))

    def test_dom_projection_not_excluded(self):
        # Basename "DOM_PROJECTION" does not start with an excluded-topic
        # prefix, and no path segment equals an excluded topic.
        self.assertFalse(size_mod.is_excluded_memory("dom/DOM_PROJECTION"))

    def test_ref_research_tools_not_excluded(self):
        # Basename "REF_RESEARCH_TOOLS" does not start with an excluded-topic
        # prefix, and no path segment equals an excluded topic.
        self.assertFalse(size_mod.is_excluded_memory("ref/REF_RESEARCH_TOOLS"))

    def test_case_insensitive_topic_and_basename(self):
        self.assertTrue(size_mod.is_excluded_memory("Spec/spec_lower"))
        self.assertTrue(size_mod.is_excluded_memory("report_lower"))

    def test_empty_name_not_excluded(self):
        self.assertFalse(size_mod.is_excluded_memory(""))

    def test_unrelated_name_not_excluded(self):
        self.assertFalse(size_mod.is_excluded_memory("wf/WF_INIT"))


# ---------------------------------------------------------------------------
# size_advisory
# ---------------------------------------------------------------------------
class TestSizeAdvisory(unittest.TestCase):
    def test_none_when_ok(self):
        self.assertIsNone(size_mod.size_advisory("dom/DOM_X", "short text"))

    def test_message_when_warn(self):
        text = "x" * (size_mod.WARN_CHARS + 1)
        msg = size_mod.size_advisory("dom/DOM_X", text)
        self.assertIsNotNone(msg)
        self.assertIn("dom/DOM_X", msg)
        self.assertIn("WARN", msg)
        self.assertIn("/swe-memory-size-audit", msg)

    def test_message_when_split(self):
        text = "x" * (size_mod.SPLIT_CHARS + 1)
        msg = size_mod.size_advisory("dom/DOM_Y", text)
        self.assertIn("SPLIT", msg)

    def test_message_when_unreadable(self):
        text = "x" * size_mod.UNREADABLE_CHARS
        msg = size_mod.size_advisory("dom/DOM_Z", text)
        self.assertIn("UNREADABLE", msg)

    def test_numbers_formatted_from_constants(self):
        text = "x" * (size_mod.WARN_CHARS + 1)
        msg = size_mod.size_advisory("dom/DOM_X", text)
        self.assertIn(f"{size_mod.WARN_CHARS:,}", msg)
        self.assertIn(f"{size_mod.SPLIT_CHARS:,}", msg)
        self.assertIn(f"{size_mod.UNREADABLE_CHARS:,}", msg)

    def test_none_for_oversized_spec_memory(self):
        text = "x" * (size_mod.UNREADABLE_CHARS + 100)
        self.assertIsNone(size_mod.size_advisory("spec/SPEC_BIG", text))

    def test_none_for_oversized_report_memory(self):
        text = "x" * (size_mod.SPLIT_CHARS + 100)
        self.assertIsNone(size_mod.size_advisory("report/REPORT_BIG", text))

    def test_none_for_oversized_research_memory(self):
        text = "x" * (size_mod.UNREADABLE_CHARS + 100)
        self.assertIsNone(size_mod.size_advisory("research/RESEARCH_BIG", text))

    def test_none_for_oversized_project_memory(self):
        text = "x" * (size_mod.SPLIT_CHARS + 100)
        self.assertIsNone(size_mod.size_advisory("project/PROJECT_BIG", text))


# ---------------------------------------------------------------------------
# scripts/memory-size-audit.py — subprocess-level tests
# ---------------------------------------------------------------------------
def run_script(args, cwd):
    return subprocess.run(
        [sys.executable, SCRIPT_PATH] + args,
        cwd=cwd, capture_output=True, text=True,
    )


class TestAuditScriptRoots(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "memories")
        os.makedirs(os.path.join(self.root, "dom"))
        with open(os.path.join(self.root, "dom", "DOM_SMALL.md"), "w") as f:
            f.write("## A\nshort\n")
        with open(os.path.join(self.root, "dom", "DOM_BIG.md"), "w") as f:
            f.write("x" * (size_mod.SPLIT_CHARS + 100))
        with open(os.path.join(self.root, "WM_SESSION.md"), "w") as f:
            f.write("x" * (size_mod.UNREADABLE_CHARS + 100))

    def tearDown(self):
        self.tmp.cleanup()

    def test_spec_and_report_memories_excluded_from_table_and_counts(self):
        os.makedirs(os.path.join(self.root, "spec"))
        os.makedirs(os.path.join(self.root, "report"))
        with open(os.path.join(self.root, "spec", "SPEC_BIG.md"), "w") as f:
            f.write("x" * (size_mod.UNREADABLE_CHARS + 100))
        with open(os.path.join(self.root, "report", "REPORT_BIG.md"), "w") as f:
            f.write("x" * (size_mod.SPLIT_CHARS + 100))
        proc = run_script(["--root", self.root, "--json", "--all"], cwd=self.tmp.name)
        data = json.loads(proc.stdout)
        names = [m["name"] for m in data["memories"]]
        self.assertNotIn("spec/SPEC_BIG", names)
        self.assertNotIn("report/REPORT_BIG", names)
        self.assertEqual(data["counts"]["excluded"], 2)
        # excluded memories never affect the split/unreadable exit code.
        text_proc = run_script(["--root", self.root], cwd=self.tmp.name)
        self.assertIn("excluded=2", text_proc.stdout)

    def test_research_and_project_memories_excluded_from_table_and_counts(self):
        os.makedirs(os.path.join(self.root, "research"))
        os.makedirs(os.path.join(self.root, "project"))
        with open(os.path.join(self.root, "research", "RESEARCH_BIG.md"), "w") as f:
            f.write("x" * (size_mod.UNREADABLE_CHARS + 100))
        with open(os.path.join(self.root, "project", "PROJECT_BIG.md"), "w") as f:
            f.write("x" * (size_mod.SPLIT_CHARS + 100))
        proc = run_script(["--root", self.root, "--json", "--all"], cwd=self.tmp.name)
        data = json.loads(proc.stdout)
        names = [m["name"] for m in data["memories"]]
        self.assertNotIn("research/RESEARCH_BIG", names)
        self.assertNotIn("project/PROJECT_BIG", names)
        self.assertEqual(data["counts"]["excluded"], 2)
        text_proc = run_script(["--root", self.root], cwd=self.tmp.name)
        self.assertIn("excluded=2", text_proc.stdout)

    def test_plain_root_json_shape_and_wm_skip(self):
        proc = run_script(["--root", self.root, "--json"], cwd=self.tmp.name)
        self.assertEqual(proc.returncode, 1)  # DOM_BIG is split
        data = json.loads(proc.stdout)
        self.assertIn("thresholds", data)
        self.assertIn("memories", data)
        self.assertIn("counts", data)
        names = [m["name"] for m in data["memories"]]
        self.assertIn("dom/DOM_SMALL", names)
        self.assertIn("dom/DOM_BIG", names)
        self.assertNotIn("WM_SESSION", names)
        big = next(m for m in data["memories"] if m["name"] == "dom/DOM_BIG")
        self.assertEqual(big["status"], "split")
        self.assertIn("chars", big)
        self.assertIn("bytes", big)
        self.assertIn("words", big)
        self.assertIn("tokens_est", big)
        self.assertIn("sections", big)

    def test_aliased_root_prefixes_name(self):
        proc = run_script(["--root", f"em={self.root}", "--json"], cwd=self.tmp.name)
        data = json.loads(proc.stdout)
        names = [m["name"] for m in data["memories"]]
        self.assertIn("em/dom/DOM_BIG", names)

    def test_topic_filter(self):
        os.makedirs(os.path.join(self.root, "ref"))
        with open(os.path.join(self.root, "ref", "REF_X.md"), "w") as f:
            f.write("## A\nshort\n")
        proc = run_script(["--root", self.root, "--topic", "dom/", "--json", "--all"],
                           cwd=self.tmp.name)
        data = json.loads(proc.stdout)
        names = [m["name"] for m in data["memories"]]
        self.assertTrue(all(n.startswith("dom/") for n in names))
        self.assertNotIn("ref/REF_X", names)

    def test_exit_code_0_when_all_ok(self):
        empty_root = os.path.join(self.tmp.name, "onlysmall")
        os.makedirs(empty_root)
        proc = run_script(["--root", empty_root, "--json"], cwd=self.tmp.name)
        # existing but empty dir -> no memories -> ok exit
        self.assertEqual(proc.returncode, 0)

    def test_missing_root_dir_errors_exit_2(self):
        # A --root that does not exist is a fatal error: it is printed to
        # stderr and the run exits 2 rather than silently reporting clean.
        missing = os.path.join(self.tmp.name, "does_not_exist")
        proc = run_script(["--root", missing, "--json"], cwd=self.tmp.name)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("ERROR: memory root not found:", proc.stderr)
        self.assertIn(missing, proc.stderr)

    def test_conf_with_one_valid_one_missing_root_errors_exit_2(self):
        os.makedirs(os.path.join(self.tmp.name, ".serena"))
        valid_root = os.path.join(self.tmp.name, "valid_root")
        os.makedirs(os.path.join(valid_root, "dom"))
        with open(os.path.join(valid_root, "dom", "DOM_OK.md"), "w") as f:
            f.write("## A\nshort\n")
        missing_root = os.path.join(self.tmp.name, "stale_root")
        conf_path = os.path.join(self.tmp.name, ".serena", "memory-paths.conf")
        with open(conf_path, "w") as f:
            f.write(f"./valid_root\n{missing_root}\n")
        proc = run_script([], cwd=self.tmp.name)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("ERROR: memory root not found:", proc.stderr)
        self.assertIn(missing_root, proc.stderr)

    def test_all_flag_includes_ok_rows_text_mode(self):
        proc = run_script(["--root", self.root, "--all"], cwd=self.tmp.name)
        self.assertIn("DOM_SMALL", proc.stdout)
        self.assertIn("DOM_BIG", proc.stdout)

    def test_default_text_mode_excludes_ok_rows(self):
        proc = run_script(["--root", self.root], cwd=self.tmp.name)
        self.assertNotIn("DOM_SMALL", proc.stdout)
        self.assertIn("DOM_BIG", proc.stdout)

    def test_counts_summary_line(self):
        proc = run_script(["--root", self.root, "--all"], cwd=self.tmp.name)
        self.assertIn("counts:", proc.stdout)

    def test_custom_thresholds_change_status(self):
        proc = run_script(
            ["--root", self.root, "--json", "--warn", "1", "--split", "2", "--unreadable", "3"],
            cwd=self.tmp.name,
        )
        data = json.loads(proc.stdout)
        small = next(m for m in data["memories"] if m["name"] == "dom/DOM_SMALL")
        self.assertEqual(small["status"], "unreadable")


class TestAuditScriptConfFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.tmp.name, ".serena"))
        self.memdir = os.path.join(self.tmp.name, ".serena", "memory")
        os.makedirs(os.path.join(self.memdir, "dom"))
        with open(os.path.join(self.memdir, "dom", "DOM_X.md"), "w") as f:
            f.write("## A\nshort\n")

        self.ext_root = os.path.join(self.tmp.name, "external")
        os.makedirs(os.path.join(self.ext_root, "feature"))
        with open(os.path.join(self.ext_root, "feature", "FEATURE_Y.md"), "w") as f:
            f.write("## A\nshort\n")

        conf = (
            "# comment\n"
            "\n"
            "./.serena/memory\n"
            f"em={self.ext_root}:ro\n"
        )
        with open(os.path.join(self.tmp.name, ".serena", "memory-paths.conf"), "w") as f:
            f.write(conf)

    def tearDown(self):
        self.tmp.cleanup()

    def test_conf_loaded_when_no_root_flag(self):
        proc = run_script(["--json", "--all"], cwd=self.tmp.name)
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        names = [m["name"] for m in data["memories"]]
        self.assertIn("dom/DOM_X", names)
        self.assertIn("em/feature/FEATURE_Y", names)

    def test_no_root_no_conf_errors_exit_2(self):
        other = tempfile.TemporaryDirectory()
        try:
            proc = run_script([], cwd=other.name)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("error", proc.stderr.lower())
        finally:
            other.cleanup()

    def test_root_flag_overrides_conf(self):
        only_dom = os.path.join(self.tmp.name, "only_dom_root")
        os.makedirs(os.path.join(only_dom, "dom"))
        with open(os.path.join(only_dom, "dom", "DOM_Z.md"), "w") as f:
            f.write("## A\nshort\n")
        proc = run_script(["--root", only_dom, "--json", "--all"], cwd=self.tmp.name)
        data = json.loads(proc.stdout)
        names = [m["name"] for m in data["memories"]]
        self.assertIn("dom/DOM_Z", names)
        self.assertNotIn("dom/DOM_X", names)
        self.assertNotIn("em/feature/FEATURE_Y", names)


if __name__ == "__main__":
    unittest.main()
