#!/usr/bin/env python3
"""SWE Bootstrap - Self-contained bootstrap for new projects.

Resolves plugin root from __file__. Operates on os.getcwd().
Creates minimal directory structure and config files needed
before /swe-init or /swe-scaffold-project can run.

Guards:
- Exit if .serena/swe-bypass.json exists (SWE bypassed)
- Exit if .serena/swe-setup-complete.json has complete: true (already initialized)
- Exit if .serena/swe-setup-complete.json has bootstrapped: true (already bootstrapped)
"""

import os
import sys
import json
import re
from datetime import datetime
from collections import Counter

# Resolve plugin root from this script's location
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Directories to skip when scanning for languages
SKIP_DIRS = {'.git', 'node_modules', 'vendor', '.serena', '.claude', '__pycache__',
             '.vscode', '.idea', 'dist', 'build', '.cache'}

# Directories that should NEVER be indexed by Serena (always excluded).
# These contain third-party code, build artifacts, or infrastructure files
# that pollute symbol resolution and bloat caches.
ALWAYS_IGNORED_DIRS = {
    'node_modules',   # npm/pnpm/yarn dependencies
    '.pnpm-store',    # pnpm global store
    'vendor',         # Composer/Go/Ruby dependencies
    'dist',           # Build output
    'build',          # Build output
    '.cache',         # Various caches
    '__pycache__',    # Python bytecode
    '.venv',          # Python virtualenv
    'venv',           # Python virtualenv
    '.tox',           # Python tox
    '.mypy_cache',    # mypy cache
    '.pytest_cache',  # pytest cache
    'target',         # Rust/Java build output
    '.gradle',        # Gradle cache
    '.next',          # Next.js build
    '.nuxt',          # Nuxt.js build
    '.output',        # Nitro/Nuxt output
    'coverage',       # Test coverage reports
    '.nyc_output',    # NYC coverage
}

# Framework-specific directories to ignore (detected by project markers)
FRAMEWORK_IGNORED = {
    'wordpress': [
        'wp/',             # WordPress core
        'uploads/',        # Media uploads
        'index.php',       # WP entry point
        'wp-*.php',        # WP root scripts
    ],
    'laravel': [
        'storage/',        # Laravel storage
        'bootstrap/cache/', # Laravel bootstrap cache
    ],
    'rails': [
        'tmp/',            # Rails temp
        'log/',            # Rails logs
    ],
}

# Extension to Serena language name mapping
EXT_TO_LANGUAGE = {
    '.php': 'php',
    '.ts': 'typescript',
    '.tsx': 'typescript',
    '.js': 'typescript',
    '.jsx': 'typescript',
    '.py': 'python',
    '.rb': 'ruby',
    '.rs': 'rust',
    '.go': 'go',
    '.java': 'java',
    '.cs': 'csharp',
    '.cpp': 'cpp',
    '.c': 'c',
    '.swift': 'swift',
    '.kt': 'kotlin',
}


# Test framework detection: manifest key -> (framework name, test commands, test root)
TEST_FRAMEWORK_HINTS = {
    'package.json': {
        '@playwright/test': ('Playwright', 'npx playwright test', 'tests/'),
        'jest': ('Jest', 'npx jest', 'tests/'),
        'vitest': ('Vitest', 'npx vitest', 'tests/'),
        'mocha': ('Mocha', 'npx mocha', 'test/'),
    },
    'composer.json': {
        'phpunit/phpunit': ('PHPUnit', 'vendor/bin/phpunit', 'tests/'),
        'pestphp/pest': ('Pest', 'vendor/bin/pest', 'tests/'),
    },
    'Cargo.toml': {
        '_default': ('cargo test', 'cargo test', 'tests/'),
    },
    'go.mod': {
        '_default': ('go test', 'go test ./...', 'tests/'),
    },
}


def detect_project_name(project_root):
    """Detect project name from manifests or directory name."""
    # Try package.json
    pkg = os.path.join(project_root, 'package.json')
    if os.path.exists(pkg):
        try:
            with open(pkg) as f:
                data = json.load(f)
            name = data.get('name', '')
            if name and not name.startswith('@'):
                return name
            if name:
                # @scope/name -> name
                return name.split('/')[-1]
        except (IOError, json.JSONDecodeError):
            pass

    # Try composer.json
    composer = os.path.join(project_root, 'composer.json')
    if os.path.exists(composer):
        try:
            with open(composer) as f:
                data = json.load(f)
            name = data.get('name', '')
            if name:
                return name.split('/')[-1]
        except (IOError, json.JSONDecodeError):
            pass

    # Try Cargo.toml (simple parse)
    cargo = os.path.join(project_root, 'Cargo.toml')
    if os.path.exists(cargo):
        try:
            with open(cargo) as f:
                for line in f:
                    m = re.match(r'^name\s*=\s*"([^"]+)"', line)
                    if m:
                        return m.group(1)
        except IOError:
            pass

    # Fall back to directory name
    return os.path.basename(project_root)


