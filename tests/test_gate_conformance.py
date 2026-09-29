"""Tests for experiments/harness-ab/gate_conformance.py pure functions.

Fixtures below are hand-built but shaped exactly like real events pulled
from experiments/harness-ab/results/20260929-123133/runs/baseline-t1
(.serena/streams/08df5352.jsonl and transcript.jsonl) — see that run's
stream file for the source of the conforming-run event shapes; the
violating-run fixtures are synthetic (a hypothetical run that edits before
its sweep is verified and never reads WF_INIT / CLAUDE_OBLIGATIONS /
WF_CLASSIFY in order).
"""
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
HARNESS_DIR = os.path.join(REPO_ROOT, "experiments", "harness-ab")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gc = _load("harness_ab_gate_conformance", os.path.join(HARNESS_DIR, "gate_conformance.py"))


def _tool_use_event(name, tool_input=None, parent=None):
    return {
        "type": "assistant",
        "parent_tool_use_id": parent,
        "message": {"content": [{"type": "tool_use", "name": name, "input": tool_input or {}}]},
    }


def _tool_deny_event(text, parent=None):
    return {
        "type": "user",
        "parent_tool_use_id": parent,
        "message": {"content": [{"type": "tool_result", "is_error": True, "content": text}]},
    }


def _text_event(text, parent=None):
    return {
        "type": "assistant",
        "parent_tool_use_id": parent,
        "message": {"content": [{"type": "text", "text": text}]},
    }


# --------------------------------------------------------------------------
# Real-shaped conforming run: baseline-t1 stream (trimmed) + a matching
# transcript timeline (init chain, then task work, then edits after sweep).
# --------------------------------------------------------------------------

CONFORMING_STREAM = [
    {"t": 1, "type": "docread", "s": "s1", "name": "wf/WF_INIT"},
    {"t": 2, "type": "docread", "s": "s1", "name": "claude/CLAUDE_OBLIGATIONS"},
    {"t": 3, "type": "docread", "s": "s1", "name": "wf/WF_CLASSIFY"},
    {"t": 4, "type": "session_start", "s": "s1"},
    {"t": 5, "type": "docread", "s": "s1", "name": "index/INDEX_FEATURES"},
    {"t": 6, "type": "docread", "s": "s1", "name": "feature/FEATURE_LEDGER"},
    {"t": 7, "type": "docread", "s": "s1", "name": "dom/DOM_LEDGER_RULES"},
    {"t": 8, "type": "sweep", "s": "s1"},
    {"t": 9, "type": "state", "from_s": "WF_CLASSIFY", "to_s": "WF_EXECUTE", "s": "s1"},
    {"t": 10, "type": "gated"},
    {"t": 11, "type": "task_work", "tool": "Bash", "s": "s1"},
    {"t": 12, "type": "edit", "file": "/work/ledgerlite/recurring.py", "s": "s1"},
    {"t": 13, "type": "edit", "file": "/work/ledgerlite/budget.py", "s": "s1"},
    {"t": 14, "type": "delegation", "tool": "Agent", "s": "s1"},
]

CONFORMING_TRANSCRIPT = [
    _tool_use_event("mcp__plugin_swe_serena__read_memory", {"memory_name": "wf/WF_INIT"}),
    _tool_use_event("mcp__plugin_swe_serena__read_memory", {"memory_name": "claude/CLAUDE_OBLIGATIONS"}),
    _tool_use_event("mcp__plugin_swe_serena__read_memory", {"memory_name": "wf/WF_CLASSIFY"}),
    _tool_use_event("mcp__plugin_swe_serena__read_memory", {"memory_name": "index/INDEX_FEATURES"}),
    _tool_use_event("mcp__plugin_swe_serena__read_memory", {"memory_name": "feature/FEATURE_LEDGER"}),
    _tool_use_event("mcp__plugin_swe_serena__read_memory", {"memory_name": "dom/DOM_LEDGER_RULES"}),
    _tool_use_event("Bash", {"command": "ls"}),
    _tool_use_event("Write", {"file_path": "/work/ledgerlite/recurring.py"}),
    _tool_use_event("Write", {"file_path": "/work/ledgerlite/budget.py"}),
    _tool_use_event("Agent", {"prompt": "go"}),
]

