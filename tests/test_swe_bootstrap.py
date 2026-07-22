"""Tests for scripts/swe-bootstrap.py.

The bootstrap script's target functions all accept an explicit `project_root`
argument (no get_project_root() indirection), so tests use tempfile dirs and
pass paths directly — no global monkeypatching required. Only PLUGIN_ROOT-based
functions (copy_template_memories, inject_claude_prefix, get_plugin_version,
migrate_auto_memory, main) are excluded per the task mandate.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import load_script  # noqa: E402

mod = load_script("scripts/swe-bootstrap.py")


class TestModuleConstants(unittest.TestCase):
    """Targeted asserts on module-level constants / maps."""

    def test_ext_to_language_map(self):
        self.assertEqual(mod.EXT_TO_LANGUAGE['.py'], 'python')
        self.assertEqual(mod.EXT_TO_LANGUAGE['.php'], 'php')
        # .js/.jsx/.ts/.tsx all collapse onto 'typescript'
        self.assertEqual(mod.EXT_TO_LANGUAGE['.js'], 'typescript')
        self.assertEqual(mod.EXT_TO_LANGUAGE['.jsx'], 'typescript')
        self.assertEqual(mod.EXT_TO_LANGUAGE['.ts'], 'typescript')
        self.assertEqual(mod.EXT_TO_LANGUAGE['.rs'], 'rust')
        self.assertEqual(mod.EXT_TO_LANGUAGE['.go'], 'go')

    def test_skip_dirs_contains_common_excludes(self):
        for d in ('.git', 'node_modules', 'vendor', '.serena', '__pycache__'):
            self.assertIn(d, mod.SKIP_DIRS)

    def test_always_ignored_dirs(self):
        for d in ('node_modules', 'vendor', 'dist', 'build', '__pycache__', '.venv'):
            self.assertIn(d, mod.ALWAYS_IGNORED_DIRS)

    def test_framework_ignored_keys(self):
        self.assertIn('wordpress', mod.FRAMEWORK_IGNORED)
        self.assertIn('laravel', mod.FRAMEWORK_IGNORED)
        self.assertIn('rails', mod.FRAMEWORK_IGNORED)
        self.assertIn('wp/', mod.FRAMEWORK_IGNORED['wordpress'])

    def test_test_framework_hints(self):
        self.assertEqual(
            mod.TEST_FRAMEWORK_HINTS['package.json']['jest'],
            ('Jest', 'npx jest', 'tests/'),
        )
        self.assertEqual(
            mod.TEST_FRAMEWORK_HINTS['Cargo.toml']['_default'],
            ('cargo test', 'cargo test', 'tests/'),
        )


class TestDetectPrimaryLanguage(unittest.TestCase):
    """Pure function: first non-markdown language, else 'unknown'."""

    def test_first_non_markdown(self):
        self.assertEqual(mod.detect_primary_language(['markdown', 'python']), 'python')

    def test_first_element_when_not_markdown(self):
        self.assertEqual(mod.detect_primary_language(['php', 'markdown']), 'php')

    def test_only_markdown_returns_unknown(self):
        self.assertEqual(mod.detect_primary_language(['markdown']), 'unknown')

    def test_empty_list_returns_unknown(self):
        self.assertEqual(mod.detect_primary_language([]), 'unknown')

    def test_multiple_non_markdown_returns_first(self):
        self.assertEqual(
            mod.detect_primary_language(['typescript', 'python', 'go']),
            'typescript',
        )


class TestRenderTemplate(unittest.TestCase):
    """Pure function: replace {{var}} placeholders; unknowns left as-is."""

    def test_known_placeholder_replaced(self):
        out = mod.render_template('Hello {{name}}!', {'name': 'World'})
        self.assertEqual(out, 'Hello World!')

    def test_unknown_placeholder_left_verbatim(self):
        out = mod.render_template('Value: {{missing}}', {'name': 'x'})
        self.assertEqual(out, 'Value: {{missing}}')

    def test_whitespace_inside_braces_not_matched(self):
        # regex is \{\{(\w+)\}\} — internal spaces mean no match at all,
        # so the placeholder is left verbatim (the .strip() never applies here).
        out = mod.render_template('{{  name  }}', {'name': 'ok'})
        self.assertEqual(out, '{{  name  }}')

    def test_multiple_placeholders(self):
        out = mod.render_template('{{a}}-{{b}}-{{a}}', {'a': '1', 'b': '2'})
        self.assertEqual(out, '1-2-1')

    def test_no_placeholders_returned_unchanged(self):
        self.assertEqual(mod.render_template('plain text', {'x': 'y'}), 'plain text')

    def test_empty_content(self):
        self.assertEqual(mod.render_template('', {'x': 'y'}), '')

    def test_non_word_chars_not_matched(self):
        # regex is \w+ only; '{{a-b}}' won't match, left verbatim
        self.assertEqual(mod.render_template('{{a-b}}', {'a-b': 'z'}), '{{a-b}}')


class TestDetectProjectName(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, obj):
        path = os.path.join(self.root, name)
        with open(path, 'w') as f:
            if isinstance(obj, str):
                f.write(obj)
            else:
                json.dump(obj, f)

    def test_package_json_plain_name(self):
        self._write('package.json', {'name': 'my-app'})
        self.assertEqual(mod.detect_project_name(self.root), 'my-app')

    def test_package_json_scoped_name(self):
        self._write('package.json', {'name': '@scope/thing'})
        self.assertEqual(mod.detect_project_name(self.root), 'thing')

    def test_composer_json_name(self):
        self._write('composer.json', {'name': 'acme/widget'})
        self.assertEqual(mod.detect_project_name(self.root), 'widget')

    def test_cargo_toml_name(self):
        self._write('Cargo.toml', 'name = "rustpkg"\nversion = "0.1.0"\n')
        self.assertEqual(mod.detect_project_name(self.root), 'rustpkg')

    def test_no_manifest_falls_back_to_basename(self):
        self.assertEqual(mod.detect_project_name(self.root), os.path.basename(self.root))

    def test_malformed_package_json_falls_back(self):
        self._write('package.json', 'not json {{{')
        self.assertEqual(mod.detect_project_name(self.root), os.path.basename(self.root))

    def test_package_json_empty_name_falls_through_to_basename(self):
        # empty name -> neither branch returns -> falls to basename
        self._write('package.json', {'name': ''})
        self.assertEqual(mod.detect_project_name(self.root), os.path.basename(self.root))

    def test_package_json_precedence_over_composer(self):
        self._write('package.json', {'name': 'js-name'})
        self._write('composer.json', {'name': 'vendor/php-name'})
        self.assertEqual(mod.detect_project_name(self.root), 'js-name')


class TestDetectTestFramework(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, obj):
        path = os.path.join(self.root, name)
        with open(path, 'w') as f:
            if isinstance(obj, str):
                f.write(obj)
            else:
                json.dump(obj, f)

    def test_default_when_nothing(self):
        self.assertEqual(
            mod.detect_test_framework(self.root),
            ('unknown', '# TODO: Add test commands', 'tests/'),
        )

    def test_package_json_jest_devdep(self):
        self._write('package.json', {'devDependencies': {'jest': '^29'}})
        self.assertEqual(
            mod.detect_test_framework(self.root),
            ('Jest', 'npx jest', 'tests/'),
        )

    def test_package_json_playwright_dep(self):
        self._write('package.json', {'dependencies': {'@playwright/test': '^1'}})
        self.assertEqual(
            mod.detect_test_framework(self.root),
            ('Playwright', 'npx playwright test', 'tests/'),
        )

    def test_composer_phpunit_require_dev(self):
        self._write('composer.json', {'require-dev': {'phpunit/phpunit': '^10'}})
        self.assertEqual(
            mod.detect_test_framework(self.root),
            ('PHPUnit', 'vendor/bin/phpunit', 'tests/'),
        )

    def test_cargo_toml_default(self):
        self._write('Cargo.toml', 'name = "x"\n')
        self.assertEqual(
            mod.detect_test_framework(self.root),
            ('cargo test', 'cargo test', 'tests/'),
        )

    def test_go_mod_default(self):
        self._write('go.mod', 'module example.com/x\n')
        self.assertEqual(
            mod.detect_test_framework(self.root),
            ('go test', 'go test ./...', 'tests/'),
        )

    def test_pytest_marker_in_pyproject(self):
        self._write('pyproject.toml', '[tool.pytest.ini_options]\n')
        self.assertEqual(
            mod.detect_test_framework(self.root),
            ('pytest', 'pytest', 'tests/'),
        )

    def test_pyproject_without_pytest_returns_unknown(self):
        self._write('pyproject.toml', '[tool.black]\nline-length = 88\n')
        self.assertEqual(
            mod.detect_test_framework(self.root),
            ('unknown', '# TODO: Add test commands', 'tests/'),
        )


class TestDetectLanguages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _touch(self, relpath):
        full = os.path.join(self.root, relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w') as f:
            f.write('x')

    def test_markdown_always_included_even_empty(self):
        self.assertEqual(mod.detect_languages(self.root), ['markdown'])

    def test_detects_python_and_markdown_sorted(self):
        self._touch('a.py')
        self.assertEqual(mod.detect_languages(self.root), ['markdown', 'python'])

    def test_js_collapses_to_typescript(self):
        self._touch('a.js')
        self._touch('b.jsx')
        langs = mod.detect_languages(self.root)
        self.assertIn('typescript', langs)
        self.assertNotIn('javascript', langs)

    def test_multiple_languages_deduped_and_sorted(self):
        self._touch('a.py')
        self._touch('b.php')
        self._touch('c.rs')
        self.assertEqual(mod.detect_languages(self.root), ['markdown', 'php', 'python', 'rust'])

    def test_skip_dirs_excluded(self):
        # a python file buried in node_modules must NOT be detected
        self._touch('node_modules/pkg/deep.py')
        self.assertEqual(mod.detect_languages(self.root), ['markdown'])

    def test_unknown_extension_ignored(self):
        self._touch('data.xyz')
        self._touch('notes.txt')
        self.assertEqual(mod.detect_languages(self.root), ['markdown'])


class TestDetectFrameworkType(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _touch(self, relpath, content='x'):
        full = os.path.join(self.root, relpath)
        os.makedirs(os.path.dirname(full) or self.root, exist_ok=True)
        with open(full, 'w') as f:
            f.write(content)

    def test_none_for_clean_project(self):
        self.assertIsNone(mod._detect_framework_type(self.root))

    def test_wordpress_via_wp_config(self):
        self._touch('wp-config.php')
        self.assertEqual(mod._detect_framework_type(self.root), 'wordpress')

    def test_wordpress_via_wp_dir(self):
        os.makedirs(os.path.join(self.root, 'wp'))
        self.assertEqual(mod._detect_framework_type(self.root), 'wordpress')

    def test_wordpress_via_wp_content_themes(self):
        os.makedirs(os.path.join(self.root, 'wp-content', 'themes'))
        self.assertEqual(mod._detect_framework_type(self.root), 'wordpress')

    def test_laravel_via_artisan(self):
        self._touch('artisan')
        self.assertEqual(mod._detect_framework_type(self.root), 'laravel')

    def test_rails_via_routes(self):
        self._touch('config/routes.rb')
        self.assertEqual(mod._detect_framework_type(self.root), 'rails')

    def test_rails_via_gemfile_with_rails(self):
        self._touch('Gemfile', "source 'https://rubygems.org'\ngem 'rails', '~> 7'\n")
        self.assertEqual(mod._detect_framework_type(self.root), 'rails')

    def test_gemfile_without_rails_returns_none(self):
        self._touch('Gemfile', "source 'https://rubygems.org'\ngem 'sinatra'\n")
        self.assertIsNone(mod._detect_framework_type(self.root))


class TestDetectIgnoredPaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _mkdir(self, relpath):
        os.makedirs(os.path.join(self.root, relpath), exist_ok=True)

    def test_empty_project_yields_only_unconditional_globs(self):
        # The **/node_modules/ and **/.pnpm-store/ globs are appended
        # unconditionally (outside the isdir check), so even a clean project
        # returns them. Sorted iteration => .pnpm-store before node_modules.
        self.assertEqual(
            mod.detect_ignored_paths(self.root),
            ['**/.pnpm-store/', '**/node_modules/'],
        )

    def test_node_modules_adds_root_and_glob(self):
        self._mkdir('node_modules')
        result = mod.detect_ignored_paths(self.root)
        self.assertIn('node_modules/', result)
        self.assertIn('**/node_modules/', result)

    def test_vendor_adds_only_root_pattern(self):
        self._mkdir('vendor')
        result = mod.detect_ignored_paths(self.root)
        self.assertIn('vendor/', result)
        self.assertNotIn('**/vendor/', result)

    def test_infra_devcontainer_detected(self):
        self._mkdir('.devcontainer')
        result = mod.detect_ignored_paths(self.root)
        self.assertIn('.devcontainer/', result)

    def test_wordpress_framework_globs_added(self):
        # wp/ dir marks wordpress; wp/ exists so 'wp/' is added,
        # plus glob pattern 'wp-*.php' always added (contains '*')
        self._mkdir('wp')
        result = mod.detect_ignored_paths(self.root)
        self.assertIn('wp/', result)
        self.assertIn('wp-*.php', result)

    def test_result_is_deduplicated(self):
        self._mkdir('node_modules')
        self._mkdir('vendor')
        self._mkdir('dist')
        result = mod.detect_ignored_paths(self.root)
        self.assertEqual(len(result), len(set(result)))


class TestUpdateGitignore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.path = os.path.join(self.root, '.gitignore')

    def tearDown(self):
        self.tmp.cleanup()

    def test_creates_when_absent(self):
        self.assertTrue(mod.update_gitignore(self.root))
        self.assertTrue(os.path.exists(self.path))
        with open(self.path) as f:
            content = f.read()
        self.assertIn('!.serena/memory/', content)
        self.assertIn('.serena/swe-bypass.json', content)

    def test_appends_to_existing(self):
        with open(self.path, 'w') as f:
            f.write('*.log\n')
        self.assertTrue(mod.update_gitignore(self.root))
        with open(self.path) as f:
            content = f.read()
        self.assertIn('*.log', content)
        self.assertIn('# SWE workflow engine', content)

    def test_idempotent_marker_present(self):
        mod.update_gitignore(self.root)
        # second call sees the negation marker, no-ops
        self.assertFalse(mod.update_gitignore(self.root))
        with open(self.path) as f:
            content = f.read()
        # marker appears exactly once
        self.assertEqual(content.count('!.serena/memory/\n'), 1)


class TestEnsureSerenaGitignore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, '.serena'))
        self.path = os.path.join(self.root, '.serena', '.gitignore')

    def tearDown(self):
        self.tmp.cleanup()

    def test_creates_when_absent(self):
        self.assertTrue(mod.ensure_serena_gitignore(self.root))
        with open(self.path) as f:
            content = f.read()
        self.assertIn('/cache', content)
        self.assertIn('/swe-setup-complete.json', content)

    def test_tops_up_missing_entries(self):
        with open(self.path, 'w') as f:
            f.write('/cache\n')
        self.assertTrue(mod.ensure_serena_gitignore(self.root))
        with open(self.path) as f:
            content = f.read()
        self.assertIn('/streams', content)
        self.assertIn('/memories', content)
        # existing /cache preserved, not duplicated
        self.assertEqual(content.count('/cache\n'), 1)

    def test_idempotent_when_all_present(self):
        mod.ensure_serena_gitignore(self.root)
        self.assertFalse(mod.ensure_serena_gitignore(self.root))
        with open(self.path) as f:
            content = f.read()
        self.assertEqual(content.count('/streams\n'), 1)


class TestEnsureMemoryPathsConf(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, '.serena'))
        self.path = os.path.join(self.root, '.serena', 'memory-paths.conf')

    def tearDown(self):
        self.tmp.cleanup()

    def test_creates_when_absent(self):
        self.assertTrue(mod.ensure_memory_paths_conf(self.root))
        with open(self.path) as f:
            content = f.read()
        self.assertIn('./.serena/memory', content)
        self.assertIn('# Serena memory paths configuration', content)

    def test_noop_when_required_present(self):
        mod.ensure_memory_paths_conf(self.root)
        self.assertFalse(mod.ensure_memory_paths_conf(self.root))

    def test_extra_paths_appended(self):
        self.assertTrue(mod.ensure_memory_paths_conf(self.root, extra_paths=['./docs:ro']))
        with open(self.path) as f:
            content = f.read()
        self.assertIn('./docs:ro', content)

    def test_adds_missing_required_to_existing_file(self):
        # file exists with only a user path, missing the required one
        with open(self.path, 'w') as f:
            f.write('# header\n./custom\n')
        self.assertTrue(mod.ensure_memory_paths_conf(self.root))
        with open(self.path) as f:
            lines = [ln for ln in f.read().splitlines() if ln and not ln.startswith('#')]
        # required path inserted before existing user path
        self.assertEqual(lines[0], './.serena/memory')
        self.assertIn('./custom', lines)

    def test_no_duplication_on_double_call(self):
        mod.ensure_memory_paths_conf(self.root)
        mod.ensure_memory_paths_conf(self.root)
        with open(self.path) as f:
            content = f.read()
        self.assertEqual(content.count('./.serena/memory'), 1)


class TestCreateProjectYml(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, '.serena'))
        self.path = os.path.join(self.root, '.serena', 'project.yml')

    def tearDown(self):
        self.tmp.cleanup()

    def test_creates_with_languages(self):
        self.assertTrue(mod.create_project_yml(self.root, ['python', 'markdown']))
        with open(self.path) as f:
            content = f.read()
        self.assertIn('- python', content)
        self.assertIn('- markdown', content)
        self.assertIn('ignored_memory_patterns: ["WM_.*"]', content)

    def test_clean_project_still_lists_unconditional_globs(self):
        # detect_ignored_paths always returns the **/node_modules/ and
        # **/.pnpm-store/ globs, so the populated (non-empty) ignored_paths
        # section is emitted even for an otherwise clean project.
        self.assertTrue(mod.create_project_yml(self.root, ['python']))
        with open(self.path) as f:
            content = f.read()
        self.assertIn('ignored_paths:', content)
        self.assertIn('**/node_modules/', content)
        self.assertNotIn('ignored_paths: []', content)

    def test_ignored_paths_populated_when_deps_exist(self):
        os.makedirs(os.path.join(self.root, 'node_modules'))
        self.assertTrue(mod.create_project_yml(self.root, ['typescript']))
        with open(self.path) as f:
            content = f.read()
        self.assertIn('ignored_paths:', content)
        self.assertIn('node_modules/', content)

    def test_skip_if_exists(self):
        with open(self.path, 'w') as f:
            f.write('preexisting: true\n')
        self.assertFalse(mod.create_project_yml(self.root, ['python']))
        with open(self.path) as f:
            content = f.read()
        # original content untouched
        self.assertEqual(content, 'preexisting: true\n')


class TestMergeMemoryMd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.source = os.path.join(self.root, 'src_MEMORY.md')
        self.target = os.path.join(self.root, 'tgt_MEMORY.md')

    def tearDown(self):
        self.tmp.cleanup()

    def test_entries_merged_with_rewritten_paths(self):
        with open(self.source, 'w') as f:
            f.write(
                "# My Memory\n"
                "## Rules\n"
                "- [Test note](feedback_test.md) — a rule\n"
                "- [User role](user_role.md) — role info\n"
            )
        with open(self.target, 'w') as f:
            f.write("# Existing\n")
        mod._merge_memory_md(self.source, self.target, self.root)
        with open(self.target) as f:
            content = f.read()
        # prefixed link paths rewritten to typed subdirs, uppercased
        self.assertIn('feedback/FEEDBACK_TEST.md', content)
        self.assertIn('user/USER_ROLE.md', content)
        self.assertIn('## Migrated from Auto-Memory', content)
        # heading/comment lines from source not carried over
        self.assertNotIn('## Rules', content)

    def test_spec_links_get_spec_prefix(self):
        with open(self.source, 'w') as f:
            f.write("- [Spec foo](SPEC_Foo.md) — a spec\n")
        with open(self.target, 'w') as f:
            f.write("# Existing\n")
        mod._merge_memory_md(self.source, self.target, self.root)
        with open(self.target) as f:
            content = f.read()
        self.assertIn('spec/SPEC_Foo.md', content)

    def test_duplicate_entry_not_appended(self):
        # target already references the rewritten link target
        with open(self.source, 'w') as f:
            f.write("- [Test](feedback_test.md) — desc\n")
        with open(self.target, 'w') as f:
            f.write("Already has feedback/FEEDBACK_TEST.md here\n")
        mod._merge_memory_md(self.source, self.target, self.root)
        with open(self.target) as f:
            content = f.read()
        # no migration section added because the only entry was a dupe
        self.assertNotIn('## Migrated from Auto-Memory', content)

    def test_no_new_entries_leaves_target_unchanged(self):
        # source has only headings/blank lines -> nothing to merge
        with open(self.source, 'w') as f:
            f.write("# Heading only\n\n## Section\n")
        with open(self.target, 'w') as f:
            f.write("# Target\n")
        mod._merge_memory_md(self.source, self.target, self.root)
        with open(self.target) as f:
            content = f.read()
        self.assertEqual(content, "# Target\n")

    def test_target_created_appends_when_absent(self):
        # target path does not exist yet; entries with links still appended
        with open(self.source, 'w') as f:
            f.write("- [Ref api](reference_api.md) — api ref\n")
        mod._merge_memory_md(self.source, self.target, self.root)
        with open(self.target) as f:
            content = f.read()
        self.assertIn('ref/REF_API.md', content)
        self.assertIn('## Migrated from Auto-Memory', content)

    def test_line_without_link_not_appended(self):
        # non-comment line lacking a markdown link is skipped (link_match None)
        with open(self.source, 'w') as f:
            f.write("- plain bullet with no link\n")
        with open(self.target, 'w') as f:
            f.write("# T\n")
        mod._merge_memory_md(self.source, self.target, self.root)
        with open(self.target) as f:
            content = f.read()
        self.assertEqual(content, "# T\n")


if __name__ == "__main__":
    unittest.main()