def detect_test_framework(project_root):
    """Detect test framework from project manifests.

    Returns (framework_name, test_commands, test_root) or defaults.
    """
    # Check package.json devDependencies / dependencies
    pkg = os.path.join(project_root, 'package.json')
    if os.path.exists(pkg):
        try:
            with open(pkg) as f:
                data = json.load(f)
            all_deps = {}
            all_deps.update(data.get('dependencies', {}))
            all_deps.update(data.get('devDependencies', {}))
            for dep, info in TEST_FRAMEWORK_HINTS.get('package.json', {}).items():
                if dep in all_deps:
                    return info
        except (IOError, json.JSONDecodeError):
            pass

    # Check composer.json require-dev
    composer = os.path.join(project_root, 'composer.json')
    if os.path.exists(composer):
        try:
            with open(composer) as f:
                data = json.load(f)
            all_deps = {}
            all_deps.update(data.get('require', {}))
            all_deps.update(data.get('require-dev', {}))
            for dep, info in TEST_FRAMEWORK_HINTS.get('composer.json', {}).items():
                if dep in all_deps:
                    return info
        except (IOError, json.JSONDecodeError):
            pass

    # Check Cargo.toml
    if os.path.exists(os.path.join(project_root, 'Cargo.toml')):
        return TEST_FRAMEWORK_HINTS['Cargo.toml']['_default']

    # Check go.mod
    if os.path.exists(os.path.join(project_root, 'go.mod')):
        return TEST_FRAMEWORK_HINTS['go.mod']['_default']

    # Check for pytest
    for marker in ('pytest.ini', 'pyproject.toml', 'setup.cfg'):
        marker_path = os.path.join(project_root, marker)
        if os.path.exists(marker_path):
            try:
                with open(marker_path) as f:
                    content = f.read()
                if 'pytest' in content or '[tool.pytest' in content:
                    return ('pytest', 'pytest', 'tests/')
            except IOError:
                pass

    return ('unknown', '# TODO: Add test commands', 'tests/')


def detect_primary_language(languages):
    """Pick the primary language from detected list (exclude markdown)."""
    for lang in languages:
        if lang != 'markdown':
            return lang
    return 'unknown'


def build_template_variables(project_root, languages):
    """Build a dict of template variables from project detection."""
    primary = detect_primary_language(languages)
    project_name = detect_project_name(project_root)
    test_framework, test_commands, test_root = detect_test_framework(project_root)

    return {
        'project_name': project_name,
        'primary_language': primary,
        'primary_language_upper': primary.upper(),
        'languages': ', '.join(languages),
        'test_framework': test_framework,
        'test_commands': test_commands,
        'test_root': test_root,
        'year': str(datetime.now().year),
    }


def render_template(content, variables):
    """Replace {{variable}} placeholders in template content.

    Unknown placeholders are left as-is so they serve as visible TODOs.
    """
    def replacer(match):
        key = match.group(1).strip()
        return variables.get(key, match.group(0))

    return re.sub(r'\{\{(\w+)\}\}', replacer, content)


def get_plugin_version():
    """Read version from plugin.json."""
    plugin_json = os.path.join(PLUGIN_ROOT, '.claude-plugin', 'plugin.json')
    try:
        with open(plugin_json) as f:
            data = json.load(f)
        return data.get('version', 'unknown')
    except (IOError, json.JSONDecodeError):
        return 'unknown'


def detect_languages(project_root):
    """Walk project tree and detect languages from file extensions."""
    ext_counts = Counter()
    for dirpath, dirnames, filenames in os.walk(project_root):
        # Skip ignored directories (modifies in-place for os.walk)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in filenames:
            _, ext = os.path.splitext(filename)
            if ext in EXT_TO_LANGUAGE:
                ext_counts[ext] += 1

    languages = set()
    for ext, _count in ext_counts.items():
        languages.add(EXT_TO_LANGUAGE[ext])

    # Always include markdown
    languages.add('markdown')
    return sorted(languages)


