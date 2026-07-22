"""Tests for swe_hooks.core.stream — append-only JSONL event tracking.

All counting functions take an EXPLICIT stream_path, so they are tested against
real temp files with no monkeypatching. get_stream_path / get_sentinel_path
resolve their directory through swe_hooks.core.config.get_project_root, which is
monkeypatched to a tmpdir.
"""
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_core, reset_caches  # noqa: E402

stream = import_core("swe_hooks.core.stream")
config = import_core("swe_hooks.core.config")


class BaseStreamTest(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = self.tmp.name
        self.stream_path = os.path.join(self.tmpdir, "session.jsonl")

    def tearDown(self):
        self.tmp.cleanup()
        reset_caches()

    def _write_jsonl(self, events):
        """Write a list of event dicts as JSONL to self.stream_path."""
        with open(self.stream_path, "w") as f:
            for ev in events:
                f.write(json.dumps(ev, separators=(",", ":")) + "\n")

    def _read_lines(self):
        with open(self.stream_path, "r") as f:
            return [ln for ln in f.read().splitlines() if ln.strip()]


class TestAppendEvent(BaseStreamTest):
    def test_writes_one_valid_json_line(self):
        stream.append_event(self.stream_path, "tool")
        lines = self._read_lines()
        self.assertEqual(len(lines), 1)
        event = json.loads(lines[0])
        self.assertEqual(event["type"], "tool")
        self.assertIn("t", event)
        self.assertIsInstance(event["t"], int)

    def test_timestamp_is_plausible_epoch_int(self):
        before = int(time.time())
        stream.append_event(self.stream_path, "state")
        after = int(time.time())
        event = json.loads(self._read_lines()[0])
        # Assert structure/range, not exact value.
        self.assertGreaterEqual(event["t"], before)
        self.assertLessEqual(event["t"], after)

    def test_extra_data_is_merged_into_event(self):
        stream.append_event(self.stream_path, "edit", path="foo.py", n=3)
        event = json.loads(self._read_lines()[0])
        self.assertEqual(event["type"], "edit")
        self.assertEqual(event["path"], "foo.py")
        self.assertEqual(event["n"], 3)

    def test_file_grows_by_one_line_each_call(self):
        for i in range(1, 6):
            stream.append_event(self.stream_path, "tool", i=i)
            self.assertEqual(len(self._read_lines()), i)
        # Every line is valid JSON with a type field.
        for ln in self._read_lines():
            ev = json.loads(ln)
            self.assertEqual(ev["type"], "tool")

    def test_creates_missing_parent_directories(self):
        nested = os.path.join(self.tmpdir, "a", "b", "c", "session.jsonl")
        self.assertFalse(os.path.exists(os.path.dirname(nested)))
        stream.append_event(nested, "tool")
        self.assertTrue(os.path.exists(nested))
        with open(nested) as f:
            event = json.loads(f.read().splitlines()[0])
        self.assertEqual(event["type"], "tool")

    def test_data_can_override_type_key(self):
        # event.update(data) runs after type is set, so an explicit type in data wins.
        stream.append_event(self.stream_path, "tool", type="override")
        event = json.loads(self._read_lines()[0])
        self.assertEqual(event["type"], "override")

    def test_appends_do_not_truncate(self):
        stream.append_event(self.stream_path, "state")
        stream.append_event(self.stream_path, "edit")
        types = [json.loads(ln)["type"] for ln in self._read_lines()]
        self.assertEqual(types, ["state", "edit"])


class TestGetEventCount(BaseStreamTest):
    def test_missing_file_returns_zero(self):
        self.assertEqual(stream.get_event_count(self.stream_path), 0)

    def test_empty_file_returns_zero(self):
        open(self.stream_path, "w").close()
        self.assertEqual(stream.get_event_count(self.stream_path), 0)

    def test_counts_n_appends(self):
        for _ in range(7):
            stream.append_event(self.stream_path, "tool")
        self.assertEqual(stream.get_event_count(self.stream_path), 7)

    def test_counts_lines_including_non_json(self):
        # get_event_count is a raw line count (sum over binary handle).
        with open(self.stream_path, "w") as f:
            f.write('{"t":1,"type":"a"}\n')
            f.write("garbage not json\n")
            f.write('{"t":2,"type":"b"}\n')
        self.assertEqual(stream.get_event_count(self.stream_path), 3)

    def test_returns_int(self):
        stream.append_event(self.stream_path, "tool")
        self.assertIsInstance(stream.get_event_count(self.stream_path), int)


class TestCountEventsSinceLast(BaseStreamTest):
    def test_missing_file_returns_zero(self):
        self.assertEqual(stream.count_events_since_last(self.stream_path), 0)

    def test_no_marker_counts_all_matching(self):
        self._write_jsonl([
            {"t": 1, "type": "edit"},
            {"t": 2, "type": "tool"},
            {"t": 3, "type": "edit"},
            {"t": 4, "type": "edit"},
        ])
        self.assertEqual(
            stream.count_events_since_last(self.stream_path,
                                           marker_types=("state", "checkpoint"),
                                           count_type="edit"),
            3,
        )

    def test_marker_resets_count(self):
        self._write_jsonl([
            {"t": 1, "type": "edit"},
            {"t": 2, "type": "edit"},
            {"t": 3, "type": "state"},   # marker resets
            {"t": 4, "type": "edit"},
            {"t": 5, "type": "edit"},
        ])
        self.assertEqual(
            stream.count_events_since_last(self.stream_path,
                                           marker_types=("state", "checkpoint"),
                                           count_type="edit"),
            2,
        )

    def test_only_counts_since_LAST_marker(self):
        self._write_jsonl([
            {"t": 1, "type": "checkpoint"},
            {"t": 2, "type": "edit"},
            {"t": 3, "type": "state"},   # this is the last marker
            {"t": 4, "type": "edit"},
        ])
        self.assertEqual(
            stream.count_events_since_last(self.stream_path,
                                           marker_types=("state", "checkpoint"),
                                           count_type="edit"),
            1,
        )

    def test_marker_at_end_yields_zero(self):
        self._write_jsonl([
            {"t": 1, "type": "edit"},
            {"t": 2, "type": "state"},
        ])
        self.assertEqual(
            stream.count_events_since_last(self.stream_path,
                                           marker_types=("state", "checkpoint"),
                                           count_type="edit"),
            0,
        )

    def test_ignores_non_count_non_marker_types(self):
        self._write_jsonl([
            {"t": 1, "type": "edit"},
            {"t": 2, "type": "tool"},
            {"t": 3, "type": "search"},
            {"t": 4, "type": "edit"},
        ])
        self.assertEqual(
            stream.count_events_since_last(self.stream_path,
                                           marker_types=("state", "checkpoint"),
                                           count_type="edit"),
            2,
        )

    def test_malformed_lines_are_skipped(self):
        with open(self.stream_path, "w") as f:
            f.write('{"t":1,"type":"edit"}\n')
            f.write("this is not json\n")
            f.write("\n")  # blank line
            f.write('{"t":2,"type":"edit"}\n')
        self.assertEqual(
            stream.count_events_since_last(self.stream_path,
                                           marker_types=("state", "checkpoint"),
                                           count_type="edit"),
            2,
        )

    def test_custom_marker_and_count_types(self):
        self._write_jsonl([
            {"t": 1, "type": "search"},
            {"t": 2, "type": "docread"},   # custom marker
            {"t": 3, "type": "search"},
            {"t": 4, "type": "search"},
        ])
        self.assertEqual(
            stream.count_events_since_last(self.stream_path,
                                           marker_types=("docread",),
                                           count_type="search"),
            2,
        )

    def test_large_file_seek_boundary_counts_since_last_marker(self):
        # Build a file well over 10KB so the seek-to-last-10KB branch runs.
        # Layout: lots of edits, then a marker, then a known number of edits.
        # The marker must fall within the last 10KB window so it is seen.
        events = []
        for i in range(2000):  # padding, each line ~30+ bytes => >>10KB
            events.append({"t": i, "type": "edit", "pad": "x" * 20})
        events.append({"t": 9000, "type": "state"})  # last marker
        for i in range(5):
            events.append({"t": 9001 + i, "type": "edit"})
        self._write_jsonl(events)
        self.assertGreater(os.path.getsize(self.stream_path), 10240)
        self.assertEqual(
            stream.count_events_since_last(self.stream_path,
                                           marker_types=("state", "checkpoint"),
                                           count_type="edit"),
            5,
        )

    def test_large_file_no_marker_in_window_counts_window_edits(self):
        # Over 10KB with NO marker anywhere; only edits inside the last-10KB
        # window are counted (the partial first line is skipped). We assert the
        # count is positive and bounded by total edits — the seek path is
        # exercised without depending on the exact window size.
        events = [{"t": i, "type": "edit", "pad": "y" * 40} for i in range(1000)]
        self._write_jsonl(events)
        self.assertGreater(os.path.getsize(self.stream_path), 10240)
        count = stream.count_events_since_last(self.stream_path,
                                               marker_types=("state", "checkpoint"),
                                               count_type="edit")
        self.assertGreater(count, 0)
        self.assertLess(count, 1000)  # only the tail window, not the whole file


class TestCountEditsSinceCheckpoint(BaseStreamTest):
    def test_default_markers_state_and_checkpoint(self):
        # No marker -> counts all edits.
        self._write_jsonl([
            {"t": 1, "type": "edit"},
            {"t": 2, "type": "edit"},
            {"t": 3, "type": "edit"},
        ])
        self.assertEqual(stream.count_edits_since_checkpoint(self.stream_path), 3)

    def test_checkpoint_marker_resets(self):
        self._write_jsonl([
            {"t": 1, "type": "edit"},
            {"t": 2, "type": "checkpoint"},  # reset
            {"t": 3, "type": "edit"},
        ])
        self.assertEqual(stream.count_edits_since_checkpoint(self.stream_path), 1)

    def test_state_marker_resets(self):
        self._write_jsonl([
            {"t": 1, "type": "edit"},
            {"t": 2, "type": "edit"},
            {"t": 3, "type": "state"},  # reset
            {"t": 4, "type": "edit"},
        ])
        self.assertEqual(stream.count_edits_since_checkpoint(self.stream_path), 1)

    def test_searches_do_not_count_as_edits(self):
        self._write_jsonl([
            {"t": 1, "type": "search"},
            {"t": 2, "type": "edit"},
        ])
        self.assertEqual(stream.count_edits_since_checkpoint(self.stream_path), 1)

    def test_missing_file_zero(self):
        self.assertEqual(stream.count_edits_since_checkpoint(self.stream_path), 0)


class TestCountSearchesSinceDocread(BaseStreamTest):
    def test_counts_searches_with_no_marker(self):
        self._write_jsonl([
            {"t": 1, "type": "search"},
            {"t": 2, "type": "search"},
        ])
        self.assertEqual(stream.count_searches_since_docread(self.stream_path), 2)

    def test_docread_marker_resets(self):
        self._write_jsonl([
            {"t": 1, "type": "search"},
            {"t": 2, "type": "search"},
            {"t": 3, "type": "docread"},  # reset
            {"t": 4, "type": "search"},
        ])
        self.assertEqual(stream.count_searches_since_docread(self.stream_path), 1)

    def test_state_marker_resets_searches(self):
        self._write_jsonl([
            {"t": 1, "type": "search"},
            {"t": 2, "type": "state"},  # reset
            {"t": 3, "type": "search"},
            {"t": 4, "type": "search"},
        ])
        self.assertEqual(stream.count_searches_since_docread(self.stream_path), 2)

    def test_checkpoint_marker_resets_searches(self):
        self._write_jsonl([
            {"t": 1, "type": "search"},
            {"t": 2, "type": "checkpoint"},  # reset
            {"t": 3, "type": "search"},
        ])
        self.assertEqual(stream.count_searches_since_docread(self.stream_path), 1)

    def test_edits_do_not_count_as_searches(self):
        self._write_jsonl([
            {"t": 1, "type": "edit"},
            {"t": 2, "type": "search"},
            {"t": 3, "type": "edit"},
        ])
        self.assertEqual(stream.count_searches_since_docread(self.stream_path), 1)

    def test_missing_file_zero(self):
        self.assertEqual(stream.count_searches_since_docread(self.stream_path), 0)


class TestPathHelpers(unittest.TestCase):
    """get_stream_path / get_sentinel_path resolve via config.get_project_root."""

    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = self.tmp.name
        self._orig_get_root = config.get_project_root
        config.get_project_root = lambda: self.tmpdir

    def tearDown(self):
        config.get_project_root = self._orig_get_root
        self.tmp.cleanup()
        reset_caches()

    def test_get_stream_dir_creates_serena_streams(self):
        d = stream.get_stream_dir()
        self.assertEqual(d, os.path.join(self.tmpdir, ".serena", "streams"))
        self.assertTrue(os.path.isdir(d))

    def test_get_stream_path_suffix_and_basename(self):
        p = stream.get_stream_path("abc123")
        self.assertTrue(p.endswith(".jsonl"))
        self.assertEqual(os.path.basename(p), "abc123.jsonl")
        self.assertEqual(
            p, os.path.join(self.tmpdir, ".serena", "streams", "abc123.jsonl")
        )

    def test_get_sentinel_path_prefix_and_basename(self):
        p = stream.get_sentinel_path("abc123")
        self.assertEqual(os.path.basename(p), ".init_abc123")
        self.assertEqual(
            p, os.path.join(self.tmpdir, ".serena", "streams", ".init_abc123")
        )

    def test_stream_and_sentinel_share_directory(self):
        sp = stream.get_stream_path("sid")
        sen = stream.get_sentinel_path("sid")
        self.assertEqual(os.path.dirname(sp), os.path.dirname(sen))


if __name__ == "__main__":
    unittest.main()
