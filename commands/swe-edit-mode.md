---
name: swe-edit-mode
description: Toggle edit mode (direct-instruction fast path gate)
argument-hint: [on|off|status]
---

# /swe-edit-mode [on|off|status]

Turn the session's edit-mode flag on, off, or report its status. No argument toggles the current value.

## What edit mode does

While ON and the session is in `WF_EXECUTE`, a literally-targeted edit instruction gets the `⚡ DIRECT INSTRUCTION` fast-path note (stay in place, apply immediately, no searching/delegating) — see `mem:claude/CLAUDE_OBLIGATIONS` Direct Instruction Fast Path. Outside edit mode, or outside `WF_EXECUTE`, the same prompt routes normally (classification / pivot analysis / delegation).

## Usage

```
/swe-edit-mode on
/swe-edit-mode off
/swe-edit-mode status
/swe-edit-mode
```

## Steps

1. Resolve the session id — the 8-char id printed in every hook message (`WM[<id>]` / `session="<id>"`), also the WM filename `WM_<id>.md`.
2. Run the CLI tool:
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/hooks/swe_hooks/tools/edit_mode.py" <session_id> <on|off|status|toggle>
   ```
   No argument given to the command → pass `toggle`. JSON output; exits 1 only on a write/remove failure.
3. Report the resulting state: `✏️ EDIT MODE ON — literal edits go straight to WF_EXECUTE; say 'exit edit mode' to leave` or `EDIT MODE OFF`.

## Notes

- Edit mode auto-clears whenever the session leaves `WF_EXECUTE` for `WF_CLASSIFY` (new task / pivot) — see `mem:dom/DOM_SWE_HOOKS_PROMPT_ROUTING`.
- The phrases "edit mode" / "enter edit mode" / "edit mode on" (leading or whole-prompt) turn it ON without this command; "exit edit mode" / "edit mode off" turn it OFF the same way.
