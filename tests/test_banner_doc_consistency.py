"""Source-repo lint: between-call banners must agree with the state docs
they summarize (G7).

The sr-only harnessed-vs-unharnessed A/B showed that hook banners injected
BETWEEN tool calls outweigh the WF_* state docs at decision time. A banner
that contradicts its doc (the observed case: a "Load ALL … SPEC_*" WF_CLASSIFY
continuation vs WF_CLASSIFY.md Step 4d's tiered loading with spec/ excluded
from bulk loading) actively mistrains the agent. These tests grep the SOURCE
files at test time and fail on divergence:

  1. The WF_CLASSIFY continuation directive in swe_post_read_state.py must be
     tiered and must not bulk-load a prefix Step 4d excludes.
  2. WF_CLASSIFY.md Step 4d must itself carry the tiered-loading language the
     directive summarizes.
  3. The stop-gate exemption marker "DIAGNOSIS VERIFICATION:" is a shared
     contract (G4/G7) between memories/wf/WF_RESEARCH.md and
     hooks/stop/swe_stop_response_format.py — it must appear in BOTH, or the
     doc promises an exemption the gate does not honor (or vice versa).

Stdlib unittest only. Read-only: no file in this test is ever written.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_hook, PLUGIN_ROOT  # noqa: E402

read_state_mod = import_hook("post/swe_post_read_state")

WF_CLASSIFY_MD = os.path.join(PLUGIN_ROOT, "memories", "wf", "WF_CLASSIFY.md")
WF_RESEARCH_MD = os.path.join(PLUGIN_ROOT, "memories", "wf", "WF_RESEARCH.md")
STOP_FORMAT_HOOK = os.path.join(
    PLUGIN_ROOT, "hooks", "stop", "swe_stop_response_format.py")

DIAGNOSIS_MARKER = "DIAGNOSIS VERIFICATION:"


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _step_4d(doc):
    """The Step 4d section of WF_CLASSIFY.md (from its heading to the next
    same-or-higher-level heading)."""
    match = re.search(r"^#{2,3} 4d\..*?(?=^#{2,3} )", doc,
                      re.MULTILINE | re.DOTALL)
    return match.group(0) if match else ""


def _4d_excluded_topics(doc):
    """Topic prefixes Step 4d excludes from bulk loading, parsed from its
    'Exclusions' block (backticked `topic/` tokens)."""
    section = _step_4d(doc)
    match = re.search(r"Exclusions.*", section, re.DOTALL)
    if not match:
        return []
    return re.findall(r"`([a-z]+)/", match.group(0))


class TestClassifyBannerMatchesDoc(unittest.TestCase):
    """The WF_CLASSIFY continuation banner vs WF_CLASSIFY.md Step 4d."""

    def setUp(self):
        self.directive = read_state_mod._get_continuation("WF_CLASSIFY", "x")
        self.doc = _read(WF_CLASSIFY_MD)

    def test_directive_exists(self):
        self.assertTrue(self.directive)

    def test_directive_has_no_bulk_load_all_spec_phrasing(self):
        # The exact divergence the A/B surfaced: "Load ALL … SPEC_*".
        self.assertIsNone(
            re.search(r"Load ALL.*SPEC_", self.directive),
            "WF_CLASSIFY banner bulk-loads SPEC_* — contradicts Step 4d "
            f"tiered loading: {self.directive!r}")

    def test_directive_is_tiered(self):
        self.assertRegex(
            self.directive, r"[Tt]iered",
            "WF_CLASSIFY banner must use the doc's tiered-sweep wording")

    def test_doc_step_4d_has_tiered_loading_language(self):
        section = _step_4d(self.doc)
        self.assertTrue(section, "WF_CLASSIFY.md has no Step 4d section")
        self.assertIn("tier", section.lower(),
                      "Step 4d must describe tiered loading — keep the "
                      "banner lint and the doc in sync")

    def test_directive_load_rule_names_no_4d_excluded_prefix(self):
        # A topic 4d excludes from bulk loading (spec/, report/, …) must not
        # appear in the banner as an uppercase load glob ("SPEC_*") — that is
        # the "load this whole prefix" phrasing. Mentioning the on-miss
        # exception in prose (e.g. "symptom-surfaced spec/") is fine.
        topics = _4d_excluded_topics(self.doc)
        self.assertTrue(topics, "could not parse Step 4d exclusions")
        for topic in topics:
            glob = f"{topic.upper()}_*"
            self.assertNotIn(
                glob, self.directive,
                f"WF_CLASSIFY banner load rule names {glob}, which Step 4d "
                "excludes from bulk loading")


class TestDiagnosisVerificationSharedContract(unittest.TestCase):
    """The stop-gate exemption marker is one contract in two files (G4/G7):
    WF_RESEARCH.md tells the agent to emit it; swe_stop_response_format.py
    exempts responses that carry it. Diverge and either the doc lies or the
    gate blocks documented behavior."""

    def test_marker_in_wf_research_doc(self):
        self.assertIn(DIAGNOSIS_MARKER, _read(WF_RESEARCH_MD),
                      f"{WF_RESEARCH_MD} must contain the "
                      f"{DIAGNOSIS_MARKER!r} stop-gate exemption marker "
                      "(shared contract with the stop-format hook)")

    def test_marker_in_stop_format_hook(self):
        self.assertIn(DIAGNOSIS_MARKER, _read(STOP_FORMAT_HOOK),
                      f"{STOP_FORMAT_HOOK} must contain the "
                      f"{DIAGNOSIS_MARKER!r} stop-gate exemption marker "
                      "(shared contract with WF_RESEARCH.md)")


if __name__ == "__main__":
    unittest.main()