# --------------------------------------------------------------------------
# Synthetic violating run: no stream sweep marker at all (or edits recorded
# in the stream before the sweep event), and the transcript jumps straight
# to Edit without the WF_INIT chain — the gate-probe failure mode.
# --------------------------------------------------------------------------

VIOLATING_STREAM = [
    {"t": 1, "type": "session_start", "s": "s2"},
    {"t": 2, "type": "edit", "file": "/work/ledgerlite/money.py", "s": "s2"},
    {"t": 3, "type": "docread", "s": "s2", "name": "wf/WF_INIT"},
    {"t": 4, "type": "sweep", "s": "s2"},
]

VIOLATING_TRANSCRIPT = [
    _tool_use_event("Edit", {"file_path": "/work/ledgerlite/money.py"}),
    _tool_deny_event("🛑 BLOCKED: Edit called before WF_INIT complete."),
    _tool_use_event("mcp__plugin_swe_serena__read_memory", {"memory_name": "wf/WF_INIT"}),
    _tool_use_event("Edit", {"file_path": "/work/ledgerlite/money.py"}),
    _tool_deny_event("🛑 SWEEP GATE — edit blocked: the Feature Knowledge Sweep is not verified."),
]

CONTROL_TRANSCRIPT = [
    _tool_use_event("Read", {"file_path": "/work/.serena/memory/feature/FEATURE_LEDGER.md"}),
    _tool_use_event("Read", {"file_path": "/work/.serena/memory/dom/DOM_LEDGER_RULES.md"}),
    _tool_use_event("Edit", {"file_path": "/work/ledgerlite/recurring.py"}),
]


class NormalizeMemoryNameTest(unittest.TestCase):
    def test_strips_prefix_and_suffix(self):
        self.assertEqual(gc.normalize_memory_name("mem:wf/WF_INIT.md"), "wf/wf_init")

    def test_plain(self):
        self.assertEqual(gc.normalize_memory_name("Feature/FEATURE_LEDGER"), "feature/feature_ledger")

    def test_empty(self):
        self.assertEqual(gc.normalize_memory_name(None), "")
        self.assertEqual(gc.normalize_memory_name(""), "")


class ParseStreamEventsTest(unittest.TestCase):
    def test_parses_real_shaped_lines(self):
        lines = [
            '{"t": 1, "type": "docread", "s": "x", "name": "wf/WF_INIT"}',
            "",
            "not json",
            '{"t": 2, "type": "sweep", "s": "x"}',
        ]
        events = gc.parse_stream_events(lines)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["type"], "docread")
        self.assertEqual(events[1]["type"], "sweep")


class ClassifyDenyReasonTest(unittest.TestCase):
    def test_init_deny(self):
        self.assertEqual(
            gc.classify_deny_reason("🛑 BLOCKED: read_memory(\"x\") called before WF_INIT complete."),
            "init",
        )

    def test_no_wm_deny(self):
        self.assertEqual(
            gc.classify_deny_reason("🛑 BLOCKED: No Working Memory for session abc123"),
            "init",
        )

    def test_sweep_deny(self):
        self.assertEqual(
            gc.classify_deny_reason("🛑 SWEEP GATE — edit blocked: the Feature Knowledge Sweep..."),
            "sweep",
        )

    def test_docs_first_deny(self):
        self.assertEqual(
            gc.classify_deny_reason("📓 DOCS FIRST — search blocked: docs-consult budget exceeded"),
            "docs",
        )

    def test_memory_index_deny_is_docs(self):
        self.assertEqual(
            gc.classify_deny_reason("🛑 BLOCKED: this write adds 2 link(s) to MEMORY.md."),
            "docs",
        )

    def test_raw_memory_edit_deny(self):
        self.assertEqual(
            gc.classify_deny_reason("🛑 BLOCKED: raw Edit/Write on a Serena memory file.\n..."),
            "edit",
        )

    def test_stop_hook(self):
        self.assertEqual(gc.classify_deny_reason("Stop hook prevented completion"), "stop")

    def test_unrelated_text_returns_none(self):
        self.assertIsNone(gc.classify_deny_reason("some unrelated error"))

    def test_empty_returns_none(self):
        self.assertIsNone(gc.classify_deny_reason(""))
        self.assertIsNone(gc.classify_deny_reason(None))


