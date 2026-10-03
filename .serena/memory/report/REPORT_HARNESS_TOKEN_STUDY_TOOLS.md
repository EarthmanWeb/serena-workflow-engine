---
name: Harness Token Study — Tool Group Costs
description: Tool-group cost/latency breakdown for the harness token-efficiency study; verified figures only.
metadata:
  type: report
---

## Tool groups (calls / result tok / carry)

| Tool Group    | Calls | Result Tok | Carry |
| ------------- | ----- | ---------- | ----- |
| serena-memory | 571   | 1,088k     | 66.5M |
| Read          | 346   | 478k       | 19.4M |
| Bash-read     | 228   | 200k       | 10.4M |
| serena-symbol | 246   | 122k       | 9.9M  |
| Bash-other    | 672   | 283k       | 9.3M  |
| Bash-search   | 388   | 142k       | 6.1M  |
| serena-search | 91    | 45k        | 2.2M  |
| hooks (total) | —     | ~70k       | —     |

## Read breakdown

- Full reads: 145 calls = 356k tok.
- Windowed reads: 201 calls = 122k tok (avg 605 tok/call).
- find_symbol+body avg: 609 tok/call.
- Reads >10k tok: 10 calls = 130k tok.

## Search comparison

- Bash grep: 388 calls.
- Serena search: 91 calls.
- search_for_pattern empty results: 27/91.
- search_for_pattern overflow results: 2 (521k chars, 352k chars).
- Confirmed false negative: mailgun_id query.

## Memory-source costs

| Source                            | Reads     | Tok                                            |
| --------------------------------- | --------- | ---------------------------------------------- |
| Subagent upfront required reading | 58 agents | 830k total (median 16.6k/agent, max 33k/agent) |
| FEATURE_TESTS                     | 44        | 228k                                           |
| DEV_SCSS                          | 30        | 101k                                           |
| DEV_PHP                           | 33        | 75k                                            |
| wf/claude machinery (main)        | —         | 72k                                            |
| WF_CLASSIFY (one session)         | 9         | 27.5k                                          |

## Benchmark: Serena vs ripgrep

| Approach           | Total Tok | Latency Range |
| ------------------ | --------- | ------------- |
| Serena             | 8,610     | 0.03-9.4s     |
| rg + full read     | 66,587    | 0.008-0.36s   |
| rg + targeted read | 6,044     | 0.008-0.36s   |

## Related Memories

`mem:report/REPORT_HARNESS_TOKEN_STUDY` — hub
`mem:report/REPORT_HARNESS_TOKEN_STUDY_PRE_POST` — PRE/MID/POST drilldown
`mem:report/REPORT_HARNESS_TOKEN_STUDY_GATES` — gate cost-benefit analysis