def detect_ignored_paths(project_root):
    """Scan the project and determine which paths Serena should ignore.

    Returns a list of gitignore-style patterns for directories that exist
    in the project but should not be indexed (dependencies, build output,
    framework infrastructure, etc.).
    """
    ignored = []

    # Check for always-ignored directories that actually exist
    for dirname in sorted(ALWAYS_IGNORED_DIRS):
        # Check at project root
        if os.path.isdir(os.path.join(project_root, dirname)):
            ignored.append(f'{dirname}/')
        # Also add glob pattern for nested occurrences of common deps
        if dirname in ('node_modules', '.pnpm-store'):
            ignored.append(f'**/{dirname}/')

    # Detect framework and add framework-specific ignores
    framework = _detect_framework_type(project_root)
    if framework and framework in FRAMEWORK_IGNORED:
        for pattern in FRAMEWORK_IGNORED[framework]:
            # Only add if the path actually exists (or is a glob)
            if '*' in pattern:
                ignored.append(pattern)
            elif os.path.exists(os.path.join(project_root, pattern.rstrip('/'))):
                ignored.append(pattern)

    # Detect other common infrastructure dirs that exist
    infra_dirs = {
        '.devcontainer': '.devcontainer/',
        '.pantheon': '.pantheon/',
        '.platform': '.platform/',
        '.docker': '.docker/',
        'docker': 'docker/',
    }
    for dirname, pattern in infra_dirs.items():
        if os.path.isdir(os.path.join(project_root, dirname)):
            ignored.append(pattern)

    # Deduplicate (nested glob patterns may overlap with root patterns)
    seen = set()
    deduped = []
    for p in ignored:
        if p not in seen:
            seen.add(p)
            deduped.append(p)

    return deduped


def _detect_framework_type(project_root):
    """Detect the project framework type from file markers."""
    # WordPress: wp-config.php, wp/ directory, or style.css with Theme Name
    wp_markers = ['wp-config.php', 'wp-config-pantheon.php']
    if any(os.path.exists(os.path.join(project_root, m)) for m in wp_markers):
        return 'wordpress'
    if os.path.isdir(os.path.join(project_root, 'wp')):
        return 'wordpress'
    style_css = os.path.join(project_root, 'wp-content', 'themes')
    if os.path.isdir(style_css):
        return 'wordpress'

    # Laravel: artisan file
    if os.path.exists(os.path.join(project_root, 'artisan')):
        return 'laravel'

    # Rails: Gemfile with rails, or config/routes.rb
    if os.path.exists(os.path.join(project_root, 'config', 'routes.rb')):
        return 'rails'
    gemfile = os.path.join(project_root, 'Gemfile')
    if os.path.exists(gemfile):
        try:
            with open(gemfile) as f:
                if 'rails' in f.read().lower():
                    return 'rails'
        except IOError:
            pass

    return None


def create_project_yml(project_root, languages):
    """Create .serena/project.yml with detected languages and ignored paths.

    Scans the project to detect directories that should not be indexed
    (dependencies, build output, framework infrastructure) and includes
    them as ignored_paths. This prevents Serena from wasting time indexing
    irrelevant code, which bloats caches and degrades symbol resolution.

    Skip if project.yml already exists.
    """
    yml_path = os.path.join(project_root, '.serena', 'project.yml')
    if os.path.exists(yml_path):
        return False

    lang_lines = '\n'.join(f'  - {lang}' for lang in languages)
    ignored = detect_ignored_paths(project_root)

    if ignored:
        ignored_lines = '\n'.join(f'  - "{p}"' for p in ignored)
        ignored_section = f"""
# Paths excluded from Serena indexing.
# Auto-detected: dependencies, build output, framework infrastructure.
# These directories contain third-party or generated code that pollutes
# symbol resolution and bloats language server caches.
ignored_paths:
{ignored_lines}
"""
    else:
        ignored_section = """
# No directories detected for exclusion.
# Add paths here if Serena indexes unwanted code (e.g. vendor/, node_modules/).
ignored_paths: []
"""

    content = f"""# Auto-generated by SWE bootstrap
# Detected languages from project file extensions
languages:
{lang_lines}
{ignored_section}
# Exclude session Working Memory files from list_memories output.
# WM files are accessed via the swe-wm MCP server, not Serena's memory API.
ignored_memory_patterns: ["WM_.*"]
"""
    with open(yml_path, 'w') as f:
        f.write(content)
    return True