class InitChainCompleteTest(unittest.TestCase):
    def test_conforming_chain_true(self):
        self.assertTrue(gc.compute_init_chain_complete(CONFORMING_TRANSCRIPT))

    def test_violating_edit_before_chain_false(self):
        self.assertFalse(gc.compute_init_chain_complete(VIOLATING_TRANSCRIPT))

    def test_empty_transcript_false(self):
        self.assertFalse(gc.compute_init_chain_complete([]))

    def test_out_of_order_chain_reads_then_other_tool_false(self):
        transcript = [
            _tool_use_event("mcp__plugin_swe_serena__read_memory", {"memory_name": "wf/WF_CLASSIFY"}),
            _tool_use_event("mcp__plugin_swe_serena__read_memory", {"memory_name": "wf/WF_INIT"}),
            _tool_use_event("Bash", {"command": "ls"}),
        ]
        self.assertFalse(gc.compute_init_chain_complete(transcript))

    def test_list_memories_before_chain_complete_does_not_break_it(self):
        transcript = [
            _tool_use_event("mcp__plugin_swe_serena__list_memories", {}),
            _tool_use_event("mcp__plugin_swe_serena__read_memory", {"memory_name": "wf/WF_INIT"}),
            _tool_use_event("mcp__plugin_swe_serena__read_memory", {"memory_name": "claude/CLAUDE_OBLIGATIONS"}),
            _tool_use_event("mcp__plugin_swe_serena__read_memory", {"memory_name": "wf/WF_CLASSIFY"}),
        ]
        self.assertTrue(gc.compute_init_chain_complete(transcript))

    def test_toolsearch_before_first_read_does_not_break_chain(self):
        # Real shape from results/20260929-123133/runs/baseline-t1: a
        # ToolSearch call to load read_memory's deferred schema precedes the
        # very first read_memory tool_use.
        transcript = [
            _tool_use_event("ToolSearch", {"query": "select:mcp__plugin_swe_serena__read_memory"}),
            _tool_use_event("mcp__plugin_swe_serena__read_memory", {"memory_name": "wf/WF_INIT"}),
            _tool_use_event("mcp__plugin_swe_serena__read_memory", {"memory_name": "claude/CLAUDE_OBLIGATIONS"}),
            _tool_use_event("mcp__plugin_swe_serena__read_memory", {"memory_name": "wf/WF_CLASSIFY"}),
        ]
        self.assertTrue(gc.compute_init_chain_complete(transcript))

    def test_subagent_events_still_count(self):
        transcript = [
            _tool_use_event("mcp__plugin_swe_serena__read_memory", {"memory_name": "wf/WF_INIT"}, parent="t1"),
            _tool_use_event("mcp__plugin_swe_serena__read_memory", {"memory_name": "claude/CLAUDE_OBLIGATIONS"}, parent="t1"),
            _tool_use_event("mcp__plugin_swe_serena__read_memory", {"memory_name": "wf/WF_CLASSIFY"}, parent="t1"),
        ]
        self.assertTrue(gc.compute_init_chain_complete(transcript))


class SweepVerifiedTest(unittest.TestCase):
    def test_conforming_true(self):
        self.assertTrue(gc.compute_sweep_verified(CONFORMING_STREAM))
        self.assertEqual(gc.find_sweep_index(CONFORMING_STREAM), 7)

    def test_no_sweep_false(self):
        stream = [{"t": 1, "type": "docread", "s": "x", "name": "wf/WF_INIT"}]
        self.assertFalse(gc.compute_sweep_verified(stream))
        self.assertIsNone(gc.find_sweep_index(stream))

    def test_empty_stream_false(self):
        self.assertFalse(gc.compute_sweep_verified([]))


