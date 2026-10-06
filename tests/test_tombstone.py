import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TREE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TREE / "hooks"))
import tombstone_cleanup as tc  # noqa: E402


def mk(base: Path, mp: str, plugin: str, ver: str) -> Path:
    d = base / "plugins" / "cache" / mp / plugin / ver
    d.mkdir(parents=True)
    (d / "f.txt").write_text("x")
    return d


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.base = Path(self._td.name)


class TestRefusal(Base):
    def test_wrong_parent_name(self) -> None:
        self.assertFalse(tc.is_own_cache_root(mk(self.base, "mp", "other", "1.0.0")))

    def test_non_semver_leaf(self) -> None:
        self.assertFalse(tc.is_own_cache_root(mk(self.base, "mp", "swe", "latest")))

    def test_missing_plugins_cache(self) -> None:
        d = self.base / "x" / "mp" / "swe" / "1.0.0"
        d.mkdir(parents=True)
        self.assertFalse(tc.is_own_cache_root(d))

    def test_accepts_valid(self) -> None:
        self.assertTrue(tc.is_own_cache_root(mk(self.base, "mp", "swe", "99.0.0")))


class TestCleanup(Base):
    def test_deletes_only_sibling_versions(self) -> None:
        root = mk(self.base, "mp", "swe", "99.0.0")
        old1 = mk(self.base, "mp", "swe", "1.0.0")
        old2 = mk(self.base, "mp", "swe", "1.3.5")
        other_plugin = mk(self.base, "mp", "keepme", "1.0.0")
        other_mp = mk(self.base, "mp2", "swe", "1.0.0")
        removed = tc.cleanup(root)
        self.assertEqual({p.name for p in removed}, {"1.0.0", "1.3.5"})
        self.assertFalse(old1.exists())
        self.assertFalse(old2.exists())
        self.assertTrue(root.exists())
        self.assertTrue(other_plugin.exists())
        self.assertTrue(other_mp.exists())

    def test_symlinked_sibling(self) -> None:
        root = mk(self.base, "mp", "swe", "99.0.0")
        target = self.base / "target"
        target.mkdir()
        (target / "keep.txt").write_text("k")
        link = root.parent / "1.0.0"
        link.symlink_to(target, target_is_directory=True)
        tc.cleanup(root)
        self.assertFalse(link.is_symlink())
        self.assertTrue((target / "keep.txt").exists())


class TestMainIdempotence(Base):
    def run_main(self, root: Path) -> str:
        buf = io.StringIO()
        old = os.environ.get("CLAUDE_PLUGIN_ROOT")
        os.environ["CLAUDE_PLUGIN_ROOT"] = str(root)
        try:
            with contextlib.redirect_stdout(buf):
                self.assertEqual(tc.main(), 0)
        finally:
            if old is None:
                os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
            else:
                os.environ["CLAUDE_PLUGIN_ROOT"] = old
        return buf.getvalue()

    def test_marker_idempotence(self) -> None:
        root = mk(self.base, "mp", "swe", "99.0.0")
        mk(self.base, "mp", "swe", "1.0.0")
        out = self.run_main(root)
        self.assertIn("systemMessage", json.loads(out))
        self.assertTrue((root / tc.MARKER).exists())
        mk(self.base, "mp", "swe", "1.0.1")
        self.assertEqual(self.run_main(root), "")
        self.assertTrue((root.parent / "1.0.1").exists())

    def test_notice_once_without_siblings(self) -> None:
        root = mk(self.base, "mp", "swe", "99.0.0")
        out = self.run_main(root)
        self.assertEqual(json.loads(out)["systemMessage"], tc.NOTICE)
        self.assertTrue((root / tc.NOTIFIED).exists())
        self.assertEqual(self.run_main(root), "")

    def test_refusal_silent(self) -> None:
        self.assertEqual(self.run_main(self.base), "")


def git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return r.stdout.strip()


def commit_all(repo: Path, msg: str) -> None:
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", msg)


def write_manifest(repo: Path, version: str, name: str = "swe") -> None:
    d = repo / ".claude-plugin"
    d.mkdir(exist_ok=True)
    (d / "plugin.json").write_text(json.dumps({"name": name, "version": version}))