def ensure_memory_paths_conf(project_root, extra_paths=None):
    """Create or update .serena/memory-paths.conf with SWE memory paths.

    SWE required paths are always placed at the top of the file (after the
    header comments), before any user-defined paths.

    Args:
        project_root: Project root directory
        extra_paths: Optional list of additional paths (e.g. ['./docs:ro'])
    """
    conf_path = os.path.join(project_root, '.serena', 'memory-paths.conf')
    required_lines = ['./.serena/memory', './.serena/memories']

    if os.path.exists(conf_path):
        with open(conf_path) as f:
            lines = f.read().splitlines()

        # Separate comment lines from path lines
        comment_lines = []
        path_lines = []
        for line in lines:
            if line.startswith('#') or line.strip() == '':
                comment_lines.append(line)
            else:
                path_lines.append(line)

        missing = [p for p in required_lines if p not in path_lines]
        if extra_paths:
            missing.extend(p for p in extra_paths if p not in path_lines)
        if not missing:
            return False  # All paths already present

        # Insert missing required paths at top, extra paths at bottom
        missing_required = [p for p in missing if p in required_lines]
        missing_extra = [p for p in missing if p not in required_lines]
        new_path_lines = missing_required + path_lines + missing_extra

        with open(conf_path, 'w') as f:
            for line in comment_lines:
                f.write(f'{line}\n')
            for line in new_path_lines:
                f.write(f'{line}\n')
        return True

    all_lines = required_lines + (extra_paths or [])
    content = "# Serena memory paths configuration\n"
    content += "# Each line is a path (relative to project root) containing memory files\n"
    for line in all_lines:
        content += f"{line}\n"
    with open(conf_path, 'w') as f:
        f.write(content)
    return True


def copy_template_memories(project_root, template_variables=None):
    """Copy template memories from plugin to project .serena/memory/.

    Supports subdirectories: templates in ref/, feedback/, etc. are copied
    to the matching subdirectory under .serena/memory/.
    Template variables ({{key}}) are rendered if template_variables is provided.
    """
    templates_dir = os.path.join(PLUGIN_ROOT, 'memories', 'templates')
    target_dir = os.path.join(project_root, '.serena', 'memory')
    copied = []

    if not os.path.isdir(templates_dir):
        return copied

    for dirpath, _dirnames, filenames in os.walk(templates_dir):
        for filename in filenames:
            if not filename.endswith('.md'):
                continue

            source = os.path.join(dirpath, filename)
            # Compute relative subdirectory from templates root
            rel_subdir = os.path.relpath(dirpath, templates_dir)
            if rel_subdir == '.':
                target_subdir = target_dir
            else:
                target_subdir = os.path.join(target_dir, rel_subdir)
                os.makedirs(target_subdir, exist_ok=True)

            target = os.path.join(target_subdir, filename)
            if os.path.exists(target):
                continue  # Don't overwrite existing
            with open(source) as f:
                content = f.read()

            # Render template variables
            if template_variables:
                for key, value in template_variables.items():
                    content = content.replace('{{' + key + '}}', str(value))

            with open(target, 'w') as f:
                f.write(content)

            rel_path = os.path.relpath(target, target_dir)
            copied.append(rel_path)

    return copied