class EditsBeforeSweepTest(unittest.TestCase):
    def test_conforming_run_zero_edits_before_sweep(self):
        # both edit stream events occur after index 7 (the sweep)
        self.assertEqual(gc.compute_edits_before_sweep(CONFORMING_STREAM, CONFORMING_TRANSCRIPT), 0)

    def test_violating_run_edit_before_sweep_counted(self):
        # VIOLATING_STREAM: edit at index 1, sweep at index 3 -> 1 edit before sweep
        self.assertEqual(gc.compute_edits_before_sweep(VIOLATING_STREAM, VIOLATING_TRANSCRIPT), 1)

    def test_no_sweep_at_all_counts_all_stream_edits(self):
        stream = [
            {"t": 1, "type": "edit", "file": "a.py", "s": "x"},
            {"t": 2, "type": "edit", "file": "b.py", "s": "x"},
        ]
        self.assertEqual(gc.compute_edits_before_sweep(stream, []), 2)

    def test_no_stream_edit_events_falls_back_to_transcript(self):
        # empty stream (e.g. control arm with no plugin) -> count transcript
        # Edit/Write/NotebookEdit tool_use events.
        transcript = [
            _tool_use_event("Edit", {"file_path": "a.py"}),
            _tool_use_event("Write", {"file_path": "b.py"}),
            _tool_use_event("Bash", {"command": "ls"}),
        ]
        self.assertEqual(gc.compute_edits_before_sweep([], transcript), 2)

    def test_no_stream_no_transcript_edits_zero(self):
        self.assertEqual(gc.compute_edits_before_sweep([], []), 0)


class MemoriesReadTest(unittest.TestCase):
    def test_conforming_run_ordered_unique(self):
        result = gc.compute_memories_read(CONFORMING_TRANSCRIPT, CONFORMING_STREAM)
        expected = [
            "wf/wf_init", "claude/claude_obligations", "wf/wf_classify",
            "index/index_features", "feature/feature_ledger", "dom/dom_ledger_rules",
        ]
        self.assertEqual(result, expected)

    def test_transcript_only_reads_included(self):
        stream = []
        transcript = [
            _tool_use_event("mcp__plugin_swe_serena__read_memory", {"memory_name": "wf/WF_INIT"}),
        ]
        self.assertEqual(gc.compute_memories_read(transcript, stream), ["wf/wf_init"])

    def test_dedup_across_channels(self):
        stream = [{"t": 1, "type": "docread", "s": "x", "name": "wf/WF_INIT"}]
        transcript = [
            _tool_use_event("mcp__plugin_swe_serena__read_memory", {"memory_name": "wf/WF_INIT"}),
        ]
        self.assertEqual(gc.compute_memories_read(transcript, stream), ["wf/wf_init"])

    def test_empty_both(self):
        self.assertEqual(gc.compute_memories_read([], []), [])


class ControlMemoriesReadTest(unittest.TestCase):
    def test_plain_reads_of_memory_files_detected(self):
        result = gc.compute_control_memories_read(CONTROL_TRANSCRIPT)
        self.assertEqual(result, ["feature/feature_ledger", "dom/dom_ledger_rules"])

    def test_non_memory_reads_ignored(self):
        transcript = [_tool_use_event("Read", {"file_path": "/work/ledgerlite/money.py"})]
        self.assertEqual(gc.compute_control_memories_read(transcript), [])

    def test_memories_plural_dir_also_matched(self):
        transcript = [_tool_use_event("Read", {"file_path": "/work/.serena/memories/ref/REF_X.md"})]
        self.assertEqual(gc.compute_control_memories_read(transcript), ["ref/ref_x"])

    def test_empty_transcript(self):
        self.assertEqual(gc.compute_control_memories_read([]), [])


