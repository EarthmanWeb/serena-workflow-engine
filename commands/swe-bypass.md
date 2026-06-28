---
name: swe-bypass
description: Disable the SWE workflow for this project (user-only command)
disable-model-invocation: true
---

# /swe-bypass

Disable the SWE workflow for **this project**. While bypassed, no init gate,
no WF_* routing, and no enforcement run — every session starts with a brief
notice that the workflow is bypassed and how to re-enable it.

## ⛔ User-only

This command exists **only** so that *you* (the user) can deliberately turn the
workflow off. It is `disable-model-invocation: true` — the assistant cannot run
it, cannot set the bypass on your behalf, and must never edit
`swe-setup-complete.json` to add the bypass field. Enabling the bypass is always
an explicit command you type — never an inferred intent or keyword.

## What it does

Sets `"bypass": true` inside `.serena/swe-setup-complete.json` (the same file
used for initialization — no separate bypass file). If the file does not exist
yet, it is created with `{"complete": false, "bypass": true}`.

The write is performed by a dedicated script, `scripts/swe-bypass.py`, NOT by
the assistant editing the file. The PreToolUse guards hard-block any Edit /
Write / `write_memory` / ad-hoc Bash that injects `"bypass": true` into the
setup file — so the assistant cannot set the bypass on its own or by inferring
intent. The guards make one narrow exception: running `swe-bypass.py`, the
single auditable write path, which only happens because *you* typed this
command (`disable-model-invocation: true`).

## Implementation

Execute immediately — run the bypass script (do NOT edit the JSON directly; the
guards will block that):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/swe-bypass.py"
```

The script reads `.serena/swe-setup-complete.json` (or starts from `{}`), sets
`bypass` to `true`, and writes it back pretty-printed. It prints the
confirmation and how to re-enable. Relay its output to the user.

## Re-enabling

Set `"bypass": false` (or remove the field) in
`.serena/swe-setup-complete.json`. The next session will resume the normal
workflow.
