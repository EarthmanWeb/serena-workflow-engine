---
name: Harness Token-Efficiency Study (Hub)
description: Hub report for the harness token-efficiency study; verified figures only.
metadata:
  type: report
---

## Scope

Latest-5 sessions: 63 transcripts, 2,939 API calls.
Input 561.8M (cache-read 550.4M, cache-create 11.3M); output 0.72M.
Baseline ~60k/call ≈ 32% (~180M).
Subagents = 61% of input (58 agents).
Main avg ctx 267k/call; sub avg 162k/call (sonnet 171k, opus 147k, haiku 61k).

## Tool groups (calls / result tok / carry)

- serena-memory: 571 / 1,088k / 66.5M
- Read: 346 / 478k / 19.4M
- Bash-read: 228 / 200k / 10.4M
- serena-symbol: 246 / 122k / 9.9M
- Bash-other: 672 / 283k / 9.3M
- Bash-search: 388 / 142k / 6.1M
- serena-search: 91 / 45k / 2.2M
- hooks total: ~70k tok

## Reads

- 145 full reads = 356k tok; 201 windowed reads = 122k tok (avg 605 tok/call).
- find_symbol+body avg 609 tok/call.
- 10 Reads >10k tok = 130k tok total.
- Bash grep 388 calls vs serena search 91 calls.
- search_for_pattern: 27/91 empty; 2 overflow results (521k, 352k chars); 1 confirmed false negative (mailgun_id).

## Memory sources

- Subagent upfront required reading: 830k tok total; median 16.6k/agent; max 33k/agent.
- FEATURE_TESTS: 44 reads, 228k tok.
- DEV_SCSS: 30 reads, 101k tok.
- DEV_PHP: 33 reads, 75k tok.
- wf/claude machinery in main: 72k tok.
- WF_CLASSIFY: 9 reads, 27.5k tok in one session.

## Benchmark tokens (Serena / rg+full / rg+targeted)

Total: 8,610 / 66,587 / 6,044.
Latency: Serena 0.03-9.4s; rg 0.008-0.36s.

## PRE/MID/POST summary

See `mem:report/REPORT_HARNESS_TOKEN_STUDY_PRE_POST` for full breakdown. Headline: combined memory tok per main session rose ~63.7k to ~116.8k (+83%) POST, driven by subagent upfront reads (median 0 to 18,748).

## Gates

See `mem:report/REPORT_HARNESS_TOKEN_STUDY_GATES` for full breakdown. Headline: docs-first denies PRE 46/MID 5/POST 22 with 0% same-tool retry; drift advisory/hard PRE 601/2 to POST 333/446 with Agent calls in drift sessions flat 184 to 186; scope exhaustion PRE 0 to POST 67 events across 43/188 subagents.

## Verdicts

- **KEEP**: scope budgets, destructive-Bash gates, memory-fs gate, classify Tier-0 digest.
- **SHRINK**: sweep-gate (QW1 done), drift (QW2 done), WF re-reads (QW3 done).
- **RETIRE**: docs-first gate; Serena-first doctrine narrows to Serena = memory ops only.
- **FIX**: em-serena search (false negatives / overflow).

## Related Memories

`mem:report/REPORT_HARNESS_TOKEN_STUDY_TOOLS` — tool-group breakdown
`mem:report/REPORT_HARNESS_TOKEN_STUDY_PRE_POST` — PRE/MID/POST drilldown
`mem:report/REPORT_HARNESS_TOKEN_STUDY_GATES` — gate cost-benefit analysis
