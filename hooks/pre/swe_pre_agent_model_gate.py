#!/usr/bin/env python3
"""PreToolUse hook for Agent (and legacy Task) — subagent model-tier gate.

Enforces "orchestrator + swarm delegation with complexity-based model tiers":
a spawned agent must (1) name an explicit model, (2) carry the subagent bypass
marker in its prompt so it does not re-run the init chain, and (3) not
over-provision opus for routine mechanical work.

Four independent DENY checks, each with its own message:

1. Missing `model` — every Agent/Task call must pick a tier explicitly
   (haiku/sonnet/opus). Skipped only for a `subagent_type` that is a built-in,
   fixed-model agent (claude-code-guide, statusline-setup) — these ignore the
   `model` param entirely, so demanding one is a false-positive trap. Every
   other subagent_type (general-purpose, Explore, Plan, claude, swe:*, or
   omitted) requires it.
2. Missing subagent bypass marker — the prompt must contain one of the
   recognized bypass phrases ("BYPASS WF_INIT" / "You are a subagent" /
   "swarm agent") or the spawned agent re-runs WF_INIT inside itself, wasting
   the whole init chain on work that should start immediately.
3. `model: "opus"` on a routine task — a conservative keyword heuristic:
   routine markers (run tests, lint, grep, inventory, list files, read-only
   audit/status check) with NO design/architecture markers denies opus and
   suggests haiku. Override with the literal tag `[opus-justified: <reason>]`
   or `[premium-justified: <reason>]` anywhere in the prompt — an assertion,
   not a bypass toggle.
4. ANY `model` in the fable family (PREMIUM tier, alongside opus) — the
   orchestrator itself already runs the premium model, so delegating TO a
   premium subagent defeats the entire point of delegation (moving work off
   the premium tier). Denied unconditionally unless the prompt carries
   `[fable-justified: <reason>]` or `[premium-justified: <reason>]`.

Model-tiering goal: this project's harness must HEAVILY enforce cutting token
usage via parallel + cheaper subagents. Premium models (opus, fable) are never
used where a cheaper tier (haiku for routine/recon/tests, sonnet for
implementation) suffices.

Fail-open on any error (never block real work over a hook bug) and on any
input the hook cannot parse into a clear judgment.
"""

import os
import re
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import output_empty, output_block
    from swe_hooks.core.input import read_stdin_safe, get_input_field
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PreToolUse")


AGENT_TOOL_NAMES = {'Agent', 'Task'}

# subagent_type values that are fixed-model built-ins — Agent's `model` param
# has no effect on them, so requiring it would be a false-positive trap.
BUILTIN_FIXED_MODEL_TYPES = {'claude-code-guide', 'statusline-setup'}

VALID_MODELS = {'haiku', 'sonnet', 'opus', 'fable'}

BYPASS_MARKER_RE = re.compile(
    r'BYPASS\s+WF_INIT|you\s+are\s+a\s+subagent|swarm\s+agent',
    re.IGNORECASE,
)

# Accepted justification tags for opus-on-routine: the specific [opus-justified: …]
# tag, or the generic [premium-justified: …] tag shared with the fable gate.
OPUS_JUSTIFIED_RE = re.compile(
    r'\[(?:opus|premium)-justified\s*:\s*[^\]]+\]', re.IGNORECASE)

# Accepted justification tags for the unconditional fable gate: the specific
# [fable-justified: …] tag, or the generic [premium-justified: …] tag.
FABLE_JUSTIFIED_RE = re.compile(
    r'\[(?:fable|premium)-justified\s*:\s*[^\]]+\]', re.IGNORECASE)

# PREMIUM model family — substring match against the lowercased `model` param.
# Covers short aliases ("opus", "fable") and full model ids
# ("claude-opus-5-5", "claude-fable-5-1").
PREMIUM_MODEL_MARKERS = ('opus', 'fable')

# Routine, mechanical work — the canonical "should have been haiku" shapes.
ROUTINE_KEYWORDS_RE = re.compile(
    r'\brun(?:ning)?\s+(?:the\s+)?test|test\s+suite|composer\s+test|npm\s+test|'
    r'npm\s+run\s+test|phpunit|\block\b|lint(?:ing)?|phpcs|phpcbf|eslint|'
    r'\bgrep\b|inventory|list\s+files|read-only\s+audit|read\s+only\s+audit|'
    r'status\s+check|check\s+status|\bformat(?:ting)?\b|dry[- ]run',
    re.IGNORECASE,
)

# Novel design/architecture work — presence of these overrides the routine
# heuristic, since opus is appropriate here even alongside a routine-sounding
# word (e.g. "design the test strategy").
DESIGN_KEYWORDS_RE = re.compile(
    r'\barchitect(?:ure)?\b|\bdesign\b|novel|\brefactor\b|\bmigrat(?:e|ion)\b|'
    r'\bplan(?:ning)?\b|trade-?off|from\s+scratch|greenfield|\bstrategy\b',
    re.IGNORECASE,
)