class MarketplaceBase(Base):
    """Old history pushed to a bare remote, CLI-style shallow clone, then an
    orphan tombstone force-pushed and pulled with fetch + reset --hard."""

    def setUp(self) -> None:
        super().setUp()
        b = self.base
        self.src = b / "src"
        self.src.mkdir()
        git(self.src, "init", "-q", "-b", "main")
        for i in range(6):
            write_manifest(self.src, f"1.0.{i}")
            (self.src / f"secret{i}.txt").write_text(f"secret {i}")
            commit_all(self.src, f"hist {i}")
        self.old_tip = git(self.src, "rev-parse", "HEAD")
        self.remote = b / "remote.git"
        git(b, "clone", "-q", "--bare", str(self.src), str(self.remote))
        self.plugins = b / "plugins"
        self.clone = self.plugins / "marketplaces" / "mp"
        self.clone.parent.mkdir(parents=True)
        git(b, "clone", "-q", "--depth", "3", "--single-branch", "--branch", "main",
            "file://" + str(self.remote), str(self.clone))
        self.root = self.plugins / "cache" / "mp" / "swe" / "99.0.0"
        self.root.mkdir(parents=True)

    def push_tombstone(self, version: str = "99.0.0", name: str = "swe") -> None:
        git(self.src, "checkout", "-q", "--orphan", "tomb")
        git(self.src, "rm", "-rqf", ".")
        write_manifest(self.src, version, name)
        commit_all(self.src, "tombstone")
        git(self.src, "push", "-qf", str(self.remote), "tomb:main")

    def cli_update(self) -> None:
        git(self.clone, "fetch", "-q", "origin")
        git(self.clone, "reset", "-q", "--hard", "origin/main")

    def has_object(self, sha: str) -> bool:
        r = subprocess.run(["git", "cat-file", "-e", sha], cwd=self.clone, capture_output=True)
        return r.returncode == 0

    def object_count(self) -> int:
        out = git(self.clone, "cat-file", "--batch-all-objects", "--batch-check")
        return len(out.splitlines())


class TestMarketplacePurge(MarketplaceBase):
    def test_purges_all_pre_tombstone_objects(self) -> None:
        self.push_tombstone()
        self.cli_update()
        self.assertTrue(self.has_object(self.old_tip))
        self.assertTrue(tc.purge_marketplace_history(self.root))
        self.assertFalse(self.has_object(self.old_tip))
        reachable = git(self.clone, "rev-list", "--objects", "--all").splitlines()
        self.assertEqual(self.object_count(), len(reachable))
        self.assertEqual(git(self.clone, "rev-list", "--all", "--count"), "1")
        self.assertEqual(git(self.clone, "fsck", "--no-progress"), "")
        self.assertFalse((self.clone / ".git" / "ORIG_HEAD").exists())
        self.assertFalse((self.clone / ".git" / "logs").exists())
        self.assertTrue((self.clone / ".git" / tc.PURGED).exists())

    def test_next_cli_update_still_works(self) -> None:
        self.push_tombstone()
        self.cli_update()
        tc.purge_marketplace_history(self.root)
        (self.src / "README.md").write_text("v2")
        commit_all(self.src, "tombstone 2")
        git(self.src, "push", "-qf", str(self.remote), "tomb:main")
        self.cli_update()
        self.assertEqual(git(self.clone, "log", "-1", "--format=%s"), "tombstone 2")

    def test_skips_until_cli_has_landed_tombstone(self) -> None:
        self.assertFalse(tc.purge_marketplace_history(self.root))
        self.assertTrue(self.has_object(self.old_tip))
        self.assertFalse((self.clone / ".git" / tc.PURGED).exists())

    def test_refuses_non_tombstone_head(self) -> None:
        self.push_tombstone(version="2.0.0")
        self.cli_update()
        self.assertFalse(tc.purge_marketplace_history(self.root))
        self.assertTrue(self.has_object(self.old_tip))

    def test_refuses_other_plugin_name(self) -> None:
        self.push_tombstone(name="cwe")
        self.cli_update()
        self.assertFalse(tc.purge_marketplace_history(self.root))
        self.assertTrue(self.has_object(self.old_tip))

    def test_refuses_head_with_parents(self) -> None:
        write_manifest(self.src, "99.0.0")
        commit_all(self.src, "tombstone on top of history")
        git(self.src, "push", "-qf", str(self.remote), "main:main")
        self.cli_update()
        self.assertFalse(tc.purge_marketplace_history(self.root))
        self.assertTrue(self.has_object(self.old_tip))

    def test_registry_install_location_wins(self) -> None:
        moved = self.base / "elsewhere"
        self.clone.rename(moved)
        self.clone = moved
        (self.plugins / "known_marketplaces.json").write_text(
            json.dumps({"mp": {"installLocation": str(moved)}}))
        self.push_tombstone()
        self.cli_update()
        self.assertTrue(tc.purge_marketplace_history(self.root))
        self.assertFalse(self.has_object(self.old_tip))

    def test_purge_marketplace_history_idempotence(self) -> None:
        self.push_tombstone()
        self.cli_update()
        self.assertTrue(tc.purge_marketplace_history(self.root))
        count_after_first = self.object_count()
        self.assertFalse(tc.purge_marketplace_history(self.root))
        self.assertEqual(self.object_count(), count_after_first)

    def test_main_purges_and_is_silent_after(self) -> None:
        self.push_tombstone()
        self.cli_update()
        os.environ["CLAUDE_PLUGIN_ROOT"] = str(self.root)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(tc.main(), 0)
                self.assertEqual(tc.main(), 0)
        finally:
            os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
        self.assertFalse(self.has_object(self.old_tip))


