---
name: WF_ARCH_REVIEW Consent Gate JS Template
description: Full AskUserQuestion JS call template for the Single Question + Consent Gate, including the exact validate-or-continue question text and options.
metadata:
  type: reference
obligations:
  - The final question in the AskUserQuestion call MUST be this exact text and these exact two options — other hooks/docs match this string verbatim.
---

# WF_ARCH_REVIEW — Single Question + Consent Gate: AskUserQuestion Template

Gather every design/approach/blocker question this task raises into a SINGLE `AskUserQuestion` call. The FINAL question in that call MUST be exactly this:

```javascript
AskUserQuestion({
  questions: [
    // ...any design / approach / blocker questions for this task, each with options...
    {
      question: 'Would you like me to validate the final plan with you, or shall I continue through completion?',
      header: 'Plan',
      options: [
        {
          label: 'Validate the plan with me first',
          description: 'Present the assembled plan and wait for explicit go-ahead before implementing',
        },
        {
          label: 'Continue through to completion',
          description: 'Proceed straight through implementation without a separate plan review',
        },
      ],
      multiSelect: false,
    },
  ],
});
```

Answering this call IS consent. There is no second approval prompt.

- "Continue through to completion" skips ONLY the separate plan review. NEVER set `blanket_consent` from it — later questions still go through AskUserQuestion.
