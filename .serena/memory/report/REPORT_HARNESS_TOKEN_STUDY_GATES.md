---
name: Harness Token Study — Gate Effectiveness & Cost-Benefit
description: Gate-by-gate error-rate and drift/scope-exhaustion analysis; verified figures only.
metadata:
  type: report
---

## Error rates

| Track    | PRE  | POST |
| -------- | ---- | ---- |
| Main     | 4.8% | 4.3% |
| Subagent | 3.7% | 3.9% |

## Flail (>=3 consecutive errors) per subagent transcript

- PRE: 20/401 (5.0%).
- POST: 15/188 (8.0%).

## Docs-first search gate

- Hard denials: PRE 46 / MID 5 / POST 22.
- Same-tool retry after denial: 0%.
- **Verdict: RETIRE.**

## Bash-policy denies

- Retried same tool after deny: 86-88%.

## Drift gate

- Advisory/hard blocks: PRE 601 advisory / 2 hard → POST 333 advisory / 446 hard.
- Agent calls in drift sessions: 184 → 186 (flat).
- **Verdict: SHRINK (QW2 done — counts mutating ops only).**

## Scope exhaustion

- PRE: 0 events.
- POST: 67 events across 43/188 subagents.

## Verdicts summary

- **KEEP**: scope budgets, destructive-Bash gates, memory-fs gate, classify Tier-0 digest.
- **SHRINK**: sweep-gate (QW1 done), drift (QW2 done), WF re-reads (QW3 done).
- **RETIRE**: docs-first gate.
- **FIX**: em-serena search (false negatives / overflow — see `mem:report/REPORT_HARNESS_TOKEN_STUDY_TOOLS`).

## Related Memories

`mem:report/REPORT_HARNESS_TOKEN_STUDY` — hub
`mem:report/REPORT_HARNESS_TOKEN_STUDY_TOOLS` — tool-group breakdown
`mem:report/REPORT_HARNESS_TOKEN_STUDY_PRE_POST` — PRE/MID/POST drilldown
