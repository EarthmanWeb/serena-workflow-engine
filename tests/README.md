# SWE Plugin Tests

Stdlib `unittest` only — no third-party deps (matches the plugin's stdlib-only
runtime). Tests import hook modules via `_hookutil.import_hook(...)`.

Run all tests from the plugin root:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Run one file:

```bash
python3 -m unittest tests.test_swe_post_memory_index -v
```

## Files

| File | Covers |
| ---- | ------ |
| `test_swe_post_memory_index.py` | MEMORY.md terse-index enforcement: `SKIP_PREFIXES` (matches only the non-indexed categories), leaked-category detection, size/line/byte budget, over-long entries, `memory_name_in_index`. |
| `test_swe_hook_pure_functions.py` | Previously-untested pure helpers across hooks: bash test gate (`is_test_command`, `check_bash_policy`), init gate (`is_working_memory_write`), prompt workflow (`detect_slash_command`), todo sync (`format_todos`), tool-failure schema correction, stop-block counter, session duration. |
