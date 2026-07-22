---
name: CLAUDE
description: Development reference — mandatory hook actions, core coding principles, file-creation constraints.
metadata:
  type: reference
---

# CLAUDE.md — Development Reference

## Mandatory Hook Actions

ALWAYS obey hook data. Before proceeding, confirm:

- Followed hook instructions exactly.
- Read all references named in hook responses COMPLETELY.
- Checked `INDEX_FEATURES` or `MEMORY.md` for existing features.
- Used Serena tools before Read/Edit.
- Logged findings to WM.
- Updated WM after significant steps.

## Core Principles

Apply in priority order: KISS → DRY → YAGNI.

- Write simple, readable code.
- Extract at 3+ occurrences (not fewer).
- Build only when needed.

"Let It Fail":

- Do NOT add defensive code; remove existing defensive code.
- Fail clearly.
- NEVER add fallbacks that mask failures.

## File Creation

- Do what is asked — nothing more, nothing less.
- NEVER create files unnecessarily.
- ALWAYS edit existing files instead of creating new ones.
- NEVER create documentation proactively; create it only when explicitly requested.
