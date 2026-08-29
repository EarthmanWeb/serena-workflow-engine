"""Tests for swe_hooks.core.config — pure parsers, version tuples, setup-state
resolution, and the injectable IO helpers (setup json read, prior-use detection,
legacy migration).

Only functions that are cleanly testable in isolation are covered here. IO
helpers are exercised against a real tempfile.TemporaryDirectory so nothing
touches the developer's project or a real Serena server. Every assertion was
verified against the actual source in hooks/swe_hooks/core/config.py.

Stdlib unittest only; no third-party deps.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_core, reset_caches  # noqa: E402

config = import_core("swe_hooks.core.config")


class TestParseWorkingMemoryState(unittest.TestCase):
    def setUp(self):
        reset_caches()

    def tearDown(self):
        reset_caches()

    def test_defaults_when_no_workflow_context(self):
        # Content with no '## Workflow Context' section -> all defaults.
        state = config.parse_working_memory_state("# Some WM\n\nnothing here")
        self.assertEqual(state["current_state"], "WF_INIT")
        self.assertEqual(state["feature_keys"], [])
        self.assertIsNone(state["session_id"])
        self.assertIsNone(state["return_step"])
        self.assertEqual(state["invocation_mode"], "workflow")
        self.assertEqual(state["status"], "Starting")

    def test_empty_content(self):
        state = config.parse_working_memory_state("")
        self.assertEqual(state["current_state"], "WF_INIT")
        self.assertEqual(state["feature_keys"], [])
        self.assertIsNone(state["session_id"])
        self.assertEqual(state["invocation_mode"], "workflow")
        self.assertEqual(state["status"], "Starting")

    def test_all_fields_present(self):
        content = (
            "# WM\n\n"
            "## Workflow Context\n"
            "**Current State**: WF_EXECUTE\n"
            "**Feature Key(s)**: SWE, AUTH, DB\n"
            "**Session ID**: abc12345\n"
            "**Return Step**: WF_VERIFY\n"
            "**Invocation Mode**: research\n"
            "\n"
            "## Session Context\n"
            "**Status**: In progress on task\n"
        )
        state = config.parse_working_memory_state(content)
        self.assertEqual(state["current_state"], "WF_EXECUTE")
        self.assertEqual(state["feature_keys"], ["SWE", "AUTH", "DB"])
        self.assertEqual(state["session_id"], "abc12345")
        self.assertEqual(state["return_step"], "WF_VERIFY")
        self.assertEqual(state["invocation_mode"], "research")
        self.assertEqual(state["status"], "In progress on task")

    def test_calling_step_fallback_when_no_current_state(self):
        # When 'Current State' absent, 'Calling Step' provides current_state.
        content = (
            "## Workflow Context\n"
            "**Calling Step**: WF_CLASSIFY\n"
        )
        state = config.parse_working_memory_state(content)
        self.assertEqual(state["current_state"], "WF_CLASSIFY")

    def test_current_state_takes_priority_over_calling_step(self):
        content = (
            "## Workflow Context\n"
            "**Current State**: WF_EXECUTE\n"
            "**Calling Step**: WF_CLASSIFY\n"
        )
        state = config.parse_working_memory_state(content)
        self.assertEqual(state["current_state"], "WF_EXECUTE")

    def test_feature_keys_single_value_stripped(self):
        content = "## Workflow Context\n**Feature Key(s)**:   SWE  \n"
        state = config.parse_working_memory_state(content)
        self.assertEqual(state["feature_keys"], ["SWE"])

    def test_status_parsed_from_anywhere_in_content(self):
        # Status regex runs against the whole content, not just the section.
        content = "# WM\n**Status**: Blocked on review\n\nmore text"
        state = config.parse_working_memory_state(content)
        self.assertEqual(state["status"], "Blocked on review")

    def test_workflow_context_section_terminated_by_next_heading(self):
        # Fields after the next '## ' heading must NOT be read as workflow ctx.
        content = (
            "## Workflow Context\n"
            "**Current State**: WF_RESEARCH\n"
            "## Other\n"
            "**Session ID**: shouldnotmatter\n"
        )
        state = config.parse_working_memory_state(content)
        self.assertEqual(state["current_state"], "WF_RESEARCH")
        # Session ID lives outside the workflow section -> stays default None.
        self.assertIsNone(state["session_id"])

    def test_returns_dict_type(self):
        self.assertIsInstance(config.parse_working_memory_state("x"), dict)


class TestVersionTuple(unittest.TestCase):
    def test_three_part_version(self):
        self.assertEqual(config._version_tuple("1.2.3"), (1, 2, 3))

    def test_two_part_version(self):
        self.assertEqual(config._version_tuple("1.2"), (1, 2))

    def test_single_number(self):
        self.assertEqual(config._version_tuple("7"), (7,))

    def test_non_numeric_returns_zero_tuple(self):
        # int('x') raises ValueError -> (0,)
        self.assertEqual(config._version_tuple("1.x.3"), (0,))

    def test_empty_string_returns_zero_tuple(self):
        # ''.split('.') -> [''] -> int('') raises ValueError -> (0,)
        self.assertEqual(config._version_tuple(""), (0,))

    def test_none_returns_zero_tuple(self):
        # None.split raises AttributeError -> (0,)
        self.assertEqual(config._version_tuple(None), (0,))

    def test_ordering_of_tuples(self):
        # The purpose of the function: version comparison via tuple ordering.
        self.assertLess(config._version_tuple("1.2.2"), config._version_tuple("1.2.3"))
        self.assertGreater(config._version_tuple("2.0.0"), config._version_tuple("1.9.9"))


class TestSetupFilePathBuilders(unittest.TestCase):
    def test_legacy_setup_file_path(self):
        root = "/some/project"
        self.assertEqual(
            config._legacy_setup_file(root),
            os.path.join(root, ".claude", "swe-setup-complete.json"),
        )

    def test_canonical_setup_file_path(self):
        root = "/some/project"
        self.assertEqual(
            config._canonical_setup_file(root),
            os.path.join(root, ".serena", "swe-setup-complete.json"),
        )

    def test_path_builders_are_pure_and_differ(self):
        root = "/p"
        self.assertNotEqual(
            config._legacy_setup_file(root), config._canonical_setup_file(root)
        )


class TestReadSetupJson(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_json(self):
        path = os.path.join(self.root, "setup.json")
        with open(path, "w") as f:
            json.dump({"complete": True, "version": "1.2.3"}, f)
        data = config._read_setup_json(path)
        self.assertEqual(data, {"complete": True, "version": "1.2.3"})

    def test_missing_file_returns_none(self):
        path = os.path.join(self.root, "does-not-exist.json")
        self.assertIsNone(config._read_setup_json(path))

    def test_malformed_json_returns_none(self):
        path = os.path.join(self.root, "bad.json")
        with open(path, "w") as f:
            f.write("{ this is not: valid json ,,, ")
        self.assertIsNone(config._read_setup_json(path))

    def test_empty_file_returns_none(self):
        path = os.path.join(self.root, "empty.json")
        with open(path, "w") as f:
            f.write("")
        self.assertIsNone(config._read_setup_json(path))


class TestHasPriorUse(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_serena_dir_is_false(self):
        self.assertFalse(config._has_prior_use(self.root))

    def test_empty_serena_dir_is_false(self):
        os.makedirs(os.path.join(self.root, ".serena"))
        self.assertFalse(config._has_prior_use(self.root))

    def test_state_file_marks_prior_use(self):
        state_dir = os.path.join(self.root, ".serena", "swe-state")
        os.makedirs(state_dir)
        with open(os.path.join(state_dir, "sess1.state"), "w") as f:
            f.write("{}")
        self.assertTrue(config._has_prior_use(self.root))

    def test_wm_file_marks_prior_use(self):
        mem_dir = os.path.join(self.root, ".serena", "memories")
        os.makedirs(mem_dir)
        with open(os.path.join(mem_dir, "WM_20260101.md"), "w") as f:
            f.write("# wm")
        self.assertTrue(config._has_prior_use(self.root))

    def test_non_matching_files_are_not_prior_use(self):
        # A memories dir with a non-WM file, and a state dir with no .state file.
        mem_dir = os.path.join(self.root, ".serena", "memories")
        os.makedirs(mem_dir)
        with open(os.path.join(mem_dir, "FEATURE_X.md"), "w") as f:
            f.write("# feature")
        state_dir = os.path.join(self.root, ".serena", "swe-state")
        os.makedirs(state_dir)
        with open(os.path.join(state_dir, "notes.txt"), "w") as f:
            f.write("x")
        self.assertFalse(config._has_prior_use(self.root))


class TestResolveSetupState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write_canonical(self, obj):
        path = config._canonical_setup_file(self.root)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(obj, f)

    def _write_legacy(self, obj):
        path = config._legacy_setup_file(self.root)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(obj, f)

    def test_pristine_project_none(self):
        r = config.resolve_setup_state(self.root)
        self.assertFalse(r["initialized"])
        self.assertFalse(r["complete"])
        self.assertFalse(r["bootstrapped"])
        self.assertFalse(r["bypassed"])
        self.assertEqual(r["source"], "none")
        self.assertFalse(r["needs_migration"])
        self.assertIsNone(r["data"])

    def test_canonical_complete(self):
        self._write_canonical({"complete": True})
        r = config.resolve_setup_state(self.root)
        self.assertTrue(r["initialized"])
        self.assertTrue(r["complete"])
        self.assertFalse(r["bootstrapped"])
        self.assertEqual(r["source"], "canonical")
        self.assertFalse(r["needs_migration"])
        self.assertEqual(r["data"], {"complete": True})

    def test_canonical_bootstrapped_not_complete(self):
        self._write_canonical({"bootstrapped": True})
        r = config.resolve_setup_state(self.root)
        self.assertTrue(r["initialized"])
        self.assertFalse(r["complete"])
        self.assertTrue(r["bootstrapped"])
        self.assertEqual(r["source"], "canonical")

    def test_canonical_bypassed(self):
        self._write_canonical({"complete": True, "bypass": True})
        r = config.resolve_setup_state(self.root)
        self.assertTrue(r["bypassed"])
        self.assertTrue(r["initialized"])

    def test_legacy_only_needs_migration(self):
        self._write_legacy({"complete": True})
        r = config.resolve_setup_state(self.root)
        self.assertTrue(r["initialized"])
        self.assertTrue(r["complete"])
        self.assertEqual(r["source"], "legacy")
        self.assertTrue(r["needs_migration"])
        self.assertEqual(r["data"], {"complete": True})

    def test_canonical_wins_over_legacy(self):
        # Both present: canonical is authoritative, no migration needed.
        self._write_canonical({"complete": True, "which": "canonical"})
        self._write_legacy({"complete": False, "which": "legacy"})
        r = config.resolve_setup_state(self.root)
        self.assertEqual(r["source"], "canonical")
        self.assertFalse(r["needs_migration"])
        self.assertEqual(r["data"]["which"], "canonical")
        self.assertTrue(r["complete"])

    def test_prior_use_source(self):
        # No setup json, but prior-use evidence (a state file) exists.
        state_dir = os.path.join(self.root, ".serena", "swe-state")
        os.makedirs(state_dir)
        with open(os.path.join(state_dir, "s.state"), "w") as f:
            f.write("{}")
        r = config.resolve_setup_state(self.root)
        self.assertTrue(r["initialized"])
        self.assertFalse(r["complete"])
        self.assertEqual(r["source"], "prior_use")
        self.assertFalse(r["needs_migration"])
        self.assertIsNone(r["data"])

    def test_returns_all_expected_keys(self):
        r = config.resolve_setup_state(self.root)
        for key in (
            "initialized", "complete", "bootstrapped", "bypassed",
            "source", "needs_migration", "data",
        ):
            self.assertIn(key, r)


class TestMigrateLegacySetupFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write_legacy(self, obj):
        path = config._legacy_setup_file(self.root)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(obj, f)

    def test_no_legacy_no_migration(self):
        self.assertFalse(config.migrate_legacy_setup_file(self.root))
        self.assertFalse(os.path.exists(config._canonical_setup_file(self.root)))

    def test_migrates_legacy_to_canonical(self):
        self._write_legacy({"complete": True})
        did = config.migrate_legacy_setup_file(self.root)
        self.assertTrue(did)
        canonical = config._canonical_setup_file(self.root)
        self.assertTrue(os.path.exists(canonical))
        with open(canonical) as f:
            data = json.load(f)
        self.assertTrue(data["complete"])
        # Migration stamps provenance.
        self.assertEqual(data["migrated_from"], ".claude/swe-setup-complete.json")

    def test_idempotent_second_call_is_noop(self):
        self._write_legacy({"complete": True})
        self.assertTrue(config.migrate_legacy_setup_file(self.root))
        # Second call: canonical already exists -> False (no write).
        self.assertFalse(config.migrate_legacy_setup_file(self.root))

    def test_no_migration_when_canonical_exists(self):
        # Canonical present, legacy present: no migration should occur.
        canonical = config._canonical_setup_file(self.root)
        os.makedirs(os.path.dirname(canonical), exist_ok=True)
        with open(canonical, "w") as f:
            json.dump({"complete": True, "which": "canonical"}, f)
        self._write_legacy({"complete": False, "which": "legacy"})
        self.assertFalse(config.migrate_legacy_setup_file(self.root))
        # Canonical is untouched.
        with open(canonical) as f:
            self.assertEqual(json.load(f)["which"], "canonical")

    def test_migration_preserves_existing_migrated_from(self):
        # setdefault must not overwrite an already-present migrated_from.
        self._write_legacy({"complete": True, "migrated_from": "custom-source"})
        self.assertTrue(config.migrate_legacy_setup_file(self.root))
        with open(config._canonical_setup_file(self.root)) as f:
            data = json.load(f)
        self.assertEqual(data["migrated_from"], "custom-source")


class TestCreateInitialState(unittest.TestCase):
    def test_shape_with_explicit_session_id(self):
        state = config.create_initial_state(session_id="x")
        self.assertEqual(state["session_id"], "x")
        self.assertEqual(state["current_state"], "UNINITIALIZED")
        self.assertIsNone(state["previous_state"])
        self.assertEqual(state["edits_since_checkpoint"], 0)
        self.assertFalse(state["is_subagent"])
        self.assertFalse(state["plan_mode"])
        self.assertIsNone(state["working_memory_file"])

    def test_all_keys_present(self):
        state = config.create_initial_state(session_id="abc")
        for key in (
            "session_id", "current_state", "previous_state",
            "edits_since_checkpoint", "is_subagent", "plan_mode",
            "working_memory_file",
        ):
            self.assertIn(key, state)

    def test_generates_session_id_when_none(self):
        # Without an explicit id, generate_session_id() supplies a timestamp id.
        state = config.create_initial_state()
        self.assertIsInstance(state["session_id"], str)
        self.assertTrue(state["session_id"])  # non-empty
        self.assertEqual(state["current_state"], "UNINITIALIZED")


class TestWriteStateFileStaleGuard(unittest.TestCase):
    """The stale-daemon guard in write_state_file must NOT brick a session
    whose state file is unowned or self-owned — only a strictly-newer owner
    (the real dual-daemon clobber race) may refuse the write. Regression for
    the 1.2.68 -> 1.2.69 auto-update deadlock (WF_DONE became inescapable
    because the state file was never created)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        config.get_project_root = lambda: self.tmp.name
        os.makedirs(os.path.join(self.tmp.name, ".serena", "swe-state"),
                    exist_ok=True)
        self._own = config._own_plugin_version
        self._stale = config._is_stale_daemon

    def tearDown(self):
        config._own_plugin_version = self._own
        config._is_stale_daemon = self._stale
        self.tmp.cleanup()
        reset_caches()

    def _seed(self, sid, owner):
        p = config.get_state_file_path(sid)
        with open(p, "w") as f:
            json.dump({"current_state": "WF_DONE", "writer_version": owner}, f)

    def test_current_daemon_writes_and_stamps_version(self):
        config._own_plugin_version = lambda: "1.2.69"
        config._is_stale_daemon = lambda: False
        self.assertTrue(config.write_state_file("s1", "WF_EXECUTE"))
        st = config.read_state_file("s1")
        self.assertEqual(st["current_state"], "WF_EXECUTE")
        self.assertEqual(st["writer_version"], "1.2.69")

    def test_stale_daemon_refuses_when_file_owned_by_newer(self):
        # The genuine dual-daemon race: a newer daemon owns the file.
        self._seed("s2", "1.2.69")
        config._own_plugin_version = lambda: "1.2.68"
        config._is_stale_daemon = lambda: True
        self.assertFalse(config.write_state_file("s2", "WF_EXECUTE"))
        st = config.read_state_file("s2")
        self.assertEqual(st["current_state"], "WF_DONE")  # untouched
        self.assertEqual(st["writer_version"], "1.2.69")

    def test_stale_daemon_writes_when_file_unowned(self):
        # Auto-update brick case: no prior owner stamp -> write through.
        config._own_plugin_version = lambda: "1.2.68"
        config._is_stale_daemon = lambda: True
        self.assertTrue(config.write_state_file("s3", "WF_EXECUTE"))
        self.assertEqual(config.read_state_file("s3")["current_state"],
                         "WF_EXECUTE")

    def test_stale_daemon_writes_when_file_self_owned(self):
        self._seed("s4", "1.2.68")
        config._own_plugin_version = lambda: "1.2.68"
        config._is_stale_daemon = lambda: True
        self.assertTrue(config.write_state_file("s4", "WF_EXECUTE"))
        self.assertEqual(config.read_state_file("s4")["current_state"],
                         "WF_EXECUTE")


class TestBypassNotice(unittest.TestCase):
    def test_bypass_notice_mentions_reinstatement_path(self):
        # Module-level constant: assert its load-bearing content.
        self.assertIn("BYPASSED", config.BYPASS_NOTICE)
        self.assertIn(".serena/swe-setup-complete.json", config.BYPASS_NOTICE)
        self.assertIn("bypass", config.BYPASS_NOTICE)

    def test_plugin_install_key_constant(self):
        self.assertEqual(config._PLUGIN_INSTALL_KEY, "swe@EarthmanWeb")


if __name__ == "__main__":
    unittest.main()
