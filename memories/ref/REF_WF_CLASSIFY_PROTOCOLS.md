---
name: WF_CLASSIFY Protocols — Gherkin Detection, Skill Invocation, Parallel-Agent Signals
description: Gherkin spec detection detail, the skill/command invocation protocol, and expanded parallel-subagent signals for WF_CLASSIFY. Open when Gherkin specs are involved, when routing to a workflow-aware skill, or when scoping a parallel-subagent task.
metadata:
  type: reference
obligations:
  - Route explicit Gherkin authoring requests to /swe-gherkin-spec and TDD-from-spec requests to /swe-gherkin-dev.
  - When routing to a workflow-aware skill, set WM context (calling step, feature key, session ID, return step, invocation mode) before invoking it.
---

# WF_CLASSIFY Protocols

## Gherkin Spec Detection (Step 2d, full)

1. Explicit Gherkin request (user asks to write specs, create `.feature` files, or do BDD/TDD from specs):
   - Note `gherkin_spec: true` in WM.
   - Route to `/swe-gherkin-spec` (authoring) or `/swe-gherkin-dev` (TDD from existing spec).
2. New feature development (user describes new functionality to build):
   - Check SPEC_* memories for the feature: `list_memories(topic="spec")` — NAMES ONLY. Do NOT read spec bodies here.
   - No specs exist → note `gherkin_spec_needed: true` in WM (enforced at WF_ARCH_REVIEW).
3. Feature addition to an existing feature with Gherkin specs:
   - Check `.feature` files: `Glob(pattern="tests/specs/*[feature-key]*.feature")`.
   - Specs exist → note `gherkin_spec_update: true` in WM (enforced at WF_VERIFY).

## Skill Invocation Protocol

When routing to a workflow-aware skill (e.g. `/research`):

1. Set workflow context in WM: calling step, feature key, session ID, return step, invocation mode.
2. Inform user: `> Routing to /research skill. Will return to WF_CLASSIFY on completion.`
3. Handle return:

| Status                              | Action                  |
| ----------------------------------- | ----------------------- |
| `success` / `success_with_findings` | Continue to return step |
| `needs_clarification`               | `WF_CLARIFY`            |
| `blocked`                           | `WF_CLARIFY`            |

## Command & Skill Identification (Step 2c, full)

Before planning manual implementation, check for an existing command or skill that handles the task.

Scan locations:

1. System-reminder skills list (already in context) — match intent against skill descriptions.
2. Project/user commands — `.claude/commands/*.md`, `.claude/skills/*/SKILL.md`, `~/.claude/commands/*.md`, `~/.claude/skills/*/SKILL.md`.
3. Plugin commands — installed plugin `commands/` directories.

- Use fuzzy intent matching. Respect `disable-model-invocation` (user-only skills).
- Match found → note `matched_skill: plugin:skill-name` or `matched_command: /command-name` in WM, then invoke it. Commands/skills may handle routing themselves.
- No match → continue to Step 3.

## Parallel Subagents — Signal Detail

Triggers (ANY): 2+ independent subtasks, OR explicit operator fan-out request, OR 6+ files, OR 3+ architectural layers.

Independent concurrent subtasks with disjoint file ownership — orchestrator mode per `feature/FEATURE_SUBAGENTS` is the DEFAULT, not an escalation. Note `parallel_agents: true`; use `Agent` tool with `run_in_background: true`, explicit `model` per tier, and optionally `isolation: "worktree"` for edit conflicts. Route to `WF_ARCH_REVIEW`.
