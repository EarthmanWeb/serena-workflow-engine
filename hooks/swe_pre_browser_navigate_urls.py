#!/usr/bin/env python3
"""PreToolUse hook for mcp__playwright__browser_navigate - Require REF_DEV_URLS."""

import os
import sys
import json

PLUGIN_ROOT = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
if PLUGIN_ROOT:
    hooks_dir = os.path.join(PLUGIN_ROOT, 'hooks')
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)

try:
    from swe_hooks.core.output import output_block
except ImportError as e:
    output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": f"SWE import error: {e}"}}
    print(json.dumps(output), file=sys.stdout)
    sys.exit(0)


def main():
    output_block(
        """🌐 BROWSER NAVIGATE DETECTED - READ REF_DEV_URLS FIRST

Before using mcp__playwright__browser_navigate, you MUST read:

```
mcp__serena__read_memory("REF_DEV_URLS")
```

This memory contains correct URL patterns for all environments.

DO NOT guess URLs."""
    )


if __name__ == '__main__':
    main()
