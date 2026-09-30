---
name: Single Test Run Per Stage
description: Run each test suite ONCE per verified stage — never re-run a green suite; implementation agents run only their scoped tests.
metadata:
  type: feedback
---

# FEEDBACK_SINGLE_TEST_RUN

Run the full test suite ONCE per verified stage, at the stage's end, by one (haiku) agent. NEVER re-run a suite that is already green this stage.

**Why:** Operator flagged the same suite running 3-4× across one stage (workflow test phase, per-agent full runs, orchestrator pre-commit re-runs) — pure duplicate spend; a green result is the result.

**How to apply:**

- Implementation agents: `py_compile` + ONLY the tests scoped to their owned files.
- One full-suite verification per stage — the final pre-commit run. Trust it; do not repeat it in the same stage.
- Re-run ONLY when files changed after the last green run.
- Enforced wording lives in `[[FEATURE_SUBAGENTS]]` Delegation Economics (plugin source `memories/feature/FEATURE_SUBAGENTS.md`).