def _is_agent_tool(tool_name: str) -> bool:
    return tool_name in AGENT_TOOL_NAMES


def _is_premium_model(model: str, marker: str) -> bool:
    """True when `marker` ("opus" or "fable") appears as a lowercase substring
    of `model` — covers both short aliases and full model ids."""
    return marker in (model or '').strip().lower()


def missing_model_reason(tool_input: dict) -> str:
    """Non-empty reason string when `model` is required but absent."""
    model = tool_input.get('model')
    if isinstance(model, str) and model.strip():
        return ''
    subagent_type = str(tool_input.get('subagent_type') or '').strip()
    if subagent_type in BUILTIN_FIXED_MODEL_TYPES:
        return ''
    return (
        "\U0001f3f7️ MISSING model tier on this Agent call "
        f"(subagent_type={subagent_type or 'unspecified/general-purpose'}).\n\n"
        "Pick one explicitly:\n"
        "  - haiku  — routine, mechanical work (tests, lint, grep, inventory, "
        "read-only audits, status checks)\n"
        "  - sonnet — implementation and verification (the default for real "
        "code changes)\n"
        "  - opus   — novel architecture/design ONLY (new systems, hard "
        "trade-offs, greenfield design)\n\n"
        "Add `model: \"haiku\"|\"sonnet\"|\"opus\"` to this Agent call."
    )


def missing_bypass_marker_reason(prompt: str) -> str:
    """Non-empty reason string when the prompt lacks the subagent bypass marker."""
    if BYPASS_MARKER_RE.search(prompt or ''):
        return ''
    return (
        "\U0001f6ab MISSING subagent bypass marker in the Agent prompt.\n\n"
        "Without it the spawned agent re-runs the full WF_INIT chain on its "
        "own, burning the init budget on work that should start immediately.\n\n"
        "Add one of these to the prompt: \"You are a subagent. BYPASS WF_INIT.\" "
        "(standard) or an explicit swarm-agent role assignment."
    )


def opus_on_routine_reason(model: str, prompt: str) -> str:
    """Non-empty reason string when opus is requested for routine work."""
    if (model or '').strip().lower() != 'opus':
        return ''
    if OPUS_JUSTIFIED_RE.search(prompt or ''):
        return ''
    if not ROUTINE_KEYWORDS_RE.search(prompt or ''):
        return ''
    if DESIGN_KEYWORDS_RE.search(prompt or ''):
        return ''
    return (
        "⚡ model: \"opus\" requested for what reads as ROUTINE work "
        "(tests/lint/grep/inventory/read-only audit).\n\n"
        "Opus is reserved for novel architecture/design — this task pattern "
        "is a haiku (mechanical) or sonnet (implementation/verification) job.\n\n"
        "Switch to haiku or sonnet, OR if opus is genuinely warranted here, "
        "add the literal tag `[opus-justified: <reason>]` (or "
        "`[premium-justified: <reason>]`) to the prompt and re-call."
    )


def fable_without_justification_reason(model: str, prompt: str) -> str:
    """Non-empty reason string when a fable-family model is requested without
    justification. Unlike opus_on_routine_reason (routine-keyword-gated),
    this denies ANY fable call unconditionally — fable is premium-tier
    alongside opus, and the orchestrator itself already runs the premium
    model, so there is no routine-vs-design distinction to make: delegating
    TO a premium subagent defeats the entire purpose of delegation."""
    if not _is_premium_model(model, 'fable'):
        return ''
    if FABLE_JUSTIFIED_RE.search(prompt or ''):
        return ''
    return (
        "\U0001f4b8 model: \"fable\" (PREMIUM tier) requested for a subagent — "
        "the orchestrator already runs the premium model — delegation exists "
        "to move work OFF it; use haiku (routine) or sonnet (implementation), "
        "or justify with [fable-justified: <reason>].\n\n"
        "Add `[fable-justified: <reason>]` or `[premium-justified: <reason>]` "
        "to the prompt only if fable is genuinely required here, then re-call."
    )


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        tool_name = get_input_field(input_data, 'tool_name', default='')

        if not _is_agent_tool(tool_name):
            output_empty()
            return

        tool_input = input_data.get('tool_input', {}) or {}
        prompt = str(tool_input.get('prompt') or '')
        model = str(tool_input.get('model') or '')

        reason = missing_model_reason(tool_input)
        if reason:
            output_block(reason)
            return

        reason = missing_bypass_marker_reason(prompt)
        if reason:
            output_block(reason)
            return

        reason = opus_on_routine_reason(model, prompt)
        if reason:
            output_block(reason)
            return

        reason = fable_without_justification_reason(model, prompt)
        if reason:
            output_block(reason)
            return

        output_empty()

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                         "additionalContext": f"Agent model gate error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
