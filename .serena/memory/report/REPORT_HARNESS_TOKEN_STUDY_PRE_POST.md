---
name: Harness Token Study — PRE/MID/POST Obligations Analysis
description: Before/after comparison of main-session and subagent memory token cost around the required-reading rollout; verified figures only.
metadata:
  type: report
---

## Epochs

- PRE: before 2026-09-30T07:57Z.
- MID: 2026-09-30T07:57Z to 2026-10-01T00:15Z.
- POST: on/after 2026-10-01T00:15Z.

## Session/subagent counts

| Epoch | Sessions | Subagents |
| ----- | -------- | --------- |
| PRE   | 93       | 401       |
| MID   | 25       | 264       |
| POST  | 40       | 188       |

## Main agent (orchestrator)

| Metric             | PRE    | MID    | POST   |
| ------------------ | ------ | ------ | ------ |
| Mem tok/session    | 48,475 | 24,330 | 26,933 |
| Task reads/session | 20.3   | 8.5    | 10.2   |

## Subagent

| Metric         | PRE   | MID   | POST   |
| -------------- | ----- | ----- | ------ |
| Mem tok mean   | 3,516 | 7,879 | 19,116 |
| Upfront median | 0     | 0     | 18,748 |
| Reads/sub      | 1.1   | 4.8   | 8.4    |

## Digest usage in prompts

- PRE: 0/401.
- MID: 75/264.
- POST: 187/188.

## Required-reading compliance

Names fully read: 1,221/1,398 (87%).

## Combined memory tok per main session

≈63.7k (PRE) → ≈116.8k (POST), +83%.

## Related Memories

`mem:report/REPORT_HARNESS_TOKEN_STUDY` — hub
`mem:report/REPORT_HARNESS_TOKEN_STUDY_TOOLS` — tool-group breakdown
`mem:report/REPORT_HARNESS_TOKEN_STUDY_GATES` — gate cost-benefit analysis