class TestManifests(unittest.TestCase):
    def test_hooks_only_session_start(self) -> None:
        data = json.loads((TREE / "hooks" / "hooks.json").read_text())
        self.assertEqual(list(data["hooks"].keys()), ["SessionStart"])

    def test_manifests(self) -> None:
        plugin = json.loads((TREE / ".claude-plugin" / "plugin.json").read_text())
        mkt = json.loads((TREE / ".claude-plugin" / "marketplace.json").read_text())
        self.assertEqual(plugin["version"], "99.0.0")
        self.assertEqual(mkt["version"], "99.0.0")
        self.assertEqual(mkt["plugins"][0]["version"], "99.0.0")
        for obj in (plugin, mkt, mkt["plugins"][0]):
            self.assertNotIn("homepage", obj)
            self.assertNotIn("repository", obj)

    def test_no_forbidden_strings(self) -> None:
        bad = [
            "em-" + "serena",
            "EM_CWE_" + "TOK" + "EN",
            "EM_SWE_" + "TOK" + "EN",
        ]
        for f in TREE.rglob("*"):
            rel = f.relative_to(TREE).parts
            if not f.is_file() or ".git" in rel or "__pycache__" in rel:
                continue
            text = f.read_text(errors="ignore")
            for b in bad:
                self.assertNotIn(b, text, f"{b} in {f}")


class TestManifestHygiene(unittest.TestCase):
    def test_emails_and_version(self) -> None:
        for name in ("plugin.json", "marketplace.json"):
            text = (TREE / ".claude-plugin" / name).read_text()
            for m in re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", text):
                self.assertEqual(m, "noreply@example.com")
            ver = json.loads(text)["version"]
            self.assertGreater(tuple(map(int, ver.split("."))), (1, 3, 328))

    def test_notice_in_readme(self) -> None:
        self.assertIn(tc.NOTICE, (TREE / "README.md").read_text())


class TestMcpServers(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads((TREE / ".claude-plugin" / "plugin.json").read_text())

    def test_only_serena_server(self) -> None:
        servers = self.manifest["mcpServers"]
        self.assertEqual(set(servers), {"serena"})
        self.assertNotIn("swe-wm", servers)

    def test_serena_command_and_args(self) -> None:
        s = self.manifest["mcpServers"]["serena"]
        self.assertEqual(s["command"], "uvx")
        self.assertEqual(
            s["args"],
            ["--from", "git+https://github.com/EarthmanWeb/serena@swe", "serena", "start-mcp-server"],
        )

    def test_no_memories_dir(self) -> None:
        self.assertFalse((TREE / "memories").exists())


if __name__ == "__main__":
    unittest.main()
