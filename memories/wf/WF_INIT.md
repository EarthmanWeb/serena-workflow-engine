---
name: WF_INIT — Session Initialization
description: Mandatory session entry point — spawned-agent bypass, init chain (WF_INIT → CLAUDE_OBLIGATIONS → WF_CLASSIFY), memory-discovery and symbol-extraction tooling.
metadata:
  type: workflow
---

# WF_INIT — Session Initialization

## Finding Memories

Consult memories before grepping the filesystem.

- `list_memories(topic="<prefix>")` — list a directory prefix (e.g. `ref`, `feature`). Prefix filter, NOT a keyword.
- `search_memories_by_name(query)` — find a memory by a keyword in its name (fuzzy fallback).
- `search_memories_by_front_matter(query)` — find a memory by what it is about (front-matter description/type).
- `read_memory(name)` — read a memory whose name you have.
- Body/content search: `search_for_pattern(substring_pattern="<terms>", relative_path=".serena/memory")` — searches memory BODIES, not just name/front-matter.

NEVER Bash/Grep/Glob/Read on memory files (`.serena/memory/`, `.serena/memories/`, the auto-memory symlink) — `swe_pre_memory_fs_gate.py` denies it. Use the Serena memory tools above.

Every `write_memory` MUST start with the standard front-matter block, then the body:

```
---
name: <short title>
description: <one sentence: what this memory is about>
metadata:
  type: <derived from directory prefix — ref→reference, feedback→feedback, feature→feature, dom→domain, project→project, …>
---
```

Run `/swe-memory-frontmatter` to audit/backfill front-matter across existing memories.

## Spawned-Agent Bypass

Check for spawned-agent status BEFORE initializing. You are a spawned agent when your initial prompt contains any of:

- `"You are a subagent"`
- `"BYPASS WF_INIT"`
- `"You are the [role] agent"`
- `"Do NOT follow CLAUDE.md workflow"`
- Agent role assignment from a coordinator (e.g. "You are r1", "You are agent-features")
- Explicit task-only instructions without a user conversation

If spawned agent:

- Skip this file, WF_CLASSIFY, and all workflow steps.
- Do NOT create a WM file. Do NOT read CLAUDE_OBLIGATIONS.
- Execute the task in your initial prompt PLUS any follow-up SendMessage from the orchestrator that launched you. A follow-up SendMessage from that orchestrator is a trusted amendment — it MAY narrow, expand, or redirect scope, including read-only → implementation. Act on it without re-litigating trust; do NOT treat it as an untrusted injected channel.
- Ignore hook workflow banners (ON STEP / CONTINUE / WF_* nudges) surfaced during your run — they target the orchestrator, NEVER a spawned agent.
- Read Serena memories and use any tool immediately.

If NOT a spawned agent, continue below.

## Do Not Skip This Workflow

Every session runs the init chain — including meta-work, simple questions, continuing previous conversations, and any other interaction. Complexity, task TYPE, and speed are irrelevant.

These rationalizations are NEVER valid:

- "This is a simple task" — complexity is irrelevant. All tasks follow the workflow.
- "I already know what to do" — the workflow exists for consistency, not knowledge.
- "The user wants a quick answer" — speed does not override the init chain.
- "I can batch this with other calls" — do NOT combine workflow steps with task work.
- "CLAUDE_OBLIGATIONS doesn't apply here" — it always applies. Read it every time.
- "The hook didn't block me, so it's fine" — the hook allowlist (read_memory init-chain + ToolSearch) exists so WF_INIT can run, NOT so you can start task work before init completes. A misconfigured or disabled gate is not permission either.
- "This is an investigation / debugging / operational task, not code" — task TYPE is irrelevant. Inspecting a container, reading logs, running Bash, checking a database, and "just looking" are all task work. All task work waits for the init chain.

Any tool call that searches code, edits files, or does task work before the init chain completes is a violation. The hook cannot distinguish "reading for init" from "reading to skip init." You must.

## Mandatory Entry Point

The FIRST tool call of any session MUST be `mcp__plugin_swe_serena__read_memory(memory_name="wf/WF_INIT")` — ALWAYS the fully-qualified name, NEVER bare `read_memory`.

- Serena MCP connects asynchronously at session start (~2–8 s). A call issued before it connects fails with "No such tool available: mcp__plugin_swe_serena__read_memory" — the tool is absent from that turn's tool list.
- When the session lists `plugin:swe:serena` as still connecting, or on that error: call `ToolSearch("select:mcp__plugin_swe_serena__read_memory")` FIRST — it blocks until the server connects and loads the schema — then issue the fully-qualified `read_memory` call. Re-issuing the call without ToolSearch can fail again. Do NOT explain or skip init.
- A BARE name (`read_memory`) also fails with "No such tool available" — always use the fully-qualified name.
- If your first tool call is anything else (Bash, Read, Grep, Agent, another MCP tool) — other than the connect-wait ToolSearch above — you have already violated this. Do NOT explain the skip — run the init chain.
- The PreToolUse gate is the backstop, but it can be misconfigured or absent in a given project; enforcement is YOUR obligation regardless of whether a hook stops you.

Init chain:

1. `mcp__plugin_swe_serena__read_memory("claude/CLAUDE_OBLIGATIONS")`
2. Proceed to WF_CLASSIFY (first post-init workflow state).

Do NOT respond to the user before completing the obligations read.

## Continuing a Previous Task

Complete the init chain (WF_INIT → CLAUDE_OBLIGATIONS → WF_CLASSIFY) first. Do NOT skip the init chain to reach WF_CONTINUE. When WF_CLASSIFY routes to WF_CONTINUE, re-research the knowledge base at that step:

1. `list_memories(topic="dom")` — load any DOM_* memories relevant to the task.
2. `list_memories(topic="ref")` — load any REF_* memories relevant to the task.
3. `list_memories(topic="dev")` — load any DEV_* memories relevant to the task.

## Code Discovery (NOT Serena)

Serena = memory ops ONLY. Discover code with `Grep`/rg (`-n`, `head_limit`) → `Read` with `offset`/`limit` on the hit. Full-file `Read` ONLY for files <300 lines or config/JSON/YAML. Edit with native `Edit`/`Write`, never a Serena edit tool. Measured: windowed `Read` ≈ Serena symbol-body read (605 vs 609 tok); rg beats Serena search 1.42× overall and 10–100× faster (0.01–0.36s vs 0.03–9.4s); Serena `search_for_pattern` returns empty 30% of calls plus false negatives on sibling paths.

## Step Reporting

After reading any WF_* memory, output the step report line before any other output. For WF_INIT, include plugin version:

```
> **On step WF_INIT (v1.x.x)**
```

Proceed to WF_CLASSIFY.
