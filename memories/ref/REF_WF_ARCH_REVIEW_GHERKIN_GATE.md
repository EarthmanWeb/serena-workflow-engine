---
name: WF_ARCH_REVIEW Gherkin Spec Gate
description: Prompt + flow for offering Gherkin BDD spec creation before implementation — opens only when WM has gherkin_spec_needed true.
metadata:
  type: reference
obligations:
  - When WM `gherkin_spec_needed: true`, check `tests/specs/**/*.feature` first; if none exist, ask the exact prompt below before Step 1.
---

# WF_ARCH_REVIEW — Gherkin Spec Gate

Open only when WM contains `gherkin_spec_needed: true` (set at WF_CLASSIFY step 2d).

1. Check for existing specs: `Glob(pattern="tests/specs/**/*.feature")`.
2. If no specs exist for this feature, prompt:

```
> This feature has no Gherkin BDD specs. Writing specs before implementation ensures
> testable requirements and enables TDD.
>
> Options:
> - [A] Write specs now with /swe-gherkin-spec (recommended)
> - [B] Skip specs and proceed to implementation
```

3. On [A]: invoke `/swe-gherkin-spec` with the feature key. On return, the `SPEC_*` memory is loaded and the SPEC Fast-Path (`mem:wf/WF_ARCH_REVIEW`) applies.
4. On [B]: clear `gherkin_spec_needed` from WM and continue to Step 1.