class DocRuleMemoriesCoverageTest(unittest.TestCase):
    DOC_RULES = [
        {"id": "R1", "memory": "dom/DOM_LEDGER_RULES", "summary": "x", "tests": ["t1"]},
        {"id": "R2", "memory": "ref/REF_CLI_OUTPUT", "summary": "y", "tests": ["t2"]},
    ]

    def test_full_coverage(self):
        read = ["wf/wf_init", "dom/dom_ledger_rules", "ref/ref_cli_output"]
        result = gc.compute_doc_rule_memories_coverage(read, self.DOC_RULES)
        self.assertEqual(result["doc_rule_memories_coverage"], 1.0)
        self.assertEqual(sorted(result["doc_rule_memories_read"]),
                          ["dom/dom_ledger_rules", "ref/ref_cli_output"])

    def test_partial_coverage(self):
        read = ["dom/dom_ledger_rules"]
        result = gc.compute_doc_rule_memories_coverage(read, self.DOC_RULES)
        self.assertEqual(result["doc_rule_memories_coverage"], 0.5)

    def test_zero_coverage(self):
        result = gc.compute_doc_rule_memories_coverage([], self.DOC_RULES)
        self.assertEqual(result["doc_rule_memories_coverage"], 0.0)

    def test_no_doc_rules_returns_none(self):
        result = gc.compute_doc_rule_memories_coverage(["x"], [])
        self.assertIsNone(result["doc_rule_memories_coverage"])
        result2 = gc.compute_doc_rule_memories_coverage(["x"], None)
        self.assertIsNone(result2["doc_rule_memories_coverage"])

    def test_dedups_rule_memories(self):
        rules = [
            {"id": "R1", "memory": "dom/DOM_X", "tests": []},
            {"id": "R2", "memory": "dom/DOM_X", "tests": []},
        ]
        result = gc.compute_doc_rule_memories_coverage(["dom/dom_x"], rules)
        self.assertEqual(result["doc_rule_memories_coverage"], 1.0)
        self.assertEqual(result["doc_rule_memories_read"], ["dom/dom_x"])


class StatesVisitedTest(unittest.TestCase):
    def test_conforming_run(self):
        self.assertEqual(gc.compute_states_visited(CONFORMING_STREAM), ["WF_EXECUTE"])

    def test_multiple_transitions_ordered(self):
        stream = [
            {"type": "state", "from_s": "WF_CLASSIFY", "to_s": "WF_ARCH_REVIEW"},
            {"type": "state", "from_s": "WF_ARCH_REVIEW", "to_s": "WF_EXECUTE"},
            {"type": "state", "from_s": "WF_EXECUTE", "to_s": "WF_VERIFY"},
        ]
        self.assertEqual(gc.compute_states_visited(stream), ["WF_ARCH_REVIEW", "WF_EXECUTE", "WF_VERIFY"])

    def test_empty(self):
        self.assertEqual(gc.compute_states_visited([]), [])


class GateDenialsTest(unittest.TestCase):
    def test_violating_run_classified(self):
        result = gc.compute_gate_denials(VIOLATING_TRANSCRIPT)
        self.assertEqual(result["init"], 1)
        self.assertEqual(result["sweep"], 1)
        self.assertEqual(result["edit"], 0)
        self.assertEqual(result["docs"], 0)

    def test_conforming_run_zero_denials(self):
        result = gc.compute_gate_denials(CONFORMING_TRANSCRIPT)
        self.assertEqual(sum(result.values()), 0)

    def test_stop_block_counted(self):
        transcript = [_text_event("Stop hook prevented completion of this turn.")]
        result = gc.compute_gate_denials(transcript)
        self.assertEqual(result["stop"], 1)

    def test_unclassified_error_bucketed(self):
        transcript = [_tool_deny_event("some random tool failure, not a gate")]
        result = gc.compute_gate_denials(transcript)
        self.assertEqual(result["unclassified"], 1)


class ComputeGateConformanceTest(unittest.TestCase):
    DOC_RULES = [{"id": "R1", "memory": "dom/DOM_LEDGER_RULES", "tests": []}]

    def test_conforming_plugin_run(self):
        result = gc.compute_gate_conformance(CONFORMING_STREAM, CONFORMING_TRANSCRIPT,
                                              doc_rules=self.DOC_RULES, is_plugin_arm=True)
        self.assertTrue(result["init_chain_complete"])
        self.assertTrue(result["sweep_verified"])
        self.assertEqual(result["edits_before_sweep"], 0)
        self.assertEqual(result["doc_rule_memories_coverage"], 1.0)
        self.assertEqual(result["memories_read_channel"], "serena+stream")
        self.assertEqual(result["states_visited"], ["WF_EXECUTE"])

    def test_violating_plugin_run(self):
        result = gc.compute_gate_conformance(VIOLATING_STREAM, VIOLATING_TRANSCRIPT,
                                              doc_rules=self.DOC_RULES, is_plugin_arm=True)
        self.assertFalse(result["init_chain_complete"])
        self.assertEqual(result["edits_before_sweep"], 1)
        self.assertEqual(result["gate_denials"]["init"], 1)
        self.assertEqual(result["gate_denials"]["sweep"], 1)

    def test_control_run(self):
        result = gc.compute_gate_conformance([], CONTROL_TRANSCRIPT,
                                              doc_rules=self.DOC_RULES, is_plugin_arm=False)
        self.assertFalse(result["init_chain_complete"])
        self.assertFalse(result["sweep_verified"])
        self.assertEqual(result["memories_read_channel"], "plain_read")
        self.assertEqual(result["memories_read"], ["feature/feature_ledger", "dom/dom_ledger_rules"])
        self.assertEqual(result["doc_rule_memories_coverage"], 1.0)
        # control arm has no sweep gate at all -> the one Edit counts as
        # "before sweep" (no gate exists to have blocked it)
        self.assertEqual(result["edits_before_sweep"], 1)