def migrate_auto_memory(project_root):
    """Migrate auto-memory files from ~/.claude/projects/<encoded>/memory/ to .serena/memory/.

    Reorganizes flat files into typed subdirectories with uppercase names:
      feedback_test.md  → feedback/FEEDBACK_TEST.md
      user_role.md      → user/USER_ROLE.md
      project_notes.md  → project/PROJECT_NOTES.md
      reference_api.md  → ref/REF_API.md
      SPEC_Foo.md       → spec/SPEC_Foo.md
      other.md          → OTHER.md (root, uppercased)

    MEMORY.md is merged (unique entries appended with updated paths).

    Returns list of migrated filenames (new paths).
    """
    target_dir = os.path.join(project_root, '.serena', 'memory')

    # Determine auto-memory source path
    encoded_both = project_root.replace('/', '-').replace('_', '-')
    if encoded_both.startswith('-'):
        encoded_both = encoded_both  # keep leading dash
    auto_dir = os.path.join(os.path.expanduser('~'), '.claude', 'projects', encoded_both, 'memory')

    if not os.path.isdir(auto_dir) or os.path.islink(auto_dir):
        # Try underscore-preserving encoding (older Claude Code)
        encoded_slash = project_root.replace('/', '-')
        auto_dir = os.path.join(os.path.expanduser('~'), '.claude', 'projects', encoded_slash, 'memory')
        if not os.path.isdir(auto_dir) or os.path.islink(auto_dir):
            return []

    # Prefix-to-subdirectory mapping
    PREFIX_MAP = {
        'feedback_': ('feedback', 'FEEDBACK_'),
        'user_': ('user', 'USER_'),
        'project_': ('project', 'PROJECT_'),
        'reference_': ('ref', 'REF_'),
    }

    migrated = []
    memory_md_source = None

    for filename in os.listdir(auto_dir):
        if not filename.endswith('.md'):
            continue
        source = os.path.join(auto_dir, filename)
        if not os.path.isfile(source):
            continue

        # Handle MEMORY.md separately
        if filename == 'MEMORY.md':
            memory_md_source = source
            continue

        # Determine target subdir and new name
        subdir = ''
        newname = filename
        matched = False

        # Check SPEC_ first (already uppercase, just move to subdir)
        if filename.startswith('SPEC_'):
            subdir = 'spec'
            newname = filename
            matched = True

        if not matched:
            for prefix, (target_subdir, new_prefix) in PREFIX_MAP.items():
                if filename.startswith(prefix):
                    subdir = target_subdir
                    # Strip old prefix, uppercase the rest, prepend new prefix
                    rest = filename[len(prefix):]
                    name_part = rest.rsplit('.md', 1)[0]
                    newname = new_prefix + name_part.upper() + '.md'
                    matched = True
                    break

        if not matched:
            # Unknown prefix — uppercase and keep at root
            name_part = filename.rsplit('.md', 1)[0]
            newname = name_part.upper() + '.md'

        # Create subdirectory if needed
        if subdir:
            target_subdir_path = os.path.join(target_dir, subdir)
            os.makedirs(target_subdir_path, exist_ok=True)
            target = os.path.join(target_subdir_path, newname)
            rel_path = f"{subdir}/{newname}"
        else:
            target = os.path.join(target_dir, newname)
            rel_path = newname

        if not os.path.exists(target):
            with open(source) as f:
                content = f.read()
            with open(target, 'w') as f:
                f.write(content)
            migrated.append(rel_path)

    # Merge MEMORY.md
    if memory_md_source:
        target_memory = os.path.join(target_dir, 'MEMORY.md')
        _merge_memory_md(memory_md_source, target_memory, project_root)
        migrated.append('MEMORY.md (merged)')

    return migrated


def _merge_memory_md(source_path, target_path, project_root):
    """Merge auto-memory MEMORY.md entries into target, rewriting paths to match new structure."""
    PREFIX_MAP = {
        'feedback_': 'feedback/FEEDBACK_',
        'user_': 'user/USER_',
        'project_': 'project/PROJECT_',
        'reference_': 'ref/REF_',
    }

    with open(source_path) as f:
        source_lines = f.readlines()

    # Read existing target content (may not exist yet)
    target_content = ''
    if os.path.exists(target_path):
        with open(target_path) as f:
            target_content = f.read()

    new_entries = []
    for line in source_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        # Rewrite link paths in the line
        rewritten = line
        for old_prefix, new_prefix in PREFIX_MAP.items():
            # Match markdown links like ](feedback_test.md)
            pattern = re.escape(old_prefix) + r'([^)]+\.md)'
            def _rewrite(m):
                rest = m.group(1)
                name_part = rest.rsplit('.md', 1)[0]
                return new_prefix + name_part.upper() + '.md'
            rewritten = re.sub(pattern, _rewrite, rewritten)

        # Handle SPEC_ links — just add spec/ prefix
        rewritten = re.sub(r'\]\((SPEC_[^)]+)\)', r'](spec/\1)', rewritten)

        # Check if this entry (by link target) already exists in target
        link_match = re.search(r'\]\(([^)]+)\)', rewritten)
        if link_match:
            link_target = link_match.group(1)
            if link_target not in target_content:
                new_entries.append(rewritten)

    if new_entries:
        with open(target_path, 'a') as f:
            f.write('\n## Migrated from Auto-Memory\n')
            for entry in new_entries:
                f.write(entry if entry.endswith('\n') else entry + '\n')


