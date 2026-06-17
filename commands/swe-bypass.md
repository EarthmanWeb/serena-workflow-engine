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

## Implementation

Execute immediately:

1. Read `.serena/swe-setup-complete.json` if present (else start from `{}`).
2. Set `bypass` to `true`.
3. Write the file back (pretty-printed JSON).
4. Confirm: "SWE workflow bypassed for this project. Run `/swe-bypass-off` or
   set `\"bypass\": false` in `.serena/swe-setup-complete.json` to re-enable."

## Re-enabling

Set `"bypass": false` (or remove the field) in
`.serena/swe-setup-complete.json`. The next session will resume the normal
workflow.