class FindPivotBoundaryTimestampTest(unittest.TestCase):
    def test_finds_resume_marker(self):
        stream = [
            {"t": 1, "type": "docread", "name": "wf/WF_INIT"},
            {"t": 5, "type": "sweep"},
            {"t": 10, "type": "resume"},
            {"t": 12, "type": "edit"},
        ]
        self.assertEqual(gc.find_pivot_boundary_timestamp(stream), 10)

    def test_finds_session_boot_marker(self):
        stream = [{"t": 1, "type": "docread"}, {"t": 9, "type": "session_boot"}]
        self.assertEqual(gc.find_pivot_boundary_timestamp(stream), 9)

    def test_falls_back_when_no_marker(self):
        stream = [{"t": 1, "type": "docread"}]
        self.assertEqual(gc.find_pivot_boundary_timestamp(stream, fallback_ts=99), 99)

    def test_returns_none_when_no_marker_and_no_fallback(self):
        self.assertIsNone(gc.find_pivot_boundary_timestamp([], fallback_ts=None))


class SplitEventsAtPivotBoundaryTest(unittest.TestCase):
    def test_splits_stream_on_timestamp(self):
        stream = [
            {"t": 1, "type": "docread"},
            {"t": 5, "type": "sweep"},
            {"t": 10, "type": "resume"},
            {"t": 12, "type": "state", "to_s": "WF_CLASSIFY"},
        ]
        task1_window, pivot_window = gc.split_events_at_pivot_boundary(stream, [], boundary_ts=10)
        self.assertEqual(len(task1_window["stream"]), 2)
        self.assertEqual(len(pivot_window["stream"]), 2)
        self.assertEqual(pivot_window["stream"][0]["type"], "resume")

    def test_event_with_no_timestamp_stays_in_task1(self):
        stream = [{"type": "gated"}]  # no 't' field
        task1_window, pivot_window = gc.split_events_at_pivot_boundary(stream, [], boundary_ts=5)
        self.assertEqual(len(task1_window["stream"]), 1)
        self.assertEqual(len(pivot_window["stream"]), 0)


class ComputePivotReclassifiedTest(unittest.TestCase):
    def test_succeeded_true_when_state_event_present(self):
        pivot_stream = [{"t": 20, "type": "state", "from_s": "WF_EXECUTE", "to_s": "WF_CLASSIFY"}]
        result = gc.compute_pivot_reclassified_from_streams(pivot_stream, [])
        self.assertTrue(result["succeeded"])
        self.assertTrue(result["attempted"])

    def test_attempted_true_succeeded_false_on_denied_transition(self):
        # v1.2.82-era plugin build: EXECUTE->CLASSIFY missing as a valid FSM
        # edge, so no 'state' stream event fires, but the hook denial text
        # mentions WF_CLASSIFY.
        pivot_transcript = [
            {"type": "assistant", "message": {"content": [{"type": "tool_use",
                "name": "mcp__plugin_swe_serena__set_state", "input": {}}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "is_error": True,
                "content": "cannot transition to WF_CLASSIFY from WF_EXECUTE"}]}},
        ]
        result = gc.compute_pivot_reclassified_from_streams([], pivot_transcript)
        self.assertFalse(result["succeeded"])
        self.assertTrue(result["attempted"])

    def test_neither_attempted_nor_succeeded(self):
        result = gc.compute_pivot_reclassified_from_streams([], [])
        self.assertFalse(result["succeeded"])
        self.assertFalse(result["attempted"])