def prompt_extra_memory_paths():
    """Prompt user for additional directories Serena should access.

    Returns list of paths like ['./docs:ro', './src/config'].
    """
    extra = []
    print("\n--- Additional Serena Memory Paths ---")
    print("Serena can read folders in your project (e.g. ./docs, ./src/config).")
    print("Append :ro for read-only access. Leave blank to skip.\n")
    while True:
        path = input("  Add folder (or press Enter to finish): ").strip()
        if not path:
            break
        # Normalize: ensure starts with ./
        if not path.startswith('./') and not path.startswith('/'):
            path = './' + path
        ro = input(f"  Read-only? (y/N): ").strip().lower()
        if ro in ('y', 'yes'):
            if not path.endswith(':ro'):
                path += ':ro'
        extra.append(path)
        print(f"    Added: {path}")
    return extra


def inject_claude_prefix(project_root):
    """Prepend CLAUDE_PREFIX.md to the project's CLAUDE.md if not already present."""
    prefix_path = os.path.join(PLUGIN_ROOT, 'scripts', 'CLAUDE_PREFIX.md')
    claude_md_path = os.path.join(project_root, 'CLAUDE.md')

    if not os.path.exists(prefix_path):
        return False

    with open(prefix_path, 'r') as f:
        prefix_content = f.read().rstrip('\n')

    # Marker to detect if already injected
    marker = 'MANDATORY ENTRY POINT'

    if os.path.exists(claude_md_path):
        with open(claude_md_path, 'r') as f:
            existing = f.read()
        if marker in existing:
            return False  # Already has the prefix
        # Prepend
        with open(claude_md_path, 'w') as f:
            f.write(prefix_content + '\n\n' + existing)
    else:
        with open(claude_md_path, 'w') as f:
            f.write(prefix_content + '\n')

    return True


def ensure_serena_gitignore(project_root):
    """Create .serena/.gitignore for runtime file exclusions."""
    gitignore_path = os.path.join(project_root, '.serena', '.gitignore')
    if os.path.exists(gitignore_path):
        return False

    content = """/cache

# Stream data (ephemeral, session-specific)
streams/

# Working memory files (session-specific, ephemeral)
memories/WM_*.md
memories/LITE_MODE_*.md

# SWE runtime state
swe-state/
swe-bypass.json
swe-setup-complete.json

# Keep everything else (feature memories, specs, etc.)
!memory/
!memory/**/*.md
!memories/
!/memory-paths.conf
"""
    with open(gitignore_path, 'w') as f:
        f.write(content)
    return True


def update_gitignore(project_root):
    """Add SWE-specific entries to .gitignore if not already present."""
    gitignore_path = os.path.join(project_root, '.gitignore')
    entries = [
        '.serena/swe-bypass.json',
        '.serena/swe-setup-complete.json',
        '.serena/swe-state/',
        '',
        '# Override global .serena/* ignore — un-ignore project memories',
        '!.serena/memory/',
        '!.serena/memory/**/*.md',
        '!.serena/memories/',
        '!.serena/memories/**/*.md',
        '.serena/memories/WM_*.md',
    ]

    existing_content = ''
    if os.path.exists(gitignore_path):
        with open(gitignore_path) as f:
            existing_content = f.read()

    # Check if already configured (use the negation pattern as marker)
    if '!.serena/memory/' in existing_content:
        return False

    with open(gitignore_path, 'a') as f:
        f.write('\n# SWE workflow engine\n')
        for entry in entries:
            f.write(f'{entry}\n')
    return True



