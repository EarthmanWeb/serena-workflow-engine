---
name: WF_RESEARCH
description: Research-only workflow state — observe runtime symptoms first, recency triage on regressions, symptom-keyed memory search, static Serena exploration, verified-diagnosis exit criteria; no code changes.
metadata:
  type: workflow
---

# WF_RESEARCH — Research Only

> **On step WF_RESEARCH**

## Verify Before Assert

- Research findings ARE factual claims.
- Any statement about backend/environment state (DB contents, existing environments, container state, remote data) MUST be preceded by a verification call (`wp_cli`, `terminus`, `docker`, logs) in the SAME turn.
- Rendering claims need rendering verifiers: browser tools, or curl of the page HTML + the enqueued asset list. NEVER assert "the page shows/loads X" from repo files alone.
- When you cannot verify, label the finding "unverified". NEVER present plausible inference as fact.

## Memories Are Hypotheses

- Memories are HYPOTHESES about the code, not ground truth. Verify every load-bearing claim (paths, URLs, class mappings, version numbers) against the code/environment before acting on it.
- Doc drift: on ANY doc↔code conflict found, correct the memory in the same session — immediate edit, or add it to a WM doc-drift list flushed at WF_VERIFY. A memory that contradicts the code is a FINDING, never context to obey.

## Step 1 — Observe the Runtime Symptom FIRST

Applies to RUNTIME symptoms (rendering/behavior a user reports). Static-only exploration remains the default ONLY for pure code-comprehension questions.

- Observe the symptom + capture runtime state BEFORE any static exploration: which stylesheet/script/asset serves (or served) the affected rule — browser tools, curl of page HTML + enqueued asset list, live-vs-local diff.
- Ask "where does the page get this rule?" before "when did the repo delete this string?".
- Runtime-source rule: when a selector/class/asset "has no definition in our code", enumerate what ships it at runtime (plugin CSS/JS, CDN, vendor bundles) BEFORE concluding on repo history. Applies to DIAGNOSING a symptom only — NEVER apply it to an explicit add/hide/remove/change instruction; see `mem:claude/CLAUDE_OBLIGATIONS` Direct Instruction Fast Path.

## Step 2 — Recency Triage (WM has `regression: recent`)

- Recency triage is the FIRST research action: `git log --oneline -15` plus diff of the most recent deploy/merge across EVERY surface that loads on the affected page (plugins, mu-plugins, themes, dist, config).
- Deep history walks come only AFTER recency candidates are exhausted.
- Archaeology trap: a runtime regression can occur with ZERO repo deletions (conditional enqueues, plugin version bumps, CDN/config changes). "No removal found in git history" is NOT evidence against a regression, and an old removal is NOT the trigger.

## Step 3 — Check Knowledge Base (symptom-keyed first)

- Symptom-keyed search FIRST: search memories on the request's LITERAL symptom tokens (error strings, class names, option keys), then feature nouns.
- Then the topic lists:
  - `list_memories(topic="dom")` — domain behavior docs
  - `list_memories(topic="ref")` — reference patterns
  - `list_memories(topic="feature")` — feature configs
- Read every memory relevant to the question. Memories may hold file paths, architecture notes, and behavioral patterns that shortcut code exploration — verify load-bearing claims per "Memories Are Hypotheses" before asserting them.

## Step 4 — Explore with Serena Tools

- When memories + runtime observation do not fully answer the question, explore with:
  - `mcp__plugin_swe_serena__find_symbol`
  - `mcp__plugin_swe_serena__get_symbols_overview`
  - `mcp__plugin_swe_serena__search_for_pattern`

## Step 5 — Report Findings

- Report findings directly to the user.
- Diagnosis tasks: apply the Diagnosis Exit Criteria below before reporting a cause.

## Diagnosis Exit Criteria

A diagnosis is a hypothesis until it passes THREE checks, recorded in the final message of any diagnosis task, using this EXACT block format:

```
DIAGNOSIS VERIFICATION:
- MECHANISM: <exact before/after code path producing the symptom>
- TIMING: <the change postdates last-known-good — explains WHY NOW>
- COUNTERFACTUAL: <prior state demonstrably produced the working behavior>
```

- Unmet checks are labeled: `candidate — unverified: <mechanism|timing|counterfactual>`
- A cause older than the symptom's onset is a "latent gap", NEVER "the regression" — report it as context and keep hunting for the trigger.
- The three-check block and the `candidate — unverified` label are exempt from the terse-format word budget and must never be stripped.

## Rules

- NEVER make code changes in this path.
- NEVER create files. Exception: correcting a drifted memory (doc-drift obligation above) is memory maintenance, not a code change — allowed.
- Information gathering only.

## Routing

| Condition                             | Next Step     |
| ------------------------------------- | ------------- |
| Research complete, user wants changes | `WF_CLASSIFY` |
| Research complete, no changes needed  | `WF_DONE`     |

- Route to `WF_CLASSIFY` to classify the task and load feature context when the user wants to implement based on findings.
- A change request mid-research ("implement", "do it", "do everything", "fix", "add"...) emits a `needs_implementation` directive from the prompt hook — take it by reading `wf/WF_CLASSIFY` (`WF_RESEARCH → WF_CLASSIFY` is a declared `readBackward` entry, so the read itself transitions).
- If the hook instead reports "inspecting — no transition" on that read (loop guard fired), call `mcp__plugin_swe_swe-wm__swe_wm_transition(session_id="<id>", target_state="WF_CLASSIFY", reason="needs_implementation")` — the explicit fallback.
- Complete with no changes needed → `WF_DONE`: read `wf/WF_DONE` (forward read-advance) or call `swe_wm_transition` with `reason="research_complete"`.
- Run `/swe-wm-update` to update WM before transitioning.