class ComputePivotResweepVerifiedTest(unittest.TestCase):
    def test_true_when_pivot_window_has_its_own_sweep(self):
        pivot_stream = [{"t": 20, "type": "sweep"}]
        self.assertTrue(gc.compute_pivot_resweep_verified(pivot_stream))

    def test_false_when_pivot_window_has_no_sweep(self):
        # task1's sweep lives in the task1 window, not this one.
        pivot_stream = [{"t": 20, "type": "edit"}]
        self.assertFalse(gc.compute_pivot_resweep_verified(pivot_stream))


class ComputePivotEditsBeforeSweepTest(unittest.TestCase):
    def test_counts_edits_in_pivot_window_before_new_sweep(self):
        pivot_stream = [
            {"t": 21, "type": "edit", "file": "a.py"},
            {"t": 22, "type": "sweep"},
        ]
        pivot_transcript = [
            {"type": "assistant", "message": {"content": [{"type": "tool_use",
                "name": "Edit", "input": {"file_path": "a.py"}}]}},
        ]
        self.assertEqual(gc.compute_pivot_edits_before_sweep(pivot_stream, pivot_transcript), 1)

    def test_zero_when_sweep_happens_first(self):
        pivot_stream = [{"t": 20, "type": "sweep"}, {"t": 21, "type": "edit", "file": "a.py"}]
        self.assertEqual(gc.compute_pivot_edits_before_sweep(pivot_stream, []), 0)


class ComputeGateConformancePivotTest(unittest.TestCase):
    PIVOT_DOC_RULES = [{"id": "P1", "memory": "dom/DOM_PIVOT_RULE", "tests": []}]

    def test_full_pivot_shape_includes_pivot_keys(self):
        pivot_stream = [
            {"t": 20, "type": "docread", "s": "s1", "name": "dom/DOM_PIVOT_RULE"},
            {"t": 21, "type": "sweep", "s": "s1"},
            {"t": 22, "type": "edit", "file": "a.py", "s": "s1"},
            {"t": 23, "type": "state", "from_s": "WF_EXECUTE", "to_s": "WF_CLASSIFY", "s": "s1"},
        ]
        pivot_transcript = [
            {"type": "assistant", "message": {"content": [{"type": "tool_use",
                "name": "mcp__plugin_swe_serena__read_memory",
                "input": {"memory_name": "dom/DOM_PIVOT_RULE"}}]}},
            {"type": "assistant", "message": {"content": [{"type": "tool_use",
                "name": "Edit", "input": {"file_path": "a.py"}}]}},
        ]
        result = gc.compute_gate_conformance_pivot(
            pivot_stream, pivot_transcript, pivot_doc_rules=self.PIVOT_DOC_RULES,
            is_plugin_arm=True)
        self.assertIn("pivot_reclassified", result)
        self.assertTrue(result["pivot_reclassified"]["succeeded"])
        self.assertTrue(result["pivot_resweep_verified"])
        self.assertEqual(result["pivot_edits_before_sweep"], 0)
        self.assertEqual(result["pivot_memories_read"], ["dom/dom_pivot_rule"])
        self.assertEqual(result["pivot_doc_rule_memories_coverage"], 1.0)
        # base-shape keys are still present (init_chain_complete included
        # for shape consistency even though a pivot window never re-runs
        # WF_INIT).
        self.assertIn("init_chain_complete", result)

    def test_control_arm_pivot_uses_plain_read_channel(self):
        pivot_transcript = [
            {"type": "assistant", "message": {"content": [{"type": "tool_use",
                "name": "Read", "input": {"file_path": ".serena/memory/dom/DOM_PIVOT_RULE.md"}}]}},
        ]
        result = gc.compute_gate_conformance_pivot(
            [], pivot_transcript, pivot_doc_rules=self.PIVOT_DOC_RULES, is_plugin_arm=False)
        self.assertEqual(result["memories_read_channel"], "plain_read")
        self.assertEqual(result["pivot_memories_read"], ["dom/dom_pivot_rule"])
        self.assertFalse(result["pivot_resweep_verified"])


if __name__ == "__main__":
    unittest.main()