def ensure_mcp_json(project_root):
    """Create or merge .mcp.json with ironbee devtools MCP server entry.

    If .mcp.json exists, merges browser-devtools into existing mcpServers
    without overwriting other entries. If it doesn't exist, creates it.
    Returns True if file was created or modified, False if already configured.
    """
    mcp_file = os.path.join(project_root, '.mcp.json')
    browser_devtools_config = {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "-p", "@ironbee-ai/devtools", "ironbee-browser-devtools-mcp"],
        "env": {
            "BROWSER_HEADLESS_ENABLE": "false",
            "TELEMETRY_ENABLE": "false"
        }
    }

    if os.path.exists(mcp_file):
        try:
            with open(mcp_file) as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            data = {}

        servers = data.get('mcpServers', {})
        if 'browser-devtools' in servers:
            return False  # Already configured

        servers['browser-devtools'] = browser_devtools_config
        data['mcpServers'] = servers
    else:
        data = {
            "mcpServers": {
                "browser-devtools": browser_devtools_config
            }
        }

    with open(mcp_file, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')

    return True


def _read_dotenv(path):
    """Parse a simple KEY=VALUE .env file into a dict. Best-effort, no deps."""
    values = {}
    try:
        with open(path) as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, val = line.partition('=')
                values[key.strip()] = val.strip().strip('"').strip("'")
    except IOError:
        pass
    return values


def ensure_wp_cli_conf(project_root):
    """Create .serena/wp-cli.conf for WordPress projects that use a devcontainer.

    Final bootstrap step. Only acts when BOTH are true:
      - the project is a WordPress project (_detect_framework_type)
      - a .devcontainer/ directory exists

    Auto-derives values from .devcontainer/.env when present (PROJECT_SLUG,
    SSH_HOST/PORT/USER, REMOTE_WP_PATH); otherwise writes documented placeholders.
    Idempotent: never overwrites an existing .serena/wp-cli.conf.

    Returns one of: 'created', 'exists', 'skipped'.
    """
    if _detect_framework_type(project_root) != 'wordpress':
        return 'skipped'
    if not os.path.isdir(os.path.join(project_root, '.devcontainer')):
        return 'skipped'

    conf_path = os.path.join(project_root, '.serena', 'wp-cli.conf')
    if os.path.exists(conf_path):
        return 'exists'

    env = _read_dotenv(os.path.join(project_root, '.devcontainer', '.env'))
    slug = env.get('PROJECT_SLUG', '') or os.path.basename(project_root.rstrip('/'))

    # Local container: devcontainer compose names it "<slug>-devcontainer-1".
    container = f"{slug}-devcontainer-1" if slug else "CHANGEME-devcontainer-1"
    local_path = f"/workspaces/{slug}/public_html" if slug else "/workspaces/CHANGEME/public_html"
    local_workdir = f"/workspaces/{slug}" if slug else "/workspaces/CHANGEME"

    # Remote SSH string (WP-CLI --ssh): [user@]host[:port][path]
    ssh_host = env.get('SSH_HOST', '')
    ssh_port = env.get('SSH_PORT', '')
    ssh_user = env.get('SSH_USER', '')
    remote_path = env.get('REMOTE_WP_PATH', '')
    if ssh_host and ssh_user:
        remote = ssh_user + '@' + ssh_host
        if ssh_port:
            remote += ':' + ssh_port
        if remote_path:
            remote += remote_path
    else:
        remote = "user@host.example.com:22/home/user/public_html"

    lines = [
        "# WP-CLI MCP server — per-project configuration (auto-generated by SWE bootstrap).",
        "# Read at runtime by the swe plugin's wp-cli MCP server. Edit values as needed.",
        "",
        "# ── Local Docker target ──────────────────────────────────────────",
        f"LOCAL_CONTAINER={container}",
        f"LOCAL_PATH={local_path}",
        f"LOCAL_WORKDIR={local_workdir}",
        "",
        "# ── Remote production target (over WP-CLI --ssh) ─────────────────",
        f"REMOTE_SSH={remote}",
        "",
        "# ── Safety: block destructive commands on production unless confirm=true ──",
        "PROD_GUARD=true",
        "",
    ]
    with open(conf_path, 'w') as f:
        f.write('\n'.join(lines))

    return 'created'


def main():
    project_root = os.getcwd()

    # Guard: Check bypass
    bypass_file = os.path.join(project_root, '.serena', 'swe-bypass.json')
    if os.path.exists(bypass_file):
        print("SWE bypassed for this project. Remove .serena/swe-bypass.json to re-enable.")
        sys.exit(0)

    # Guard: Check if already fully initialized (complete=true is the ONLY early exit)
    setup_file = os.path.join(project_root, '.serena', 'swe-setup-complete.json')
    if os.path.exists(setup_file):
        try:
            with open(setup_file) as f:
                setup_data = json.load(f)
            if setup_data.get('complete'):
                print("Already fully initialized. Nothing to do.")
                sys.exit(0)
        except (json.JSONDecodeError, IOError):
            pass  # Corrupt file — proceed with bootstrap

    # All operations below are idempotent — safe to re-run.
    # Existing files are preserved; only missing items are created.

    # Create directories
    dirs = [
        os.path.join(project_root, '.serena'),
                os.path.join(project_root, '.serena', 'memory'),
        os.path.join(project_root, '.serena', 'memory', 'feature'),
        os.path.join(project_root, '.serena', 'memories'),
        os.path.join(project_root, '.serena', 'swe-state'),
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)

    # Detect languages
    languages = detect_languages(project_root)

    # Detect ignored paths (dependencies, build output, framework dirs)
    ignored_paths = detect_ignored_paths(project_root)

    # Create project.yml with languages and ignored paths
    yml_created = create_project_yml(project_root, languages)

    # Prompt for additional memory paths
    extra_paths = prompt_extra_memory_paths()

    # Create/update memory-paths.conf
    conf_updated = ensure_memory_paths_conf(project_root, extra_paths=extra_paths)

    # Build template variables from detected project info
    template_variables = build_template_variables(project_root, languages)

    # Copy and render template memories FIRST (establishes MEMORY.md base + defaults)
    # Idempotent: skips files that already exist at the correct location
    copied_templates = copy_template_memories(project_root, template_variables)

    # Migrate existing auto-memory files (appends to MEMORY.md, skips files that exist)
    migrated_files = migrate_auto_memory(project_root)

    # Create README.md only if zero non-dot files exist
    non_dot_files = [f for f in os.listdir(project_root) if not f.startswith('.')]
    if not non_dot_files:
        readme_path = os.path.join(project_root, 'README.md')
        if not os.path.exists(readme_path):
            with open(readme_path, 'w') as f:
                f.write('# Project\\n')

    # Create .serena/.gitignore
    serena_gitignore_created = ensure_serena_gitignore(project_root)

    # Update project .gitignore
    gitignore_updated = update_gitignore(project_root)

    # Create/merge .mcp.json with ironbee devtools
    mcp_json_updated = ensure_mcp_json(project_root)

    # WordPress + devcontainer projects: install wp-cli MCP config (final step)
    wp_cli_conf_status = ensure_wp_cli_conf(project_root)

    # Inject CLAUDE_PREFIX.md into CLAUDE.md
    claude_prefix_injected = inject_claude_prefix(project_root)

    # Create swe-setup-complete.json LAST — only after all operations succeed
    version = get_plugin_version()
    setup_data = {
        "complete": False,
        "bootstrapped": True,
        "bootstrapped_at": datetime.now().isoformat(),
        "version": version,
        "needs_full_init": True,
    }
    with open(setup_file, 'w') as f:
        json.dump(setup_data, f, indent=2)

    # Report
    print("SWE Bootstrap Complete")
    print(f"  Plugin version: {version}")
    print(f"  Project name: {template_variables['project_name']}")
    print(f"  Primary language: {template_variables['primary_language']}")
    print(f"  Languages detected: {', '.join(languages)}")
    print(f"  Test framework: {template_variables['test_framework']}")
    print(f"  project.yml: {'created' if yml_created else 'already exists'}")
    if ignored_paths:
        print(f"  ignored_paths: {len(ignored_paths)} exclusions detected ({', '.join(ignored_paths[:5])}{'...' if len(ignored_paths) > 5 else ''})")
    else:
        print(f"  ignored_paths: none detected (clean project)")
    print(f"  memory-paths.conf: {'updated' if conf_updated else 'already configured'}")
    if extra_paths:
        print(f"  Extra paths added: {', '.join(extra_paths)}")
    if migrated_files:
        print(f"  Auto-memory migrated: {', '.join(migrated_files)}")
    if copied_templates:
        print(f"  Templates rendered: {', '.join(copied_templates)}")
    else:
        print(f"  Templates: all already exist (skipped)")
    print(f"  .serena/.gitignore: {'created' if serena_gitignore_created else 'already exists'}")
    print(f"  .gitignore: {'updated' if gitignore_updated else 'already configured'}")
    print(f"  .mcp.json: {'updated' if mcp_json_updated else 'already configured'}")
    if wp_cli_conf_status == 'created':
        print(f"  wp-cli.conf: created (WordPress + devcontainer detected)")
    elif wp_cli_conf_status == 'exists':
        print(f"  wp-cli.conf: already exists")
    print(f"  CLAUDE.md: {'prefix injected' if claude_prefix_injected else 'already configured'}")
    print(f"  Setup status: bootstrapped (run /swe-init to complete, or /swe-scaffold-project for manual setup)")


if __name__ == '__main__':
    main()
