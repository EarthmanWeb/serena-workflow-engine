# Task Completion Checklist

When a task is completed, run these steps:

1. **Format code**: `npm run fmt` (formats markdown and JSON via dprint)
2. **Format check**: `npm run fmt:check` (verify no formatting issues)
3. **Version bump** (if releasing): `bash scripts/bump-version.sh`
4. **Git commit**: Stage and commit changes with descriptive message
5. **Test hooks**: If hook scripts were modified, verify they work by checking Python syntax (`python3 -c "import py_compile; py_compile.compile('path/to/script.py')"`)

Note: There is no formal test suite. The project relies on:
- dprint for formatting validation
- Python syntax checking for hook scripts
- Manual testing through Claude Code plugin system
