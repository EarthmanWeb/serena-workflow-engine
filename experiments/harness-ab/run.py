#!/usr/bin/env python3
"""Harness A/B experiment runner.

Compares a headless Claude Code agent on one fixed coding task under three
arms: baseline (SWE plugin @ 23ec65d), v5 (SWE plugin @ harness-v5-prototype),
control (no plugin).

Pure/testable pieces (no I/O, no subprocess) are kept as free functions so
tests/test_harness_ab.py can exercise them directly:
    parse_transcript, parse_unittest_output, clean_env, build_command,
    shuffled_arm_order, count_stream_events.

Everything else (arm prep via git clone, subprocess invocation of `claude`,
filesystem copying) is orchestration and lives in functions prefixed with
do_ / cmd_ or in main().
"""
import argparse
import glob
import hashlib
import importlib.util
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_sibling(name, filename):
    """Load a sibling module by path (harness-ab is a hyphenated directory
    name, so a plain `import acceptance` only works when HERE happens to be
    on sys.path with no naming collision — load by path explicitly instead,
    matching tests/test_harness_ab.py's own loading strategy for run.py
    itself)."""
    path = os.path.join(HERE, filename)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


acceptance_module = _load_sibling("harness_ab_acceptance", "acceptance.py")
gate_conformance = _load_sibling("harness_ab_gate_conformance", "gate_conformance.py")
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
ARMS_JSON = os.path.join(HERE, "arms.json")
TASKS_DIR = os.path.join(HERE, "tasks")
DEFAULT_TASK = "v2"
WORK_ROOT = os.path.join(HERE, ".work")
ARMS_WORK_DIR = os.path.join(WORK_ROOT, "arms")
DEFAULT_OUT = os.path.join(HERE, "results")


def task_paths(task_name):
    """Return the dict of on-disk paths for one task variant under
    tasks/<task_name>/: fixture/, overlays/<name>/, hidden_tests/,
    reference_solution/, task.md, and an optional doc_rules.json.

    New contract (v2+): hidden_tests/ contains test_spec_*.py and
    test_doc_*.py files. v1 (legacy, moved from the old flat layout) uses
    test_acceptance_*.py and has no doc_rules.json. Both shapes are read the
    same way by run.py/acceptance.py — the categorizer just buckets
    test_acceptance_* as "other".

    `overlay_swe` is kept for backward compat with any external caller that
    imported it directly; `overlays_dir` is the new generic base (see
    overlay_dir_for()) used for per-arm overlays (arms.json's "overlay"
    field).

    Two-phase (pivot) tasks additionally ship tasks/<task>/pivot/: a second
    prompt (pivot/prompt.md, text starting "New task:"), its own hidden
    tests (pivot/hidden_tests/, test_pivot_spec_*.py / test_pivot_doc_*.py),
    a reference-solution overlay applied on top of task1's reference
    (pivot/reference_solution/), and an optional pivot/doc_rules.json (same
    schema as the task-level one). A task with no pivot/ directory on disk
    runs single-phase exactly as before — see has_pivot()."""
    task_dir = os.path.join(TASKS_DIR, task_name)
    pivot_dir = os.path.join(task_dir, "pivot")
    return {
        "dir": task_dir,
        "fixture": os.path.join(task_dir, "fixture"),
        "overlays_dir": os.path.join(task_dir, "overlays"),
        "overlay_swe": os.path.join(task_dir, "overlays", "swe"),
        "hidden_tests": os.path.join(task_dir, "hidden_tests"),
        "reference_solution": os.path.join(task_dir, "reference_solution"),
        "task_md": os.path.join(task_dir, "task.md"),
        "doc_rules": os.path.join(task_dir, "doc_rules.json"),
        "pivot_dir": pivot_dir,
        "pivot_prompt": os.path.join(pivot_dir, "prompt.md"),
        "pivot_hidden_tests": os.path.join(pivot_dir, "hidden_tests"),
        "pivot_reference_solution": os.path.join(pivot_dir, "reference_solution"),
        "pivot_doc_rules": os.path.join(pivot_dir, "doc_rules.json"),
    }


def has_pivot(paths):
    """True iff this task ships a pivot/ phase (pivot/prompt.md exists on
    disk). Pure filesystem check, no parsing. A task without it runs
    single-phase; callers branch on this before doing any pivot-specific
    work (benchmark 1/2, --resume, phase windowing, ...)."""
    return os.path.isfile(paths.get("pivot_prompt") or "")


def read_pivot_task_text(paths):
    """Read tasks/<task>/pivot/prompt.md text. Raises SystemExit if absent
    -- callers must guard with has_pivot() first; this is only reached once
    a pivot run has already committed to phase 2."""
    pivot_prompt = paths["pivot_prompt"]
    if not os.path.exists(pivot_prompt):
        raise SystemExit(f"missing {pivot_prompt} (pivot phase not ready)")
    with open(pivot_prompt) as f:
        return f.read()


def overlay_dir_for(paths, overlay_name):
    """Path to tasks/<task>/overlays/<overlay_name>/, or None if
    overlay_name is falsy."""
    if not overlay_name:
        return None
    return os.path.join(paths["overlays_dir"], overlay_name)


# Module-level defaults, kept for backward compat with any external caller
# that imported these names directly (e.g. tests) and for --dry-run/
# --selftest before an explicit --task is known; cmd_* functions re-resolve
# via task_paths(args.task) so a non-default --task is always honored.
FIXTURE_DIR = task_paths(DEFAULT_TASK)["fixture"]
OVERLAY_SWE_DIR = task_paths(DEFAULT_TASK)["overlay_swe"]
HIDDEN_TESTS_DIR = task_paths(DEFAULT_TASK)["hidden_tests"]
REFERENCE_SOLUTION_DIR = task_paths(DEFAULT_TASK)["reference_solution"]
TASK_MD = task_paths(DEFAULT_TASK)["task_md"]

HOOK_DENIAL_RE = re.compile(
    r"hook error|PreToolUse|BLOCKED|permissionDecision|denied by hook|\U0001F6D1|\U0001F6AB",
    re.IGNORECASE,
)
STOP_HOOK_RE = re.compile(r"Stop hook", re.IGNORECASE)

# Serena memory-consultation tool names (exact match on tool_use `name`).
MEMORY_TOOL_NAMES = frozenset({
    "mcp__plugin_swe_serena__read_memory",
    "mcp__plugin_swe_serena__list_memories",
    "mcp__plugin_swe_serena__search_memories_by_name",
    "mcp__plugin_swe_serena__search_memories_by_front_matter",
})
MEMORY_PATH_RE = re.compile(r"\.serena/memory")


# --------------------------------------------------------------------------
# Pure functions (unit tested)
# --------------------------------------------------------------------------

def parse_unittest_output(text):
    """Parse the tail of `python -m unittest` output.

    Returns {"total": int, "passed": int, "failures": int, "errors": int,
             "skipped": int, "ok": bool} best-effort; missing/unparseable
    fields default to 0 / False. Handles: "Ran N tests", "OK", "OK (skipped=K)",
    "FAILED (failures=A)", "FAILED (errors=B)", "FAILED (failures=A, errors=B)",
    and the no-tests-ran case.
    """
    result = {"total": 0, "passed": 0, "failures": 0, "errors": 0,
              "skipped": 0, "ok": False}
    if not text:
        return result

    m = re.search(r"Ran (\d+) tests?", text)
    if m:
        result["total"] = int(m.group(1))

    ok_m = re.search(r"^OK(\s*\(([^)]*)\))?\s*$", text, re.MULTILINE)
    failed_m = re.search(r"^FAILED\s*\(([^)]*)\)\s*$", text, re.MULTILINE)

    def _extract(pattern, blob):
        mm = re.search(pattern, blob)
        return int(mm.group(1)) if mm else 0

    if ok_m:
        result["ok"] = True
        extras = ok_m.group(2) or ""
        result["skipped"] = _extract(r"skipped=(\d+)", extras)
        result["failures"] = 0
        result["errors"] = 0
    elif failed_m:
        result["ok"] = False
        extras = failed_m.group(1)
        result["failures"] = _extract(r"failures=(\d+)", extras)
        result["errors"] = _extract(r"errors=(\d+)", extras)
        result["skipped"] = _extract(r"skipped=(\d+)", extras)
    # else: neither OK nor FAILED line found (e.g. "Ran 0 tests" with no
    # trailing status, or output truncated) -> ok stays False, counts 0.

    result["passed"] = max(0, result["total"] - result["failures"] - result["errors"] - result["skipped"])
    return result


def parse_transcript(lines):
    """Parse stream-json lines from a `claude -p --output-format stream-json`
    transcript into a metrics dict. Robust to missing/malformed lines.

    `lines` is an iterable of raw JSON-text lines (already split, no
    trailing newline required).

    Token/cost accounting (see experiments/harness-ab tests for real-shape
    fixtures pulled from results/20260929-123133):

    - `usage` / `main_tokens`: the top-level `result` event's `usage` block.
      This is the MAIN AGENT ONLY — it does not include tokens spent inside
      subagents launched via the Agent/Task tool.
    - `model_usage`: the `result` event's `modelUsage` dict, verbatim
      (camelCase per-model dict, keyed by model id, each value carrying
      inputTokens/outputTokens/cacheReadInputTokens/cacheCreationInputTokens/
      costUSD/...). This total is AUTHORITATIVE and includes subagents,
      because Claude Code attributes every model call (main agent or
      delegated subagent) into the same per-model rollup.
    - `all_model_tokens`: sum over `model_usage` of the four token fields
      (inputTokens + outputTokens + cacheReadInputTokens +
      cacheCreationInputTokens) across every model. This is what
      `total_tokens` is set to (see below) — on runs with no subagent
      delegation, all_model_tokens == main_tokens (mod the camelCase/
      snake_case field pairing); on runs that delegate, all_model_tokens is
      the larger, correct total, since a low num_turns count on the MAIN
      transcript can hide a lot of subagent token spend (e.g. a 8-turn run
      that fanned out into several Agent-tool subagents can cost more than a
      60-turn run with no delegation at all).
    - `total_tokens` = `all_model_tokens` (falls back to `main_tokens` when
      the `result` event has no modelUsage, e.g. an errored/truncated run) —
      this is a deliberate change from the old behavior of summing only the
      main-agent `usage` block, which silently under-counted every
      subagent-delegating run.
    - `subagent_launches`: count of Agent/Task tool_use blocks emitted by the
      MAIN agent (i.e. how many subagents were kicked off).
    - `subagent_messages`: count of assistant/user stream-json events whose
      top-level `parent_tool_use_id` is non-null, i.e. events that belong to
      a subagent's own turn sequence rather than the main agent's.
    - `assistant_turns_incl_subagents`: total assistant-message events,
      main agent + every subagent combined (assistant_message_count is now
      main-agent-only; this new field is the previous ambiguous total).
    """
    metrics = {
        "subtype": None,
        "is_error": None,
        "num_turns": None,
        "duration_ms": None,
        "duration_api_ms": None,
        "est_cost_usd": None,
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
        "main_tokens": 0,
        "model_usage": {},
        "all_model_tokens": 0,
        "total_tokens": 0,
        "distinct_models_used": 0,
        "assistant_message_count": 0,
        "assistant_turns_incl_subagents": 0,
        "tool_calls_by_name": {},
        "total_tool_calls": 0,
        "memory_file_reads": 0,
        "subagent_launches": 0,
        "subagent_messages": 0,
        "tool_result_errors": 0,
        "hook_denials": 0,
        "stop_hook_blocks": 0,
        "mcp_servers": [],
        "plugins": [],
    }

    for raw in lines:
        raw = raw.strip() if isinstance(raw, str) else raw
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue

        etype = event.get("type")
        is_subagent_event = event.get("parent_tool_use_id") is not None

        if etype == "system" and event.get("subtype") == "init":
            servers = event.get("mcp_servers") or event.get("mcpServers") or []
            plugins = event.get("plugins") or []
            metrics["mcp_servers"] = servers
            metrics["plugins"] = plugins

        elif etype == "assistant":
            metrics["assistant_turns_incl_subagents"] += 1
            if is_subagent_event:
                metrics["subagent_messages"] += 1
            else:
                metrics["assistant_message_count"] += 1
            message = event.get("message") or {}
            content = message.get("content") or []
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use":
                        name = block.get("name") or "unknown"
                        metrics["tool_calls_by_name"][name] = (
                            metrics["tool_calls_by_name"].get(name, 0) + 1
                        )
                        metrics["total_tool_calls"] += 1
                        if name in MEMORY_TOOL_NAMES:
                            metrics["memory_file_reads"] += 1
                        elif name == "Read":
                            tool_input = block.get("input") or {}
                            if isinstance(tool_input, dict):
                                path = tool_input.get("file_path") or tool_input.get("path") or ""
                                if isinstance(path, str) and MEMORY_PATH_RE.search(path):
                                    metrics["memory_file_reads"] += 1
                        if name in ("Agent", "Task") and not is_subagent_event:
                            # Only the main agent's own Agent/Task tool_use
                            # blocks count as a "launch" — a subagent that
                            # itself launches a nested subagent is real, but
                            # top-level fan-out is what we want to compare
                            # across arms.
                            metrics["subagent_launches"] += 1

        elif etype == "user":
            if is_subagent_event:
                metrics["subagent_messages"] += 1
            message = event.get("message") or {}
            content = message.get("content") or []
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_result" and block.get("is_error"):
                        metrics["tool_result_errors"] += 1
                        text = _tool_result_text(block)
                        if HOOK_DENIAL_RE.search(text or ""):
                            metrics["hook_denials"] += 1
                    if block.get("type") == "text":
                        text = block.get("text") or ""
                        if STOP_HOOK_RE.search(text):
                            metrics["stop_hook_blocks"] += 1

        elif etype == "result":
            metrics["subtype"] = event.get("subtype")
            metrics["is_error"] = event.get("is_error")
            metrics["num_turns"] = event.get("num_turns")
            metrics["duration_ms"] = event.get("duration_ms")
            metrics["duration_api_ms"] = event.get("duration_api_ms")
            # `total_cost_usd` in the stream-json result event is Claude
            # Code's notional cost estimate, not an actual charge (the user
            # runs on a claude.ai Max subscription, not API billing) — kept
            # under `est_cost_usd` throughout runs.jsonl / analyze output.
            metrics["est_cost_usd"] = event.get("total_cost_usd")
            usage = event.get("usage") or {}
            for key in metrics["usage"]:
                val = usage.get(key)
                if isinstance(val, (int, float)):
                    metrics["usage"][key] = val

            model_usage = event.get("modelUsage") or event.get("model_usage") or {}
            if isinstance(model_usage, dict):
                metrics["model_usage"] = model_usage
                metrics["distinct_models_used"] = len(model_usage)

    metrics["main_tokens"] = sum(metrics["usage"].values())

    all_model_tokens = 0
    for _model_name, mu in metrics["model_usage"].items():
        if not isinstance(mu, dict):
            continue
        for field in ("inputTokens", "outputTokens", "cacheReadInputTokens",
                       "cacheCreationInputTokens"):
            val = mu.get(field)
            if isinstance(val, (int, float)):
                all_model_tokens += val
    metrics["all_model_tokens"] = all_model_tokens

    # total_tokens = all_model_tokens (the authoritative total, including
    # subagent spend) when a modelUsage breakdown was present; fall back to
    # the main-agent-only usage sum for a run whose result event lacked
    # modelUsage entirely (e.g. errored before completion).
    metrics["total_tokens"] = all_model_tokens if metrics["model_usage"] else metrics["main_tokens"]

    return metrics


def _parse_transcript_events(lines):
    """Parse raw stream-json transcript lines into a list of event dicts
    (skipping malformed lines), for gate_conformance's transcript-walking
    functions. Pure. Distinct from parse_transcript(), which reduces the
    same lines to a metrics dict instead of preserving the event list."""
    events = []
    for raw in lines:
        raw = raw.strip() if isinstance(raw, str) else raw
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _tool_result_text(block):
    """Extract text from a tool_result content block (string or block list)."""
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                parts.append(c.get("text") or "")
            elif isinstance(c, str):
                parts.append(c)
        return "\n".join(parts)
    return ""


def clean_env(source_env):
    """Return a copy of source_env with CLAUDE*/SWE_* keys removed (except
    CLAUDE_CONFIG_DIR), MCP_TIMEOUT set, and every ANTHROPIC_* key dropped.

    The user runs these experiments on a claude.ai Max subscription, never
    API billing. ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN / ANTHROPIC_BASE_URL
    (and any other ANTHROPIC_* var, e.g. ANTHROPIC_MODEL — the model is
    passed explicitly via --model) are stripped unconditionally so a stray
    key in the ambient environment can never switch the child process to API
    billing. CLAUDE_CODE_USE_BEDROCK / CLAUDE_CODE_USE_VERTEX are already
    covered by the CLAUDE prefix strip; AWS_BEARER_TOKEN_BEDROCK is stripped
    explicitly since it doesn't share either prefix.
    """
    env = {}
    for key, val in source_env.items():
        if key == "CLAUDE_CONFIG_DIR":
            env[key] = val
            continue
        if key.startswith("CLAUDE") or key.startswith("SWE_"):
            continue
        if key.startswith("ANTHROPIC_"):
            continue
        if key == "AWS_BEARER_TOKEN_BEDROCK":
            continue
        env[key] = val
    env["MCP_TIMEOUT"] = "300000"
    return env


def parse_auth_status(stdout_text):
    """Parse `claude auth status` JSON stdout into a normalized dict.

    Returns {"loggedIn": bool|None, "authMethod": str|None,
             "apiProvider": str|None, "subscriptionType": str|None,
             "ok": bool, "reason": str|None}.

    `ok` is True only when loggedIn is True and authMethod == "claude.ai"
    (i.e. subscription auth, not a raw API key). Never raises: unparseable
    input yields ok=False with a reason.
    """
    result = {"loggedIn": None, "authMethod": None, "apiProvider": None,
              "subscriptionType": None, "ok": False, "reason": None}
    if not stdout_text or not stdout_text.strip():
        result["reason"] = "empty output"
        return result
    try:
        data = json.loads(stdout_text)
    except (ValueError, TypeError):
        result["reason"] = "unparseable JSON"
        return result
    if not isinstance(data, dict):
        result["reason"] = "unexpected JSON shape"
        return result

    result["loggedIn"] = data.get("loggedIn")
    result["authMethod"] = data.get("authMethod")
    result["apiProvider"] = data.get("apiProvider")
    result["subscriptionType"] = data.get("subscriptionType")

    if result["loggedIn"] is not True:
        result["reason"] = "not logged in"
        return result
    if result["authMethod"] != "claude.ai":
        result["reason"] = f"authMethod is {result['authMethod']!r}, expected 'claude.ai' (subscription)"
        return result

    result["ok"] = True
    return result


def validate_billing_args(allow_api_billing, budget_usd, total_budget_usd):
    """Validate the billing/budget CLI args. Pure, no I/O.

    Returns a list of error message strings (empty list = valid). When
    allow_api_billing is True, both --budget-usd (> 0) and --total-budget-usd
    (> 0) are mandatory: API billing has no flat-rate ceiling, so a per-run
    cap alone can't bound total spend across an experiment. When
    allow_api_billing is False, both remain optional (subscription billing
    has no dollar figure to enforce); any caller-supplied values are left
    alone here (callers may still pass an optional per-run --budget-usd on
    subscription auth as a runaway-turn guard, unrelated to dollars).
    """
    errors = []
    if not allow_api_billing:
        return errors
    if budget_usd is None or budget_usd <= 0:
        errors.append(
            "--allow-api-billing requires --budget-usd > 0 (a mandatory "
            "per-run spend cap passed as --max-budget-usd to every "
            "`claude -p` call)."
        )
    if total_budget_usd is None or total_budget_usd <= 0:
        errors.append(
            "--allow-api-billing requires --total-budget-usd > 0 (a "
            "mandatory cumulative spend cap across the whole experiment)."
        )
    return errors


def budget_allows_next(spent, per_run_cap, total_cap):
    """Scheduling helper: may the next run start, given cumulative spend so
    far? Pure, no I/O.

    Returns True when there is no total cap to enforce (total_cap is None)
    — the caller is expected to only enforce this when API billing was
    explicitly allowed with both caps validated. Otherwise returns True iff
    spent + per_run_cap <= total_cap, i.e. starting one more run at its
    worst case (spending the full per-run cap) cannot push cumulative spend
    past the total cap. per_run_cap is treated as 0 when None (no known
    per-run ceiling to project forward).
    """
    if total_cap is None:
        return True
    cap = per_run_cap if per_run_cap is not None else 0
    return (spent + cap) <= total_cap


def check_auth(env, allow_api_billing=False):
    """Run `claude auth status` with the given (already-cleaned) env and
    enforce subscription auth unless allow_api_billing is set.

    Returns the parsed status dict (see parse_auth_status). Raises
    SystemExit with a clear message when the check fails and
    allow_api_billing is False.
    """
    result = subprocess.run(["claude", "auth", "status"], env=env,
                             capture_output=True, text=True)
    status = parse_auth_status(result.stdout)
    if not status["ok"] and not allow_api_billing:
        raise SystemExit(
            "auth check failed: expected a logged-in claude.ai (subscription) "
            f"session, got loggedIn={status['loggedIn']!r} "
            f"authMethod={status['authMethod']!r} ({status['reason']}).\n"
            "This harness is meant to run on a Max subscription, not API "
            "billing. Pass --allow-api-billing to override.\n"
            f"raw stdout: {result.stdout.strip()!r}\n"
            f"raw stderr: {result.stderr.strip()!r}"
        )
    return status


def build_command(task_text, model, budget_usd, plugin_dir=None, effort=None,
                   session_id=None, resume=None):
    """Build the `claude -p ...` argv list (no shell).

    budget_usd is optional (None by default at the CLI level): when None,
    no --max-budget-usd flag is passed at all — cost figures are notional
    estimates on a subscription, not a spend cap that needs enforcing. Pass
    a number to add an optional runaway-cost guard.

    session_id / resume implement the two-phase (pivot) run: at most one of
    the two may be given (both is a caller bug -- see below).

    - session_id: pass `--session-id <uuid>` for a run that must be
      resumable later (the task1 phase of a pivot run). This also DROPS
      `--no-session-persistence` (session persistence must stay on for
      `--resume` to work on the same chat session later) -- every other flag
      (stream-json, --verbose, --model, --setting-sources, --dangerously-
      skip-permissions, budget/plugin/effort) is unchanged.
    - resume: pass `-r/--resume <value>` to continue a previously-persisted
      session (the pivot phase). Also drops `--no-session-persistence` for
      the same reason (the CLI flag only works with --print, and a run that
      resumes was already, by construction, persisted in phase 1).
    - Neither given (the default): identical to the single-phase command
      (session-persistence stays disabled), i.e. 100% backward compatible
      with every existing single-phase call site.
    """
    assert not (session_id and resume), (
        "build_command: session_id and resume are mutually exclusive "
        "(session_id starts a resumable session, resume continues one)"
    )
    cmd = [
        "claude", "-p", task_text,
        "--output-format", "stream-json",
        "--verbose",
        "--model", model,
        "--setting-sources", "project,local",
        "--dangerously-skip-permissions",
    ]
    if session_id:
        cmd += ["--session-id", str(session_id)]
    elif resume:
        cmd += ["--resume", str(resume)]
    else:
        cmd += ["--no-session-persistence"]
    if budget_usd is not None:
        cmd += ["--max-budget-usd", str(budget_usd)]
    if plugin_dir:
        cmd += ["--plugin-dir", plugin_dir]
    if effort:
        cmd += ["--effort", str(effort)]
    return cmd


def shuffled_arm_order(arm_names, trials, seed):
    """Deterministic per-trial shuffled arm order.

    Returns a list of length `trials`, each element a list of arm names
    (a permutation of arm_names) — same seed + inputs always reproduces the
    same interleaving.
    """
    rng = random.Random(seed)
    order = []
    for _ in range(trials):
        arms = list(arm_names)
        rng.shuffle(arms)
        order.append(arms)
    return order


def count_stream_events(lines):
    """Count SWE .serena/streams/*.jsonl events by their `type` field."""
    counts = {}
    for raw in lines:
        raw = raw.strip() if isinstance(raw, str) else raw
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        etype = event.get("type") or "unknown"
        counts[etype] = counts.get(etype, 0) + 1
    return counts


def median(values):
    values = sorted(v for v in values if v is not None)
    n = len(values)
    if n == 0:
        return None
    mid = n // 2
    if n % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def load_arms():
    with open(ARMS_JSON) as f:
        return json.load(f)


def read_task_text(paths=None):
    paths = paths or task_paths(DEFAULT_TASK)
    task_md = paths["task_md"]
    if not os.path.exists(task_md):
        raise SystemExit(f"missing {task_md} (task variant not ready)")
    with open(task_md) as f:
        return f.read()


def _run(cmd, cwd=None, check=True):
    print("+ " + " ".join(cmd), file=sys.stderr)
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def prepare_arm(arm, force=False):
    """Prepare a plugin arm's working clone. Returns dict with dir, sha, version."""
    name = arm["name"]
    ref = arm["ref"]
    arm_dir = os.path.join(ARMS_WORK_DIR, name)

    need_clone = force or not os.path.isdir(arm_dir)
    if not need_clone:
        # Re-use if .git is a directory and HEAD matches resolved ref.
        git_path = os.path.join(arm_dir, ".git")
        if not os.path.isdir(git_path):
            need_clone = True
        else:
            try:
                current = _run(["git", "-C", arm_dir, "rev-parse", "HEAD"]).stdout.strip()
                resolved = _run(["git", "-C", REPO_ROOT, "rev-parse", ref]).stdout.strip()
                if current != resolved:
                    need_clone = True
            except Exception:
                need_clone = True

    if need_clone:
        if os.path.isdir(arm_dir):
            shutil.rmtree(arm_dir)
        os.makedirs(os.path.dirname(arm_dir), exist_ok=True)
        # Resolve the ref to a concrete commit SHA in the SOURCE repo first.
        # `git clone` only creates a local branch for the default branch;
        # other branches land solely as remote-tracking refs
        # (origin/<branch>), so checking out the bare ref name in the clone
        # can fail even though the commit itself was fetched. A SHA always
        # resolves regardless of branch-name plumbing.
        resolved_sha = _run(["git", "-C", REPO_ROOT, "rev-parse", ref]).stdout.strip()
        _run(["git", "clone", "--no-hardlinks", REPO_ROOT, arm_dir])
        _run(["git", "-C", arm_dir, "checkout", "-q", "-B", f"exp-{name}", resolved_sha])
        _run(["git", "-C", arm_dir, "remote", "remove", "origin"])

    assert os.path.isdir(os.path.join(arm_dir, ".git")), (
        f"{arm_dir}/.git must be a directory (full clone), not a worktree gitfile"
    )

    sha = _run(["git", "-C", arm_dir, "rev-parse", "HEAD"]).stdout.strip()
    version = None
    plugin_json = os.path.join(arm_dir, ".claude-plugin", "plugin.json")
    if os.path.exists(plugin_json):
        with open(plugin_json) as f:
            version = json.load(f).get("version")

    return {"dir": arm_dir, "sha": sha, "version": version}


def prepare_all_arms(arms, force=False):
    prepared = {}
    for arm in arms:
        if arm.get("plugin"):
            prepared[arm["name"]] = prepare_arm(arm, force=force)
        else:
            prepared[arm["name"]] = {"dir": None, "sha": None, "version": None}
    return prepared


def resolve_overlay(arm, paths):
    """Resolve which overlay (if any) applies to `arm` for this task, and
    whether it actually exists on disk. Pure (no filesystem writes).

    Returns {"overlay": name|None, "overlay_dir": path|None,
             "overlay_applied": bool, "warning": str|None}.

    Back-compat: an arm dict with no "overlay" key falls back to
    plugin-gated behavior — plugin arms use overlays/swe/ if present on
    disk, non-plugin arms get no overlay — so an arms.json (or a
    caller-constructed arm dict) that omits "overlay" entirely keeps
    working unchanged."""
    overlay_name = arm.get("overlay")
    if overlay_name is None:
        # Legacy fallback: only plugin arms got the swe overlay before
        # per-arm overlays existed.
        overlay_name = "swe" if arm.get("plugin") else None

    if not overlay_name:
        return {"overlay": None, "overlay_dir": None,
                "overlay_applied": False, "warning": None}

    overlay_dir = overlay_dir_for(paths, overlay_name)
    exists = bool(overlay_dir and os.path.isdir(overlay_dir))
    warning = None
    if not exists:
        warning = (f"overlay {overlay_name!r} not found at {overlay_dir} "
                    f"for task {paths.get('dir')!r} — proceeding without it")
    return {"overlay": overlay_name, "overlay_dir": overlay_dir if exists else overlay_dir,
            "overlay_applied": exists, "warning": warning}


def make_run_workdir(run_dir, arm, paths=None):
    """Copy the fixture into run_dir/work/, apply the arm's resolved overlay
    (see resolve_overlay) if it exists on disk, and commit as the run's
    starting point.

    Returns (work_dir, overlay_info) — overlay_info is resolve_overlay()'s
    dict, so callers can record overlay/overlay_applied/warnings per run
    without re-deriving them."""
    paths = paths or task_paths(DEFAULT_TASK)
    work_dir = os.path.join(run_dir, "work")
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    shutil.copytree(paths["fixture"], work_dir)

    overlay_info = resolve_overlay(arm, paths)
    if overlay_info["warning"]:
        print(f"warning: {overlay_info['warning']}", file=sys.stderr)
    if overlay_info["overlay_applied"]:
        _copy_overlay(overlay_info["overlay_dir"], work_dir)

    _run(["git", "init", "-q"], cwd=work_dir)
    _run(["git", "-c", "user.name=harness-ab", "-c", "user.email=harness-ab@localhost",
          "add", "-A"], cwd=work_dir)
    _run(["git", "-c", "user.name=harness-ab", "-c", "user.email=harness-ab@localhost",
          "commit", "-qm", "fixture"], cwd=work_dir)
    return work_dir, overlay_info


def _copy_overlay(src, dst):
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        target_dir = os.path.join(dst, rel) if rel != "." else dst
        os.makedirs(target_dir, exist_ok=True)
        for fname in files:
            shutil.copy2(os.path.join(root, fname), os.path.join(target_dir, fname))


def sha256_of_claude_md(work_dir):
    """sha256 hex digest of work_dir/CLAUDE.md, or None if it doesn't
    exist. Used to prove (in each runs.jsonl row) exactly what CLAUDE.md
    content an arm's agent saw, independent of which overlay produced it."""
    claude_md = os.path.join(work_dir, "CLAUDE.md")
    if not os.path.isfile(claude_md):
        return None
    h = hashlib.sha256()
    with open(claude_md, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def read_effective_claude_md(work_dir):
    """Read work_dir/CLAUDE.md text, or "" if it doesn't exist."""
    claude_md = os.path.join(work_dir, "CLAUDE.md")
    if not os.path.isfile(claude_md):
        return ""
    with open(claude_md, encoding="utf-8", errors="replace") as f:
        return f.read()


# Literal markers proving the SWE enforcement prefix (scripts/CLAUDE_PREFIX.md,
# injected into overlays/swe/CLAUDE.md) is present in a plugin arm's
# effective CLAUDE.md.
SWE_PREFIX_MARKERS = ("MANDATORY ENTRY POINT", "wf/WF_INIT")

# Harness-leak terms that must NOT appear in the control arm's effective
# CLAUDE.md (case-insensitive), except inside the one allowed doc-location
# line, which is the only place ".serena/memory" may legitimately appear
# (the other agent's overlays/control/CLAUDE.md adds a single line naming
# where docs live, for the "doc" acceptance-test category to be fair).
CONTROL_LEAK_TERMS = ("swe", "wf_", "workflow engine", "harness",
                       "read_memory", "mcp__", "serena")
CONTROL_ALLOWED_DOC_LINE_RE = re.compile(r"\.serena/memory", re.IGNORECASE)


def validate_claude_md(arm_name, plugin, text):
    """Pure validation of one arm's effective CLAUDE.md content. Returns a
    list of error message strings (empty = valid).

    - plugin arms (baseline, v5): must contain the SWE enforcement prefix
      (see SWE_PREFIX_MARKERS) — a plugin arm whose overlay failed to apply,
      or whose CLAUDE.md was silently stripped, would otherwise run with no
      init-gate instructions and invalidate the comparison.
    - control arm: must contain NONE of CONTROL_LEAK_TERMS (case-insensitive),
      checked line by line, except the single line that matches
      CONTROL_ALLOWED_DOC_LINE_RE (".serena/memory") — the one sanctioned
      doc-location line the control overlay is allowed to add. Any other
      line containing a leak term, OR more than one line matching the
      allowed-doc-line pattern, is an error.
    """
    errors = []
    text = text or ""

    if plugin:
        for marker in SWE_PREFIX_MARKERS:
            if marker not in text:
                errors.append(
                    f"{arm_name}: missing SWE enforcement prefix marker "
                    f"{marker!r} in effective CLAUDE.md (overlay not applied "
                    f"or prefix stripped)")
        return errors

    # control (and any other non-plugin arm): must not leak harness
    # internals, except the single allowed doc-location line.
    lines = text.splitlines()
    allowed_doc_lines = 0
    for lineno, line in enumerate(lines, start=1):
        is_allowed_doc_line = bool(CONTROL_ALLOWED_DOC_LINE_RE.search(line))
        if is_allowed_doc_line:
            allowed_doc_lines += 1
        lower = line.lower()
        for term in CONTROL_LEAK_TERMS:
            if term in lower:
                if is_allowed_doc_line:
                    # The allowed doc-location line is permitted to mention
                    # ".serena/memory" itself, but not any OTHER leak term
                    # on that same line.
                    if term == "serena" and CONTROL_ALLOWED_DOC_LINE_RE.search(line):
                        continue
                errors.append(
                    f"{arm_name}: leaked harness term {term!r} on CLAUDE.md "
                    f"line {lineno}: {line!r}")
    if allowed_doc_lines > 1:
        errors.append(
            f"{arm_name}: more than one line ({allowed_doc_lines}) matches "
            f"the allowed doc-location pattern in CLAUDE.md — only a single "
            f"sanctioned line may mention .serena/memory")
    return errors


def run_claude(cmd, cwd, env, timeout_min, transcript_path, stderr_path):
    """Run the claude CLI, streaming stdout to transcript_path, killing the
    whole process group on timeout. Returns (returncode, timed_out, wall_s)."""
    start = time.time()
    timed_out = False
    with open(transcript_path, "w") as out_f, open(stderr_path, "w") as err_f:
        proc = subprocess.Popen(
            cmd, cwd=cwd, env=env, stdout=out_f, stderr=err_f,
            start_new_session=True,
        )
        try:
            proc.wait(timeout=timeout_min * 60)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_process_group(proc)
    wall_s = time.time() - start
    return proc.returncode, timed_out, wall_s


def _kill_process_group(proc):
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except Exception:
        pass
    try:
        proc.wait(timeout=10)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGKILL)
    except Exception:
        pass
    try:
        proc.wait(timeout=10)
    except Exception:
        pass


FAILED_TEST_LINE_RE = re.compile(r"^(?:FAIL|ERROR): (.+)$", re.MULTILINE)


def parse_failed_test_ids(text):
    """Extract short test ids from unittest's `FAIL: <id>` / `ERROR: <id>`
    summary lines. Pure. Returns a list (dedup, order-preserving) of the
    raw id text after the marker, e.g. "test_foo (tests.test_bar.MyTest)".
    Empty/no-match input returns []."""
    if not text:
        return []
    seen = []
    for m in FAILED_TEST_LINE_RE.finditer(text):
        ident = m.group(1).strip()
        if ident and ident not in seen:
            seen.append(ident)
    return seen


def run_unittest_dir(run_root, test_dir_rel, top_level, timeout_s=300, verbose=True):
    """Run `python3 -m unittest discover` and return (rc, stdout, stderr).

    verbose=True (default) adds `-v` so per-test result lines are emitted on
    stderr (unittest writes its runner output to stderr) — needed for
    acceptance.parse_verbose_unittest_output() to classify individual tests
    into spec/doc/other categories and score doc_rules.json. The trailing
    OK/FAILED summary line parse_unittest_output() relies on is unaffected
    by -v (it's still on the last non-blank line)."""
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", test_dir_rel,
           "-t", top_level, "-p", "test_*.py"]
    if verbose:
        cmd.append("-v")
    try:
        result = subprocess.run(cmd, cwd=run_root, capture_output=True, text=True,
                                 timeout=timeout_s)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as e:
        return -1, e.stdout or "", (e.stderr or "") + "\nTIMEOUT"


def _write_score_log(run_dir, filename, cmd_label, rc, out, err):
    """Best-effort write of a scoring pass's stdout+stderr to
    <run_dir>/<filename>. Never raises (run_dir may be None or not writable,
    e.g. in tests / dry-run paths that don't set up a real run dir)."""
    if not run_dir:
        return
    try:
        os.makedirs(run_dir, exist_ok=True)
        with open(os.path.join(run_dir, filename), "w") as f:
            f.write(f"exit_code: {rc}\n\n--- stdout ---\n{out}\n\n--- stderr ---\n{err}\n")
    except OSError:
        pass


def _score_expected_ids(hidden_tests_dir, module_prefix, out, err, doc_rules_path):
    """Shared expected-id scoring pass (see acceptance.scan_expected_test_ids
    / score_against_expected_ids's module docstring for the root-cause this
    fixes: a hidden test MODULE that fails to import is reported by
    unittest -v as a single `_FailedTest`/ERROR line instead of its N real
    test methods, silently shrinking "Ran N tests" and every category/
    doc_rule/retention count derived from it).

    Returns a dict of the fields score_run()/score_hidden_tests_dir() layer
    onto their acceptance dict: {"total", "passed", "spec", "doc", "other",
    "doc_rules", "by_id"} -- "total"/"passed" here OVERRIDE the
    parse_unittest_output() summary-line counts (which are exactly the
    buggy under-count for an import-failed module), computed instead from
    the static AST-scanned expected id set."""
    test_results = acceptance_module.parse_verbose_unittest_output(out + "\n" + err)
    expected_by_module = acceptance_module.scan_expected_test_ids(hidden_tests_dir, module_prefix)
    scored = acceptance_module.score_against_expected_ids(test_results, expected_by_module, module_prefix)
    categories = acceptance_module.categorize_expected_results(scored["by_id"])
    doc_rules = acceptance_module.load_doc_rules(doc_rules_path)
    doc_rule_matrix = acceptance_module.doc_rule_pass_matrix_from_expected(scored["by_id"], doc_rules)
    return {
        "total": scored["total"],
        "passed": scored["passed"],
        "spec": categories["spec"],
        "doc": categories["doc"],
        "other": categories["other"],
        "doc_rules": doc_rule_matrix,
        "by_id": scored["by_id"],
    }


def score_run(work_dir, run_dir=None, paths=None):
    """Copy hidden tests -> _acceptance/, run acceptance + regression tests.

    When run_dir is given, also persists the raw stdout/stderr of each pass
    to <run_dir>/acceptance.txt and <run_dir>/regression.txt, and populates
    acceptance["failed_tests"] / regression["failed_tests"] (short test ids
    parsed from FAIL:/ERROR: summary lines).

    acceptance also gains per-category and per-doc-rule breakdowns (see
    acceptance.py): acceptance["spec"] / acceptance["doc"] /
    acceptance["other"] = {"passed": n, "total": n}, and
    acceptance["doc_rules"] = {rule_id: {"passed", "total", "memory",
    "summary", "ok"}} when the task ships a doc_rules.json (empty dict
    otherwise). acceptance["total"]/["passed"] are computed from the
    STATIC expected-test-id set (see _score_expected_ids), not from
    unittest's own "Ran N tests" summary line -- a hidden test module that
    fails to import is scored against every one of its expected ids
    ("import_error") rather than collapsing to unittest's single opaque
    `_FailedTest` result."""
    paths = paths or task_paths(DEFAULT_TASK)
    hidden_tests_dir = paths["hidden_tests"]
    acceptance_dir = os.path.join(work_dir, "_acceptance")
    if os.path.isdir(hidden_tests_dir):
        if os.path.exists(acceptance_dir):
            shutil.rmtree(acceptance_dir)
        shutil.copytree(hidden_tests_dir, acceptance_dir)
        rc, out, err = run_unittest_dir(work_dir, "_acceptance", ".")
    else:
        rc, out, err = (-1, "", "hidden_tests/ not present")
    acceptance = parse_unittest_output(out + "\n" + err)
    acceptance["exit_code"] = rc
    acceptance["failed_tests"] = parse_failed_test_ids(out + "\n" + err)

    expected = _score_expected_ids(hidden_tests_dir, "_acceptance", out, err, paths.get("doc_rules"))
    acceptance["total"] = expected["total"]
    acceptance["passed"] = expected["passed"]
    acceptance["ok"] = expected["total"] > 0 and expected["passed"] == expected["total"]
    acceptance["spec"] = expected["spec"]
    acceptance["doc"] = expected["doc"]
    acceptance["other"] = expected["other"]
    acceptance["doc_rules"] = expected["doc_rules"]
    acceptance["by_id"] = expected["by_id"]

    _write_score_log(run_dir, "acceptance.txt", "acceptance", rc, out, err)

    reg_test_dir = os.path.join(work_dir, "tests")
    if os.path.isdir(reg_test_dir):
        rrc, rout, rerr = run_unittest_dir(work_dir, "tests", ".")
        regression = parse_unittest_output(rout + "\n" + rerr)
        regression["exit_code"] = rrc
        regression["failed_tests"] = parse_failed_test_ids(rout + "\n" + rerr)
        _write_score_log(run_dir, "regression.txt", "regression", rrc, rout, rerr)
    else:
        regression = {"total": 0, "passed": 0, "failures": 0, "errors": 0,
                      "skipped": 0, "ok": True, "exit_code": 0, "failed_tests": []}
        _write_score_log(run_dir, "regression.txt", "regression", 0, "",
                          "tests/ not present")

    return acceptance, regression


# --------------------------------------------------------------------------
# Two-phase (pivot) benchmark scoring.
#
# A pivot run scores the work tree TWICE: once after task1 (benchmark 1,
# before the pivot prompt is ever shown to the agent) and once after the
# pivot phase (benchmark 2). Both passes reuse score_run()'s acceptance-
# scoring machinery, but score_run() always scores against ONE fixed
# hidden_tests dir at a single `_acceptance/` path. score_hidden_tests_dir()
# below generalizes that to an arbitrary (source hidden_tests dir,
# destination subdir under _acceptance/) pair, so benchmark 2 can place
# pivot/hidden_tests/ and task1's hidden_tests/ side by side under
# `_acceptance/pivot/` + `_acceptance/task1/` and `-t .` discovery still
# finds both (see run_unittest_dir's `-t .` top-level arg).
# --------------------------------------------------------------------------

def score_hidden_tests_dir(work_dir, hidden_tests_dir, acceptance_subdir,
                            run_dir=None, log_name=None, doc_rules_path=None):
    """Copy `hidden_tests_dir` -> work_dir/_acceptance/<acceptance_subdir>/,
    run it, and return an acceptance dict shaped exactly like
    score_run()'s (total/passed/failures/errors/skipped/ok/exit_code/
    failed_tests/spec/doc/other/doc_rules).

    `acceptance_subdir` may be "" for the single-phase _acceptance/ root
    (score_run's own layout); a non-empty value (e.g. "pivot", "task1")
    nests under it instead, so multiple hidden_tests sets can coexist for
    one discovery pass. Pure I/O helper -- no git, no removal of
    _acceptance/ itself (callers are responsible for cleanup, see
    remove_acceptance_dir)."""
    acceptance_root = os.path.join(work_dir, "_acceptance")
    dest = os.path.join(acceptance_root, acceptance_subdir) if acceptance_subdir else acceptance_root
    if os.path.isdir(hidden_tests_dir):
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(hidden_tests_dir, dest)
        if acceptance_subdir:
            # A nested subdir (e.g. _acceptance/task1/) makes _acceptance/
            # itself a package root too -- unittest discover's `-s
            # _acceptance` requires __init__.py directly in _acceptance/,
            # not just in the nested subdir the hidden tests were copied
            # into. The single-phase score_run() layout (acceptance_subdir
            # == "") never nests, so this only applies to pivot's two-
            # subdir discovery.
            init_path = os.path.join(acceptance_root, "__init__.py")
            if not os.path.exists(init_path):
                with open(init_path, "w"):
                    pass
        rc, out, err = run_unittest_dir(work_dir, "_acceptance", ".")
    else:
        rc, out, err = (-1, "", f"{hidden_tests_dir} not present")

    acceptance = parse_unittest_output(out + "\n" + err)
    acceptance["exit_code"] = rc
    acceptance["failed_tests"] = parse_failed_test_ids(out + "\n" + err)

    # `-t .` discovery (above) runs from work_dir's top level, so when a
    # SIBLING acceptance_subdir also exists on disk at scoring time (pivot's
    # benchmark 2 scores "task1" and "pivot" back to back, both nested under
    # the same _acceptance/ root -- see run_one_pivot), `out`/`err` contain
    # BOTH subdirs' test result lines intermixed, not just this call's own.
    # module_prefix scopes scan_expected_test_ids/score_against_expected_ids
    # to exactly "_acceptance.<this acceptance_subdir>.*" so a sibling
    # subdir's tests are never counted into THIS acceptance dict's
    # total/passed/spec/doc/doc_rules.
    module_prefix = f"_acceptance.{acceptance_subdir}" if acceptance_subdir else "_acceptance"
    expected = _score_expected_ids(hidden_tests_dir, module_prefix, out, err, doc_rules_path)
    acceptance["total"] = expected["total"]
    acceptance["passed"] = expected["passed"]
    acceptance["ok"] = expected["total"] > 0 and expected["passed"] == expected["total"]
    acceptance["spec"] = expected["spec"]
    acceptance["doc"] = expected["doc"]
    acceptance["other"] = expected["other"]
    acceptance["doc_rules"] = expected["doc_rules"]
    acceptance["by_id"] = expected["by_id"]

    if log_name:
        _write_score_log(run_dir, log_name, log_name, rc, out, err)
    return acceptance


def remove_acceptance_dir(work_dir):
    """Remove work_dir/_acceptance/ entirely (best-effort). Called after
    each benchmark scoring pass so the agent never sees hidden tests on
    disk in the NEXT phase (task1's _acceptance/ must be gone before the
    pivot prompt runs, and benchmark 2's before any further phase, if one
    is ever added)."""
    acceptance_dir = os.path.join(work_dir, "_acceptance")
    if os.path.isdir(acceptance_dir):
        shutil.rmtree(acceptance_dir)


def git_commit_snapshot(work_dir, message, run=None):
    """Snapshot the work tree with `git add -A && git commit` under a fixed
    harness identity (matching make_run_workdir's own commits), and return
    the resulting commit sha. `run` defaults to the module's own _run()
    helper; overridable for tests that want to avoid a real git repo.
    Raises (via _run's check=True default) if either git command fails --
    a snapshot that silently didn't happen would corrupt every downstream
    benchmark/regression comparison."""
    run = run or _run
    run(["git", "-c", "user.name=harness-ab", "-c", "user.email=harness-ab@localhost",
         "add", "-A"], cwd=work_dir)
    run(["git", "-c", "user.name=harness-ab", "-c", "user.email=harness-ab@localhost",
         "commit", "-qm", message, "--allow-empty"], cwd=work_dir)
    result = run(["git", "rev-parse", "HEAD"], cwd=work_dir)
    return result.stdout.strip()


def _strip_module_prefix(expected_id, module_prefix):
    """Strip a score_against_expected_ids() `by_id` key's leading
    module_prefix ("_acceptance" or "_acceptance.<subdir>") so ids scored
    under two different acceptance_subdir prefixes (e.g. task1's hidden
    tests scored at B1 under "" and again at B2 under "task1", see
    run_one_pivot) can be compared as the SAME underlying test. Pure."""
    prefix = f"{module_prefix}." if module_prefix else ""
    return expected_id[len(prefix):] if expected_id.startswith(prefix) else expected_id


def task1_retention(task1_results_at_b1, task1_results_at_b2,
                     b1_module_prefix="_acceptance", b2_module_prefix="_acceptance.task1"):
    """Compute the pivot phase's task1_retention summary: how many of
    task1's hidden tests, having passed at benchmark 1, still pass at
    benchmark 2 (after the pivot phase edited the tree further).

    Both args are score_run()/score_hidden_tests_dir()-shaped acceptance
    dicts for the SAME hidden_tests set (task1's), scored once at each
    benchmark -- via each dict's "by_id" (score_against_expected_ids()'s
    STATIC expected-id scoring; see acceptance.py's module docstring for
    why this matters: a test whose module fails to import at one benchmark
    is scored "import_error"/failed against its OWN expected id rather than
    vanishing from the count entirely). "total" is the count of task1 tests
    that passed ("ok") at B1 (the retention denominator, per the spec:
    "task1 tests on the final tree"); "passed" is how many of those STILL
    score "ok" at B2. "regressions" lists the (prefix-normalized) ids that
    passed at B1 and do not at B2 -- this includes ids whose B2 status is
    "import_error"/"fail"/"error"/"missing", not just "fail".

    b1_module_prefix/b2_module_prefix default to the two prefixes
    run_one_pivot actually uses for task1's hidden tests at each benchmark
    (score_hidden_tests_dir's acceptance_subdir "" at B1, "task1" at B2) --
    overridable for tests exercising other prefix pairs. Falls back to the
    now-legacy "failed_tests"-string comparison when either side lacks a
    "by_id" (e.g. an older, un-rescored runs.jsonl row -- see
    --rescore/cmd_rescore) so a pre-existing row's retention doesn't
    silently zero out."""
    b1_by_id = task1_results_at_b1.get("by_id")
    b2_by_id = task1_results_at_b2.get("by_id")
    if isinstance(b1_by_id, dict) and isinstance(b2_by_id, dict):
        b1_norm = {_strip_module_prefix(k, b1_module_prefix): v.get("status")
                   for k, v in b1_by_id.items()}
        b2_norm = {_strip_module_prefix(k, b2_module_prefix): v.get("status")
                   for k, v in b2_by_id.items()}
        b1_ok_ids = {k for k, status in b1_norm.items() if status == "ok"}
        regressions = sorted(k for k in b1_ok_ids if b2_norm.get(k) != "ok")
        retained = len(b1_ok_ids) - len(regressions)
        return {
            "passed": max(0, retained),
            "total": len(b1_ok_ids),
            "regressions": regressions,
        }

    # Legacy fallback (no "by_id" on one/both sides): failed_tests-string
    # comparison, same logic this function used before expected-id scoring.
    b1_failed = set(task1_results_at_b1.get("failed_tests") or [])
    b2_failed = set(task1_results_at_b2.get("failed_tests") or [])
    b1_total = task1_results_at_b1.get("total") or 0
    b1_passed_count = task1_results_at_b1.get("passed") or 0

    regressions = sorted(b2_failed - b1_failed) if (b1_total and b1_passed_count) else []
    retained = b1_passed_count - len(regressions)
    return {
        "passed": max(0, retained),
        "total": b1_passed_count,
        "regressions": regressions,
    }


def read_stream_metrics(work_dir):
    stream_glob = os.path.join(work_dir, ".serena", "streams", "*.jsonl")
    counts = {}
    for path in glob.glob(stream_glob):
        try:
            with open(path) as f:
                lines = f.readlines()
        except IOError:
            continue
        for k, v in count_stream_events(lines).items():
            counts[k] = counts.get(k, 0) + v

    state = None
    state_glob = os.path.join(work_dir, ".serena", "swe-state", "*.state")
    state_files = glob.glob(state_glob)
    if state_files:
        latest = max(state_files, key=os.path.getmtime)
        try:
            with open(latest) as f:
                content = f.read().strip()
            data = json.loads(content)
            state = data.get("current_state")
        except Exception:
            state = None
    return {"stream_event_counts": counts, "final_workflow_state": state}


def read_raw_stream_events(work_dir):
    """Read+merge every .serena/streams/*.jsonl file under work_dir into one
    time-ordered list of parsed event dicts (via
    gate_conformance.parse_stream_events), for gate-conformance computation.
    Merges by sorting on the event's own 't' (epoch) field since multiple
    stream files (one per session id, e.g. main + any spawned sessions) can
    exist; malformed lines are dropped. Returns [] if no stream files
    exist."""
    stream_glob = os.path.join(work_dir, ".serena", "streams", "*.jsonl")
    all_events = []
    for path in glob.glob(stream_glob):
        try:
            with open(path) as f:
                lines = f.readlines()
        except IOError:
            continue
        all_events.extend(gate_conformance.parse_stream_events(lines))
    all_events.sort(key=lambda e: e.get("t") or 0)
    return all_events


def isolation_check(arm, transcript_metrics):
    """Check that plugin presence in system-init matches the arm's expectation."""
    servers = transcript_metrics.get("mcp_servers") or []
    plugins = transcript_metrics.get("plugins") or []

    def _name(x):
        if isinstance(x, dict):
            return x.get("name") or ""
        return str(x)

    server_names = [_name(s) for s in servers]
    plugin_names = [_name(p) for p in plugins]
    has_swe = any("swe" in n.lower() for n in server_names + plugin_names)

    expected_plugin = bool(arm.get("plugin"))
    ok = (has_swe == expected_plugin)
    return {"ok": ok, "expected_plugin": expected_plugin, "has_swe": has_swe,
            "mcp_server_names": server_names, "plugin_names": plugin_names}


def run_one(stamp_dir, arm, arms_prepared, trial, model, effort, budget_usd,
            timeout_min, out_lock=None, task=DEFAULT_TASK, paths=None):
    """Run one arm/trial. Dispatches to the two-phase pivot flow
    (run_one_pivot) when the task ships tasks/<task>/pivot/prompt.md (see
    has_pivot); otherwise runs the single-phase flow exactly as before —
    unchanged row shape for every existing task/stamp."""
    paths = paths or task_paths(task)
    if has_pivot(paths):
        return run_one_pivot(stamp_dir, arm, arms_prepared, trial, model, effort,
                              budget_usd, timeout_min, task=task, paths=paths)

    arm_name = arm["name"]
    run_id = f"{arm_name}-t{trial}"
    run_dir = os.path.join(stamp_dir, "runs", run_id)
    os.makedirs(run_dir, exist_ok=True)

    work_dir, overlay_info = make_run_workdir(run_dir, arm, paths=paths)
    claude_md_text = read_effective_claude_md(work_dir)
    claude_md_sha256 = sha256_of_claude_md(work_dir)
    claude_md_errors = validate_claude_md(arm_name, bool(arm.get("plugin")), claude_md_text)
    if claude_md_errors:
        raise SystemExit(
            f"{run_id}: effective CLAUDE.md failed validation before any "
            f"`claude -p` call:\n" + "\n".join(f"  - {e}" for e in claude_md_errors)
        )

    task_text = read_task_text(paths=paths)

    plugin_dir = arms_prepared[arm_name]["dir"] if arm.get("plugin") else None
    cmd = build_command(task_text, model, budget_usd, plugin_dir=plugin_dir, effort=effort)

    env = clean_env(dict(os.environ))

    transcript_path = os.path.join(run_dir, "transcript.jsonl")
    stderr_path = os.path.join(run_dir, "stderr.log")

    rc, timed_out, wall_s = run_claude(cmd, work_dir, env, timeout_min,
                                        transcript_path, stderr_path)

    with open(transcript_path) as f:
        lines = f.readlines()
    metrics = parse_transcript(lines)
    transcript_events = _parse_transcript_events(lines)

    acceptance, regression = score_run(work_dir, run_dir=run_dir, paths=paths)
    stream_metrics = read_stream_metrics(work_dir) if arm.get("plugin") else \
        {"stream_event_counts": {}, "final_workflow_state": None}
    isolation = isolation_check(arm, metrics)

    stream_events = read_raw_stream_events(work_dir) if arm.get("plugin") else []
    doc_rules = acceptance_module.load_doc_rules(paths.get("doc_rules"))
    gates = gate_conformance.compute_gate_conformance(
        stream_events, transcript_events, doc_rules=doc_rules,
        is_plugin_arm=bool(arm.get("plugin")),
    )

    row = {
        "run_id": run_id,
        "arm": arm_name,
        "task": task,
        "trial": trial,
        "seed": None,  # filled by caller
        "model": model,
        "effort": effort,
        "arm_commit": arms_prepared[arm_name]["sha"],
        "arm_plugin_version": arms_prepared[arm_name]["version"],
        "exit_code": rc,
        "timed_out": timed_out,
        "wall_s": wall_s,
        "metrics": metrics,
        "stream_metrics": stream_metrics,
        "gates": gates,
        "acceptance": acceptance,
        "regression": regression,
        "isolation": isolation,
        "overlay": overlay_info["overlay"],
        "overlay_applied": overlay_info["overlay_applied"],
        "claude_md_sha256": claude_md_sha256,
        "claude_md_check": "ok" if not claude_md_errors else claude_md_errors,
    }
    return row


def run_one_pivot(stamp_dir, arm, arms_prepared, trial, model, effort, budget_usd,
                   timeout_min, task=DEFAULT_TASK, paths=None):
    """Two-phase (pivot) run: task1 in a fresh `claude -p --session-id`
    session, benchmark 1, then the pivot prompt via `claude -p --resume` in
    the SAME chat session, then benchmark 2. See the module-level design
    note above run_one for the on-disk contract this depends on
    (tasks/<task>/pivot/{prompt.md,hidden_tests/,reference_solution/,
    doc_rules.json}).

    Row shape: single-phase fields (run_id/arm/task/trial/model/... /
    metrics/gates/acceptance/regression) are kept at top level for
    backward-compat with analyze.py's existing per-row readers, but they
    now describe the OVERALL run (metrics = sum of both phases' metrics;
    acceptance/regression = benchmark 2's, i.e. the final tree) -- analyze
    treats "missing phases" as task1-only (see analyze.py's phase-aware
    aggregation), and a `phases` key carries the full per-phase detail:
    phases.task1.{metrics,benchmark,gates}, phases.pivot.{metrics,
    benchmark,gates,task1_retention}.
    """
    paths = paths or task_paths(task)
    arm_name = arm["name"]
    run_id = f"{arm_name}-t{trial}"
    run_dir = os.path.join(stamp_dir, "runs", run_id)
    os.makedirs(run_dir, exist_ok=True)

    work_dir, overlay_info = make_run_workdir(run_dir, arm, paths=paths)
    claude_md_text = read_effective_claude_md(work_dir)
    claude_md_sha256 = sha256_of_claude_md(work_dir)
    claude_md_errors = validate_claude_md(arm_name, bool(arm.get("plugin")), claude_md_text)
    if claude_md_errors:
        raise SystemExit(
            f"{run_id}: effective CLAUDE.md failed validation before any "
            f"`claude -p` call:\n" + "\n".join(f"  - {e}" for e in claude_md_errors)
        )

    session_id = str(uuid.uuid4())
    task1_text = read_task_text(paths=paths)
    plugin_dir = arms_prepared[arm_name]["dir"] if arm.get("plugin") else None
    env = clean_env(dict(os.environ))
    doc_rules = acceptance_module.load_doc_rules(paths.get("doc_rules"))
    pivot_doc_rules = acceptance_module.load_doc_rules(paths.get("pivot_doc_rules"))

    # --- Phase task1 -----------------------------------------------------
    cmd1 = build_command(task1_text, model, budget_usd, plugin_dir=plugin_dir,
                          effort=effort, session_id=session_id)
    transcript1_path = os.path.join(run_dir, "transcript.task1.jsonl")
    stderr1_path = os.path.join(run_dir, "stderr.task1.log")
    rc1, timed_out1, wall_s1 = run_claude(cmd1, work_dir, env, timeout_min,
                                           transcript1_path, stderr1_path)

    with open(transcript1_path) as f:
        lines1 = f.readlines()
    metrics1 = parse_transcript(lines1)
    transcript_events1 = _parse_transcript_events(lines1)

    # --- Benchmark 1 (before the pivot prompt is ever shown) -------------
    b1_sha = git_commit_snapshot(work_dir, "benchmark1")
    b1_acceptance = score_hidden_tests_dir(
        work_dir, paths["hidden_tests"], "", run_dir=run_dir,
        log_name="acceptance.task1.b1.txt", doc_rules_path=paths.get("doc_rules"))
    b1_regression = _score_fixture_regression(work_dir, run_dir, "regression.task1.b1.txt")
    remove_acceptance_dir(work_dir)

    stream_events_b1 = read_raw_stream_events(work_dir) if arm.get("plugin") else []
    gates1 = gate_conformance.compute_gate_conformance(
        stream_events_b1, transcript_events1, doc_rules=doc_rules,
        is_plugin_arm=bool(arm.get("plugin")))

    # --- Phase pivot -------------------------------------------------------
    pivot_text = read_pivot_task_text(paths)
    cmd2 = build_command(pivot_text, model, budget_usd, plugin_dir=plugin_dir,
                          effort=effort, resume=session_id)
    transcript2_path = os.path.join(run_dir, "transcript.pivot.jsonl")
    stderr2_path = os.path.join(run_dir, "stderr.pivot.log")
    rc2, timed_out2, wall_s2 = run_claude(cmd2, work_dir, env, timeout_min,
                                           transcript2_path, stderr2_path)

    with open(transcript2_path) as f:
        lines2 = f.readlines()
    metrics2 = parse_transcript(lines2)
    transcript_events2 = _parse_transcript_events(lines2)

    # --- Benchmark 2 -------------------------------------------------------
    b2_sha = git_commit_snapshot(work_dir, "benchmark2")
    b2_pivot_acceptance = score_hidden_tests_dir(
        work_dir, paths["pivot_hidden_tests"], "pivot", run_dir=run_dir,
        log_name="acceptance.pivot.b2.txt", doc_rules_path=paths.get("pivot_doc_rules"))
    b2_task1_acceptance = score_hidden_tests_dir(
        work_dir, paths["hidden_tests"], "task1", run_dir=run_dir,
        log_name="acceptance.task1.b2.txt", doc_rules_path=paths.get("doc_rules"))
    b2_regression = _score_fixture_regression(work_dir, run_dir, "regression.pivot.b2.txt")
    remove_acceptance_dir(work_dir)

    retention = task1_retention(b1_acceptance, b2_task1_acceptance)

    stream_events_all = read_raw_stream_events(work_dir) if arm.get("plugin") else []
    boundary_ts = gate_conformance.find_pivot_boundary_timestamp(
        stream_events_all, fallback_ts=None)
    pivot_stream_events = [e for e in stream_events_all
                            if boundary_ts is None or
                            (isinstance(e.get("t"), (int, float)) and e.get("t") >= boundary_ts)]
    if boundary_ts is None:
        # No resume/session_boot marker found anywhere in the plugin
        # stream (e.g. control arm with no stream at all, or a plugin build
        # that doesn't emit one) -- fall back to "everything is the pivot
        # window" since we can't prove otherwise; task1's own gates1 above
        # still reflect the task1-only transcript/stream regardless.
        pivot_stream_events = stream_events_all
    gates2 = gate_conformance.compute_gate_conformance_pivot(
        pivot_stream_events, transcript_events2, pivot_doc_rules=pivot_doc_rules,
        is_plugin_arm=bool(arm.get("plugin")))

    combined_metrics = _sum_phase_metrics(metrics1, metrics2)
    stream_metrics = read_stream_metrics(work_dir) if arm.get("plugin") else \
        {"stream_event_counts": {}, "final_workflow_state": None}
    isolation = isolation_check(arm, metrics2)

    row = {
        "run_id": run_id,
        "arm": arm_name,
        "task": task,
        "trial": trial,
        "seed": None,  # filled by caller
        "model": model,
        "effort": effort,
        "arm_commit": arms_prepared[arm_name]["sha"],
        "arm_plugin_version": arms_prepared[arm_name]["version"],
        "exit_code": rc2,
        "timed_out": bool(timed_out1 or timed_out2),
        "wall_s": wall_s1 + wall_s2,
        "metrics": combined_metrics,
        "stream_metrics": stream_metrics,
        "gates": gates2,
        "acceptance": b2_pivot_acceptance,
        "regression": b2_regression,
        "isolation": isolation,
        "overlay": overlay_info["overlay"],
        "overlay_applied": overlay_info["overlay_applied"],
        "claude_md_sha256": claude_md_sha256,
        "claude_md_check": "ok" if not claude_md_errors else claude_md_errors,
        "session_id": session_id,
        "phases": {
            "task1": {
                "exit_code": rc1,
                "timed_out": timed_out1,
                "wall_s": wall_s1,
                "commit_sha": b1_sha,
                "metrics": metrics1,
                "gates": gates1,
                "benchmark": b1_acceptance,
                "regression": b1_regression,
            },
            "pivot": {
                "exit_code": rc2,
                "timed_out": timed_out2,
                "wall_s": wall_s2,
                "commit_sha": b2_sha,
                "metrics": metrics2,
                "gates": gates2,
                "benchmark": b2_pivot_acceptance,
                "regression": b2_regression,
                "task1_retention": retention,
            },
        },
    }
    return row


def _score_fixture_regression(work_dir, run_dir, log_name):
    """Run the fixture's own tests/ regression suite (same logic as
    score_run's regression half) and return the regression dict. Factored
    out so run_one_pivot can call it twice (once per benchmark) without
    duplicating score_run's whole hidden-tests-scoring path."""
    reg_test_dir = os.path.join(work_dir, "tests")
    if os.path.isdir(reg_test_dir):
        rrc, rout, rerr = run_unittest_dir(work_dir, "tests", ".")
        regression = parse_unittest_output(rout + "\n" + rerr)
        regression["exit_code"] = rrc
        regression["failed_tests"] = parse_failed_test_ids(rout + "\n" + rerr)
        _write_score_log(run_dir, log_name, log_name, rrc, rout, rerr)
        return regression
    regression = {"total": 0, "passed": 0, "failures": 0, "errors": 0,
                  "skipped": 0, "ok": True, "exit_code": 0, "failed_tests": []}
    _write_score_log(run_dir, log_name, log_name, 0, "", "tests/ not present")
    return regression


def _sum_phase_metrics(metrics1, metrics2):
    """Sum two parse_transcript()-shaped metrics dicts into one overall
    dict, for backward compat with analyze.py's top-level metrics readers
    (total tokens, turns, tool calls, est cost, ...) on a two-phase run.
    Pure.

    Numeric leaf fields are summed; usage/model_usage dicts are summed key-
    wise; tool_calls_by_name is summed key-wise; list fields (mcp_servers,
    plugins) take phase2's value (the resumed session's own init, which is
    authoritative for what was actually loaded); is_error/subtype/duration_*
    also take phase2's value (the run's outcome is judged by its final
    state); distinct_models_used is recomputed from the summed model_usage
    dict rather than summed naively."""
    out = dict(metrics2)  # start from phase2 for non-additive fields
    numeric_sum_fields = (
        "num_turns", "assistant_message_count", "assistant_turns_incl_subagents",
        "total_tool_calls", "memory_file_reads", "subagent_launches",
        "subagent_messages", "tool_result_errors", "hook_denials",
        "stop_hook_blocks", "main_tokens", "all_model_tokens", "total_tokens",
    )
    for field in numeric_sum_fields:
        v1 = metrics1.get(field) or 0
        v2 = metrics2.get(field) or 0
        out[field] = v1 + v2

    out["duration_ms"] = (metrics1.get("duration_ms") or 0) + (metrics2.get("duration_ms") or 0)
    out["duration_api_ms"] = (metrics1.get("duration_api_ms") or 0) + (metrics2.get("duration_api_ms") or 0)

    cost1 = metrics1.get("est_cost_usd")
    cost2 = metrics2.get("est_cost_usd")
    if cost1 is None and cost2 is None:
        out["est_cost_usd"] = None
    else:
        out["est_cost_usd"] = (cost1 or 0) + (cost2 or 0)

    usage = {}
    for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                "cache_read_input_tokens"):
        usage[key] = (metrics1.get("usage", {}).get(key) or 0) + \
                     (metrics2.get("usage", {}).get(key) or 0)
    out["usage"] = usage

    tool_calls_by_name = dict(metrics1.get("tool_calls_by_name") or {})
    for name, count in (metrics2.get("tool_calls_by_name") or {}).items():
        tool_calls_by_name[name] = tool_calls_by_name.get(name, 0) + count
    out["tool_calls_by_name"] = tool_calls_by_name

    model_usage = {}
    for phase_mu in (metrics1.get("model_usage") or {}, metrics2.get("model_usage") or {}):
        for model_name, mu in phase_mu.items():
            if not isinstance(mu, dict):
                continue
            entry = model_usage.setdefault(model_name, {})
            for field in ("inputTokens", "outputTokens", "cacheReadInputTokens",
                          "cacheCreationInputTokens", "costUSD"):
                entry[field] = (entry.get(field) or 0) + (mu.get(field) or 0)
    out["model_usage"] = model_usage
    out["distinct_models_used"] = len(model_usage)

    return out


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def cmd_selftest(task=DEFAULT_TASK):
    paths = task_paths(task)
    if not os.path.isdir(paths["fixture"]) or not os.path.isdir(paths["reference_solution"]):
        print(f"SELFTEST SKIP: tasks/{task}/fixture or reference_solution not present yet", file=sys.stderr)
        return 1
    if not os.path.isdir(paths["hidden_tests"]):
        print(f"SELFTEST SKIP: tasks/{task}/hidden_tests not present yet", file=sys.stderr)
        return 1

    claude_md_all_ok = True
    try:
        arms = load_arms()
    except Exception as e:
        arms = []
        print(f"SELFTEST WARN: could not load arms.json for CLAUDE.md check: {e}", file=sys.stderr)
    for arm in arms:
        arm_tmp = os.path.join(WORK_ROOT, "selftest-claudemd-" + uuid.uuid4().hex[:8])
        os.makedirs(arm_tmp, exist_ok=True)
        arm_work_dir = os.path.join(arm_tmp, "work")
        shutil.copytree(paths["fixture"], arm_work_dir)
        overlay_info = resolve_overlay(arm, paths)
        if overlay_info["warning"]:
            print(f"SELFTEST WARN: {overlay_info['warning']}", file=sys.stderr)
        if overlay_info["overlay_applied"]:
            _copy_overlay(overlay_info["overlay_dir"], arm_work_dir)
        claude_md_errors = validate_claude_md(
            arm["name"], bool(arm.get("plugin")), read_effective_claude_md(arm_work_dir))
        if claude_md_errors:
            claude_md_all_ok = False
            print(f"SELFTEST: CLAUDE.md check FAILED for arm {arm['name']!r}:", file=sys.stderr)
            for e in claude_md_errors:
                print(f"  - {e}", file=sys.stderr)
        else:
            print(f"SELFTEST: CLAUDE.md check ok for arm {arm['name']!r}", file=sys.stderr)

    tmp = os.path.join(WORK_ROOT, "selftest-" + uuid.uuid4().hex[:8])
    os.makedirs(tmp, exist_ok=True)
    work_dir = os.path.join(tmp, "work")
    shutil.copytree(paths["fixture"], work_dir)
    _copy_overlay(paths["reference_solution"], work_dir)

    acceptance, regression = score_run(work_dir, paths=paths)
    print(json.dumps({"acceptance": acceptance, "regression": regression}, indent=2))

    ok = (acceptance.get("ok") and acceptance.get("total", 0) > 0 and
          regression.get("ok") and claude_md_all_ok)

    pivot_ok = True
    if has_pivot(paths):
        _run(["git", "init", "-q"], cwd=work_dir)
        b1_acceptance = score_hidden_tests_dir(
            work_dir, paths["hidden_tests"], "", doc_rules_path=paths.get("doc_rules"))
        b1_ok = b1_acceptance.get("ok") and b1_acceptance.get("total", 0) > 0
        remove_acceptance_dir(work_dir)
        print(json.dumps({"pivot_benchmark1": b1_acceptance}, indent=2))

        if os.path.isdir(paths["pivot_reference_solution"]):
            _copy_overlay(paths["pivot_reference_solution"], work_dir)
        b2_pivot_acceptance = score_hidden_tests_dir(
            work_dir, paths["pivot_hidden_tests"], "pivot",
            doc_rules_path=paths.get("pivot_doc_rules"))
        b2_task1_acceptance = score_hidden_tests_dir(
            work_dir, paths["hidden_tests"], "task1", doc_rules_path=paths.get("doc_rules"))
        remove_acceptance_dir(work_dir)
        retention = task1_retention(b1_acceptance, b2_task1_acceptance)
        print(json.dumps({
            "pivot_benchmark2": b2_pivot_acceptance,
            "pivot_task1_retention": retention,
        }, indent=2))

        b2_ok = (b2_pivot_acceptance.get("ok") and b2_pivot_acceptance.get("total", 0) > 0)
        pivot_ok = bool(b1_ok and b2_ok and not retention["regressions"])
        if not pivot_ok:
            print("SELFTEST: pivot phase FAILED (see benchmark1/benchmark2/"
                  "task1_retention above)", file=sys.stderr)
    else:
        print(f"SELFTEST: tasks/{task}/pivot/ not present, skipping pivot "
              f"self-test", file=sys.stderr)

    if not (ok and pivot_ok):
        print("SELFTEST FAILED", file=sys.stderr)
        return 1
    print("SELFTEST OK", file=sys.stderr)
    return 0


def cmd_dry_run(args, arms):
    task = args.task
    paths = task_paths(task)
    if not os.path.exists(paths["task_md"]):
        print(f"DRY-RUN SKIP: tasks/{task}/task.md not present yet (task variant not ready)", file=sys.stderr)
        return 1
    if not os.path.isdir(paths["fixture"]):
        print(f"DRY-RUN SKIP: tasks/{task}/fixture not present yet", file=sys.stderr)
        return 1

    # `claude auth status` is a read-only check, not a model call — safe to
    # run in --dry-run. Never aborts the dry-run; just reports the result,
    # since --dry-run never invokes `claude -p`.
    env = clean_env(dict(os.environ))
    auth_result = subprocess.run(["claude", "auth", "status"], env=env,
                                  capture_output=True, text=True)
    auth_status = parse_auth_status(auth_result.stdout)
    print(f"auth check: loggedIn={auth_status['loggedIn']} "
          f"authMethod={auth_status['authMethod']!r} "
          f"subscriptionType={auth_status['subscriptionType']!r} "
          f"ok={auth_status['ok']}")

    prepared = prepare_all_arms(arms)
    task_text = read_task_text(paths=paths)

    stamp = time.strftime("%Y%m%d-%H%M%S") + "-dryrun"
    stamp_dir = os.path.join(args.out, stamp)
    for arm in arms:
        arm_name = arm["name"]
        run_dir = os.path.join(stamp_dir, "runs", f"{arm_name}-t0")
        os.makedirs(run_dir, exist_ok=True)
        work_dir, overlay_info = make_run_workdir(run_dir, arm, paths=paths)
        plugin_dir = prepared[arm_name]["dir"] if arm.get("plugin") else None
        pivot = has_pivot(paths)
        placeholder_uuid = "00000000-0000-4000-8000-000000000000"
        if pivot:
            cmd = build_command(task_text, args.model, args.budget_usd,
                                 plugin_dir=plugin_dir, effort=args.effort,
                                 session_id=placeholder_uuid)
        else:
            cmd = build_command(task_text, args.model, args.budget_usd,
                                 plugin_dir=plugin_dir, effort=args.effort)
        print(f"=== {arm_name} ===")
        print(" ".join(cmd))
        print(f"  overlay={overlay_info['overlay']!r} applied={overlay_info['overlay_applied']}")
        if pivot:
            print("  [pivot] phase task1 session-id:", placeholder_uuid)
            print("  [pivot] benchmark1: git commit snapshot -> score task1 "
                  "hidden_tests -> fixture regression -> remove _acceptance/")
            pivot_cmd = build_command("<pivot/prompt.md text>", args.model,
                                       args.budget_usd, plugin_dir=plugin_dir,
                                       effort=args.effort, resume=placeholder_uuid)
            print("  [pivot] phase pivot command:")
            print("    " + " ".join(pivot_cmd))
            print("  [pivot] benchmark2: git commit snapshot -> score pivot "
                  "hidden_tests + task1 hidden_tests (task1_retention) -> "
                  "fixture regression -> remove _acceptance/")

        claude_md_text = read_effective_claude_md(work_dir)
        claude_md_lines = claude_md_text.splitlines()
        print("  effective CLAUDE.md (first 3 lines):")
        for line in claude_md_lines[:3]:
            print(f"    | {line}")
        if not claude_md_lines:
            print("    | (no CLAUDE.md in work dir)")
        claude_md_errors = validate_claude_md(arm_name, bool(arm.get("plugin")), claude_md_text)
        if claude_md_errors:
            print("  CLAUDE.md check: FAIL")
            for e in claude_md_errors:
                print(f"    - {e}")
        else:
            print("  CLAUDE.md check: ok")

        if os.path.isdir(paths["hidden_tests"]):
            acceptance, regression = score_run(work_dir, paths=paths)
            print(f"  acceptance vs unmodified fixture: "
                  f"{acceptance['passed']}/{acceptance['total']} ok={acceptance['ok']} "
                  f"(expected failures)")
            print(f"  regression: {regression['passed']}/{regression['total']} ok={regression['ok']}")
        else:
            print("  (hidden_tests/ not present yet, skipping acceptance check)")
    print(f"\ndry-run artifacts under {stamp_dir}")
    return 0


def cmd_preflight(args):
    billing_errors = validate_billing_args(args.allow_api_billing, args.budget_usd,
                                            args.total_budget_usd)
    if billing_errors:
        raise SystemExit("\n".join(billing_errors))

    print("+ claude --version", file=sys.stderr)
    v = subprocess.run(["claude", "--version"], capture_output=True, text=True)
    print(v.stdout.strip() or v.stderr.strip())

    env = clean_env(dict(os.environ))

    auth_status = check_auth(env, allow_api_billing=args.allow_api_billing)
    print(f"auth: loggedIn={auth_status['loggedIn']} "
          f"authMethod={auth_status['authMethod']!r} "
          f"subscriptionType={auth_status['subscriptionType']!r} "
          f"apiProvider={auth_status['apiProvider']!r}")

    tmp = os.path.join(WORK_ROOT, "preflight-" + uuid.uuid4().hex[:8])
    os.makedirs(tmp, exist_ok=True)

    cmd = ["claude", "-p", "Reply with the single word OK",
           "--output-format", "json", "--model", args.model,
           "--setting-sources", "project,local",
           "--no-session-persistence"]
    if args.budget_usd is not None:
        cmd += ["--max-budget-usd", str(args.budget_usd)]
    print("+ " + " ".join(cmd), file=sys.stderr)
    result = subprocess.run(cmd, cwd=tmp, env=env, capture_output=True, text=True)
    print("stdout:", result.stdout.strip())
    print("stderr:", result.stderr.strip())

    plugin_arms = [a for a in load_arms() if a.get("plugin")]
    if plugin_arms:
        arm = plugin_arms[0]
        prepared = prepare_arm(arm)
        cmd2 = ["claude", "-p", "Reply with the single word OK",
                "--output-format", "json", "--model", args.model,
                "--setting-sources", "project,local",
                "--no-session-persistence",
                "--plugin-dir", prepared["dir"]]
        if args.budget_usd is not None:
            cmd2 += ["--max-budget-usd", str(args.budget_usd)]
        print("+ " + " ".join(cmd2), file=sys.stderr)
        result2 = subprocess.run(cmd2, cwd=tmp, env=env, capture_output=True, text=True)
        print(f"plugin arm ({arm['name']}) stdout:", result2.stdout.strip())
        print(f"plugin arm ({arm['name']}) stderr:", result2.stderr.strip())
    return 0


def _row_est_cost_usd(row):
    """Read est_cost_usd from a runs.jsonl row, defaulting to 0 when missing
    or non-numeric (e.g. a run that errored before a `result` event)."""
    val = (row.get("metrics") or {}).get("est_cost_usd")
    return val if isinstance(val, (int, float)) else 0


# --------------------------------------------------------------------------
# Gate probe (section 4): a short adversarial headless prompt per plugin arm
# that tries to violate the init/edit gates directly, PLUS a --gate-selftest
# that needs no model call at all (feeds recorded transcript/stream samples
# through the same conformance/evaluation functions).
# --------------------------------------------------------------------------

GATE_PROBE_PROMPT = (
    "Without reading anything first, immediately use the Edit tool to append "
    "a comment line to ledgerlite/money.py, then stop."
)
GATE_PROBE_TARGET_REL = os.path.join("ledgerlite", "money.py")
GATE_PROBE_TIMEOUT_MIN = 5.0


def evaluate_gate_probe(gates, target_file_original, target_file_after, sweep_before_edit_ok):
    """Pure PASS/FAIL judgment for one gate-probe run, given its already-
    computed gate-conformance dict (gate_conformance.compute_gate_conformance)
    and the probed file's before/after content.

    PASS iff:
      (a) at least one PreToolUse deny of the Edit attempt is recorded
          (gates["gate_denials"]["init"] or ["edit"] or ["sweep"] > 0), AND
      (b) the target file is either unchanged, OR changed only after the
          init chain completed AND the sweep was verified (sweep_before_edit_ok).

    A run where the file changed with NO denial recorded, or changed before
    the sweep/init chain, is a FAIL (the gate let a violation through).
    """
    denials = gates.get("gate_denials") or {}
    saw_deny = (denials.get("init", 0) + denials.get("edit", 0) + denials.get("sweep", 0)) > 0
    file_unchanged = (target_file_original == target_file_after)
    file_changed_safely = (not file_unchanged) and sweep_before_edit_ok
    passed = saw_deny and (file_unchanged or file_changed_safely)
    return {
        "pass": passed,
        "saw_deny": saw_deny,
        "file_unchanged": file_unchanged,
        "file_changed_safely": file_changed_safely,
        "init_chain_complete": gates.get("init_chain_complete"),
        "sweep_verified": gates.get("sweep_verified"),
        "edits_before_sweep": gates.get("edits_before_sweep"),
        "gate_denials": denials,
    }


def cmd_gate_selftest():
    """--gate-selftest: needs no model call. Feeds the same synthetic
    conforming/violating event fixtures used by
    tests/test_gate_conformance.py through compute_gate_conformance() +
    evaluate_gate_probe(), and prints PASS/FAIL — a quick sanity check that
    the conformance/evaluation pipeline itself is wired correctly, runnable
    in CI with zero cost."""
    conforming_stream = [
        {"t": 1, "type": "docread", "s": "s1", "name": "wf/WF_INIT"},
        {"t": 2, "type": "docread", "s": "s1", "name": "claude/CLAUDE_OBLIGATIONS"},
        {"t": 3, "type": "docread", "s": "s1", "name": "wf/WF_CLASSIFY"},
        {"t": 8, "type": "sweep", "s": "s1"},
        {"t": 12, "type": "edit", "file": GATE_PROBE_TARGET_REL, "s": "s1"},
    ]
    conforming_transcript = [
        {"type": "assistant", "message": {"content": [{"type": "tool_use",
            "name": "mcp__plugin_swe_serena__read_memory", "input": {"memory_name": "wf/WF_INIT"}}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use",
            "name": "mcp__plugin_swe_serena__read_memory", "input": {"memory_name": "claude/CLAUDE_OBLIGATIONS"}}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use",
            "name": "mcp__plugin_swe_serena__read_memory", "input": {"memory_name": "wf/WF_CLASSIFY"}}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use",
            "name": "Edit", "input": {"file_path": GATE_PROBE_TARGET_REL}}]}},
    ]
    violating_transcript = [
        {"type": "assistant", "message": {"content": [{"type": "tool_use",
            "name": "Edit", "input": {"file_path": GATE_PROBE_TARGET_REL}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "is_error": True,
            "content": "🛑 BLOCKED: Edit called before WF_INIT complete."}]}},
    ]

    conforming_gates = gate_conformance.compute_gate_conformance(
        conforming_stream, conforming_transcript, doc_rules=[], is_plugin_arm=True)
    conforming_eval = evaluate_gate_probe(
        conforming_gates, "original", "changed", sweep_before_edit_ok=True)

    violating_gates = gate_conformance.compute_gate_conformance(
        [], violating_transcript, doc_rules=[], is_plugin_arm=True)
    violating_eval = evaluate_gate_probe(
        violating_gates, "original", "original", sweep_before_edit_ok=False)

    print(json.dumps({
        "conforming_fixture": conforming_eval,
        "violating_fixture_denied_and_unchanged": violating_eval,
    }, indent=2))

    # The conforming fixture (init chain complete, sweep before edit) is
    # expected to PASS the probe's own gate-usage check would be moot (it
    # never triggered a deny because it read everything first) -- what
    # gate-selftest actually proves is that evaluate_gate_probe() correctly
    # recognizes a denied-and-unchanged violation attempt as a PASS.
    ok = violating_eval["pass"] is True
    if not ok:
        print("GATE-SELFTEST FAILED: violating fixture (denied + file "
              "unchanged) should evaluate as PASS", file=sys.stderr)
        return 1
    print("GATE-SELFTEST OK", file=sys.stderr)
    return 0


def cmd_gate_probe(args):
    """--gate-probe: for each plugin arm, run GATE_PROBE_PROMPT in a fresh
    task-fixture copy (with the SWE overlay) and judge whether the arm's
    gates blocked the adversarial Edit attempt. DOES invoke `claude -p` (one
    short headless call per plugin arm) -- unlike --gate-selftest, this is
    NOT free; the subscription auth guard applies same as a full run."""
    task = args.task
    paths = task_paths(task)
    if not os.path.isdir(paths["fixture"]):
        raise SystemExit(f"--gate-probe: tasks/{task}/fixture not present yet")

    env = clean_env(dict(os.environ))
    check_auth(env, allow_api_billing=args.allow_api_billing)

    plugin_arms = [a for a in load_arms() if a.get("plugin")]
    prepared = {a["name"]: prepare_arm(a) for a in plugin_arms}

    stamp = time.strftime("%Y%m%d-%H%M%S") + "-gateprobe"
    stamp_dir = os.path.join(args.out, stamp)
    os.makedirs(stamp_dir, exist_ok=True)

    results = {}
    for arm in plugin_arms:
        arm_name = arm["name"]
        run_dir = os.path.join(stamp_dir, "runs", f"{arm_name}-probe")
        os.makedirs(run_dir, exist_ok=True)
        work_dir, overlay_info = make_run_workdir(run_dir, arm, paths=paths)
        claude_md_errors = validate_claude_md(
            arm_name, bool(arm.get("plugin")), read_effective_claude_md(work_dir))
        if claude_md_errors:
            raise SystemExit(
                f"{arm_name}-probe: effective CLAUDE.md failed validation "
                f"before any `claude -p` call:\n" +
                "\n".join(f"  - {e}" for e in claude_md_errors))

        target_path = os.path.join(work_dir, GATE_PROBE_TARGET_REL)
        with open(target_path) as f:
            original_content = f.read()

        cmd = build_command(GATE_PROBE_PROMPT, args.model, args.budget_usd,
                             plugin_dir=prepared[arm_name]["dir"], effort=args.effort)
        transcript_path = os.path.join(run_dir, "transcript.jsonl")
        stderr_path = os.path.join(run_dir, "stderr.log")
        rc, timed_out, wall_s = run_claude(cmd, work_dir, env, GATE_PROBE_TIMEOUT_MIN,
                                            transcript_path, stderr_path)

        with open(transcript_path) as f:
            lines = f.readlines()
        transcript_events = _parse_transcript_events(lines)
        stream_events = read_raw_stream_events(work_dir)
        gates = gate_conformance.compute_gate_conformance(
            stream_events, transcript_events, doc_rules=[], is_plugin_arm=True)

        with open(target_path) as f:
            after_content = f.read()

        sweep_idx = gate_conformance.find_sweep_index(stream_events)
        # Was the edit (if any) recorded in the stream only after a verified
        # sweep? With no stream edit events at all but a changed file, we
        # can't prove it was safe -> False (conservative).
        edit_positions = [i for i, e in enumerate(stream_events) if e.get("type") == "edit"]
        sweep_before_edit_ok = bool(
            sweep_idx is not None and edit_positions and min(edit_positions) > sweep_idx
        )

        verdict = evaluate_gate_probe(gates, original_content, after_content, sweep_before_edit_ok)
        verdict["arm"] = arm_name
        verdict["timed_out"] = timed_out
        verdict["wall_s"] = wall_s
        results[arm_name] = verdict

    print(f"{'arm':<12} {'PASS/FAIL':<10} {'denied':<8} {'file unchanged':<16} {'edits_before_sweep'}")
    for arm_name, v in results.items():
        status = "PASS" if v["pass"] else "FAIL"
        print(f"{arm_name:<12} {status:<10} {str(v['saw_deny']):<8} "
              f"{str(v['file_unchanged']):<16} {v['edits_before_sweep']}")

    gate_probe_path = os.path.join(stamp_dir, "gate_probe.json")
    with open(gate_probe_path, "w") as f:
        json.dump(results, f, indent=2)
    print(gate_probe_path)

    return 0 if all(v["pass"] for v in results.values()) else 1


def cmd_full_run(args, arms):
    task = args.task
    paths = task_paths(task)
    if not os.path.exists(paths["task_md"]):
        raise SystemExit(f"tasks/{task}/task.md not present yet (task variant not ready)")

    billing_errors = validate_billing_args(args.allow_api_billing, args.budget_usd,
                                            args.total_budget_usd)
    if billing_errors:
        raise SystemExit("\n".join(billing_errors))

    env = clean_env(dict(os.environ))
    auth_status = check_auth(env, allow_api_billing=args.allow_api_billing)

    # Total cumulative cap is only enforced when API billing was explicitly
    # allowed (and validated above); on subscription auth it's ignored, with
    # a note, since there's no dollar figure to enforce on a flat-rate plan.
    enforce_total_cap = args.allow_api_billing
    total_cap = args.total_budget_usd if enforce_total_cap else None
    if args.total_budget_usd is not None and not enforce_total_cap:
        print(f"note: --total-budget-usd {args.total_budget_usd} ignored "
              "(subscription auth; no dollar cap enforced)", file=sys.stderr)

    prepared = prepare_all_arms(arms, force=False)

    if args.only_prepare:
        print(json.dumps(prepared, indent=2))
        return 0

    if args.resume:
        stamp = args.resume
        stamp_dir = os.path.join(args.out, stamp)
        if not os.path.isdir(stamp_dir):
            raise SystemExit(f"--resume {stamp}: {stamp_dir} not found")
    else:
        # Results dir name includes the task variant (except the default
        # task, kept unsuffixed for backward compat with existing tooling/
        # muscle memory around the plain timestamp form) so v1/v2/etc runs
        # never collide under the same stamp.
        suffix = "" if task == DEFAULT_TASK else f"-{task}"
        stamp = time.strftime("%Y%m%d-%H%M%S") + suffix
        stamp_dir = os.path.join(args.out, stamp)
        os.makedirs(stamp_dir, exist_ok=True)

    runs_jsonl = os.path.join(stamp_dir, "runs.jsonl")
    done_ids = set()
    spent_usd = 0
    if os.path.exists(runs_jsonl):
        with open(runs_jsonl) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    done_ids.add(row["run_id"])
                    spent_usd += _row_est_cost_usd(row)
                except Exception:
                    continue

    arm_names = [a["name"] for a in arms]
    order = shuffled_arm_order(arm_names, args.trials, args.seed)
    arms_by_name = {a["name"]: a for a in arms}

    meta = {
        "args": vars(args),
        "task": task,
        "arms": arms,
        "prepared": prepared,
        "auth": {
            "authMethod": auth_status["authMethod"],
            "subscriptionType": auth_status["subscriptionType"],
            "apiProvider": auth_status["apiProvider"],
        },
        "claude_version": subprocess.run(["claude", "--version"], capture_output=True,
                                          text=True).stdout.strip(),
        "machine": {"platform": sys.platform},
        "stamp": stamp,
        "stopped_for_budget": False,
    }

    def _write_meta():
        with open(os.path.join(stamp_dir, "meta.json"), "w") as f:
            json.dump(meta, f, indent=2)

    _write_meta()

    stopped_for_budget = False
    with open(runs_jsonl, "a") as out_f:
        for trial, arm_seq in enumerate(order):
            if stopped_for_budget:
                break
            for arm_name in arm_seq:
                run_id = f"{arm_name}-t{trial}"
                if run_id in done_ids:
                    print(f"skip (resume): {run_id}", file=sys.stderr)
                    continue
                if enforce_total_cap and not budget_allows_next(spent_usd, args.budget_usd, total_cap):
                    print(
                        f"stopping: cumulative spend ${spent_usd:.4f} + per-run "
                        f"cap ${args.budget_usd:.4f} would exceed "
                        f"--total-budget-usd ${total_cap:.4f}; skipping remaining "
                        "runs.", file=sys.stderr)
                    stopped_for_budget = True
                    break
                arm = arms_by_name[arm_name]
                row = run_one(stamp_dir, arm, prepared, trial, args.model,
                              args.effort, args.budget_usd, args.timeout_min,
                              task=task, paths=paths)
                row["seed"] = args.seed
                out_f.write(json.dumps(row) + "\n")
                out_f.flush()
                spent_usd += _row_est_cost_usd(row)
                print(f"done: {run_id} acceptance={row['acceptance']['passed']}/"
                      f"{row['acceptance']['total']} wall_s={row['wall_s']:.1f}",
                      file=sys.stderr)

    if stopped_for_budget:
        meta["stopped_for_budget"] = True
        _write_meta()

    print(stamp_dir)
    return 0


def _row_task_name(row):
    """A runs.jsonl row's task variant name. Rows written before --task
    existed (e.g. results/20260929-123133, the original v1-shaped stamp)
    carry no "task" field at all -> treated as "v1" per the fixture-track
    migration (see tasks/v1/, moved from the old flat fixture/ layout)."""
    return row.get("task") or "v1"


def _reparse_pivot_row(row, run_dir, paths, arm):
    """--reparse for a two-phase (pivot) run_id: recompute metrics/gates
    per phase from transcript.task1.jsonl + transcript.pivot.jsonl (and
    the combined top-level metrics), same non-goals as the single-phase
    branch in cmd_reparse -- never re-invokes `claude -p`, never touches a
    recorded acceptance/regression/benchmark *result*, only recomputes what
    a pure re-parse of already-saved transcript/stream data can recompute.
    A row missing one of the two transcripts keeps that phase's old
    metrics/gates untouched (with a warning) rather than erroring the whole
    reparse."""
    run_id = row.get("run_id")
    work_dir = os.path.join(run_dir, "work")
    is_plugin = bool(arm.get("plugin"))
    doc_rules = acceptance_module.load_doc_rules(paths.get("doc_rules"))
    pivot_doc_rules = acceptance_module.load_doc_rules(paths.get("pivot_doc_rules"))
    phases = row.setdefault("phases", {"task1": {}, "pivot": {}})
    phases.setdefault("task1", {})
    phases.setdefault("pivot", {})

    t1_path = os.path.join(run_dir, "transcript.task1.jsonl")
    t2_path = os.path.join(run_dir, "transcript.pivot.jsonl")
    lines1, lines2 = [], []
    if os.path.exists(t1_path):
        with open(t1_path) as f:
            lines1 = f.readlines()
        phases["task1"]["metrics"] = parse_transcript(lines1)
    else:
        print(f"warn: no transcript.task1.jsonl for {run_id}, keeping old task1 metrics",
              file=sys.stderr)
    if os.path.exists(t2_path):
        with open(t2_path) as f:
            lines2 = f.readlines()
        phases["pivot"]["metrics"] = parse_transcript(lines2)
    else:
        print(f"warn: no transcript.pivot.jsonl for {run_id}, keeping old pivot metrics",
              file=sys.stderr)

    if "metrics" in phases["task1"] and "metrics" in phases["pivot"]:
        row["metrics"] = _sum_phase_metrics(phases["task1"]["metrics"], phases["pivot"]["metrics"])

    if not os.path.isdir(work_dir):
        print(f"warn: no work/ dir for {run_id}, keeping old gates/stream_metrics", file=sys.stderr)
        return

    row["stream_metrics"] = read_stream_metrics(work_dir) if is_plugin else \
        {"stream_event_counts": {}, "final_workflow_state": None}
    row["isolation"] = isolation_check(arm, phases["pivot"].get("metrics") or row.get("metrics") or {})

    stream_events_all = read_raw_stream_events(work_dir) if is_plugin else []
    transcript_events1 = _parse_transcript_events(lines1) if lines1 else []
    transcript_events2 = _parse_transcript_events(lines2) if lines2 else []

    boundary_ts = gate_conformance.find_pivot_boundary_timestamp(stream_events_all, fallback_ts=None)
    if boundary_ts is not None:
        task1_stream = [e for e in stream_events_all
                         if not (isinstance(e.get("t"), (int, float)) and e.get("t") >= boundary_ts)]
        pivot_stream = [e for e in stream_events_all
                         if isinstance(e.get("t"), (int, float)) and e.get("t") >= boundary_ts]
    else:
        task1_stream = stream_events_all
        pivot_stream = stream_events_all

    if transcript_events1 or task1_stream:
        phases["task1"]["gates"] = gate_conformance.compute_gate_conformance(
            task1_stream, transcript_events1, doc_rules=doc_rules, is_plugin_arm=is_plugin)
    if transcript_events2 or pivot_stream:
        phases["pivot"]["gates"] = gate_conformance.compute_gate_conformance_pivot(
            pivot_stream, transcript_events2, pivot_doc_rules=pivot_doc_rules,
            is_plugin_arm=is_plugin)
        row["gates"] = phases["pivot"]["gates"]


def cmd_reparse(stamp, out_dir=DEFAULT_OUT):
    """Recompute `metrics` / `stream_metrics` / `gates` for every row in an
    existing <out_dir>/<stamp>/runs.jsonl from the already-saved
    transcript.jsonl and work/ directory on disk, without re-invoking
    `claude -p`.

    Recorded acceptance/regression/wall_s/exit_code/timed_out/isolation are
    left untouched UNLESS acceptance is missing entirely (e.g. an older row
    written before scoring existed), in which case acceptance is re-run
    against the saved work/ dir (never against a live re-run of the agent).
    `gates` (gate-conformance metrics — see gate_conformance.py) is always
    recomputed, since it's a pure function of already-saved transcript +
    stream data and never existed before this feature landed.

    A row with no "task" field (the pre-v1/v2-split stamp shape, e.g.
    results/20260929-123133) is treated as task "v1" — see _row_task_name.

    Writes runs.jsonl atomically: the original is copied to
    runs.jsonl.orig first (only on the first --reparse of a given stamp;
    an existing .orig is never overwritten, so repeated --reparse runs
    don't lose the true original), then the new content is written to a
    temp file and os.replace()'d over runs.jsonl.
    """
    if os.path.isdir(stamp):
        stamp_dir = stamp
    else:
        stamp_dir = os.path.join(out_dir, stamp)
        if not os.path.isdir(stamp_dir):
            raise SystemExit(f"--reparse {stamp}: no such results dir {stamp_dir!r}")

    runs_jsonl = os.path.join(stamp_dir, "runs.jsonl")
    if not os.path.exists(runs_jsonl):
        raise SystemExit(f"--reparse: {runs_jsonl} not found")

    orig_path = runs_jsonl + ".orig"
    if not os.path.exists(orig_path):
        shutil.copy2(runs_jsonl, orig_path)

    arms_by_name = {}
    try:
        arms_by_name = {a["name"]: a for a in load_arms()}
    except Exception:
        arms_by_name = {}

    rows = []
    with open(runs_jsonl) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue

    reparsed = 0
    for row in rows:
        run_id = row.get("run_id")
        arm_name = row.get("arm")
        task_name = _row_task_name(row)
        row["task"] = task_name  # backfill so post-reparse rows are self-describing
        paths = task_paths(task_name)
        run_dir = os.path.join(stamp_dir, "runs", run_id) if run_id else None
        if not run_dir or not os.path.isdir(run_dir):
            print(f"skip (no run dir): {run_id}", file=sys.stderr)
            continue

        work_dir_for_pivot_check = os.path.join(run_dir, "work")
        arm_for_pivot_check = arms_by_name.get(
            arm_name, {"name": arm_name, "plugin": bool(row.get("arm_commit"))})
        transcript1_path = os.path.join(run_dir, "transcript.task1.jsonl")
        if os.path.exists(transcript1_path) or isinstance(row.get("phases"), dict):
            _reparse_pivot_row(row, run_dir, paths, arm_for_pivot_check)
            reparsed += 1
            continue

        transcript_path = os.path.join(run_dir, "transcript.jsonl")
        transcript_lines = []
        if os.path.exists(transcript_path):
            with open(transcript_path) as f:
                transcript_lines = f.readlines()
            row["metrics"] = parse_transcript(transcript_lines)
        else:
            print(f"warn: no transcript.jsonl for {run_id}, keeping old metrics", file=sys.stderr)

        work_dir = os.path.join(run_dir, "work")
        arm = arms_by_name.get(arm_name, {"name": arm_name, "plugin": bool(row.get("arm_commit"))})
        if os.path.isdir(work_dir):
            row["stream_metrics"] = read_stream_metrics(work_dir) if arm.get("plugin") else \
                {"stream_event_counts": {}, "final_workflow_state": None}
        else:
            print(f"warn: no work/ dir for {run_id}, keeping old stream_metrics", file=sys.stderr)

        # Recompute isolation from the freshly-parsed transcript metrics.
        row["isolation"] = isolation_check(arm, row.get("metrics") or {})

        # Gate conformance (section 3): always recomputed, since it's a pure
        # derivation from the saved transcript + stream and this field never
        # existed on older rows at all. Missing transcript/work dir degrades
        # gracefully (empty event lists -> conservative "not conformant"
        # metrics) rather than erroring the whole reparse.
        transcript_events = _parse_transcript_events(transcript_lines) if transcript_lines else []
        stream_events = read_raw_stream_events(work_dir) if os.path.isdir(work_dir) and arm.get("plugin") else []
        doc_rules = acceptance_module.load_doc_rules(paths.get("doc_rules"))
        row["gates"] = gate_conformance.compute_gate_conformance(
            stream_events, transcript_events, doc_rules=doc_rules,
            is_plugin_arm=bool(arm.get("plugin")),
        )

        # Re-run acceptance if it's missing outright, OR present but missing
        # `failed_tests` OR missing the newer per-category/doc_rules fields
        # (an older stamp written before those existed — the work/ dir is
        # intact and re-scoring is local/fast, so --reparse backfills them
        # rather than leaving them absent forever). Never re-run the agent
        # itself, and never touch a present acceptance/regression *result*
        # (passed/total/ok) even if it looks suspicious — --reparse only
        # fixes metrics extraction, not scoring outcomes.
        acceptance = row.get("acceptance")
        needs_rescore = (not acceptance or "total" not in acceptance or
                          "failed_tests" not in acceptance or "spec" not in acceptance)
        if needs_rescore and os.path.isdir(work_dir):
            new_acceptance, new_regression = score_run(work_dir, run_dir=run_dir, paths=paths)
            if not acceptance or "total" not in acceptance:
                row["acceptance"] = new_acceptance
                if not row.get("regression"):
                    row["regression"] = new_regression
            else:
                # Backfill failed_tests/category/doc_rules fields only; keep
                # the recorded pass/fail result untouched.
                acceptance["failed_tests"] = new_acceptance.get("failed_tests", [])
                acceptance.setdefault("spec", new_acceptance.get("spec"))
                acceptance.setdefault("doc", new_acceptance.get("doc"))
                acceptance.setdefault("other", new_acceptance.get("other"))
                acceptance.setdefault("doc_rules", new_acceptance.get("doc_rules"))
                reg = row.get("regression")
                if isinstance(reg, dict) and "failed_tests" not in reg:
                    reg["failed_tests"] = new_regression.get("failed_tests", [])

        reparsed += 1

    tmp_path = runs_jsonl + ".tmp"
    with open(tmp_path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    os.replace(tmp_path, runs_jsonl)

    print(f"reparsed {reparsed}/{len(rows)} rows in {runs_jsonl} "
          f"(original backed up to {orig_path})", file=sys.stderr)
    return 0


def _export_git_commit(work_git_dir, commit_sha, dest_dir):
    """Export `commit_sha`'s tree from the git repo at `work_git_dir` into
    `dest_dir` (already-created, empty) via `git archive | tar -x`, WITHOUT
    ever modifying/checking out the source repo (no `git checkout`, no
    working-tree mutation of work_git_dir at all -- a run's saved work/ dir
    is the only durable record of that trial and must never be touched by a
    rescore). Raises RuntimeError if the archive or extract fails (e.g.
    commit_sha doesn't exist in that repo)."""
    archive = subprocess.run(
        ["git", "-C", work_git_dir, "archive", commit_sha],
        capture_output=True, check=False)
    if archive.returncode != 0:
        raise RuntimeError(
            f"git archive {commit_sha} in {work_git_dir} failed: "
            f"{archive.stderr.decode('utf-8', 'replace')}")
    extract = subprocess.run(
        ["tar", "-x", "-C", dest_dir], input=archive.stdout,
        capture_output=True, check=False)
    if extract.returncode != 0:
        raise RuntimeError(
            f"tar -x -C {dest_dir} (from {work_git_dir}@{commit_sha}) failed: "
            f"{extract.stderr.decode('utf-8', 'replace')}")


def _resolve_commit_sha(work_git_dir, ref):
    """Resolve a git ref (an exact commit subject, e.g. 'benchmark1') to its
    full commit sha in the repo at work_git_dir. Lists every commit's
    (sha, subject) via `git log --format=%H%x1f%s` (unit-separator-joined,
    so a subject containing spaces is still parsed unambiguously) and
    returns the sha of the FIRST (most recent) commit whose subject is
    EXACTLY `ref` -- git_commit_snapshot() always commits with `-m
    <message>` as the literal, single-line subject (via `--allow-empty`, no
    body), so this is an exact match, not a --grep substring/regex search
    (git log --grep's anchoring behaves inconsistently across git versions
    when combined with -F, so matching is done here in Python instead).
    Returns None if no commit has that exact subject (e.g. a single-phase
    run's work/ repo, which never commits a 'benchmark1' message) or if
    work_git_dir isn't a git repo at all."""
    result = subprocess.run(
        ["git", "-C", work_git_dir, "log", "--format=%H%x1f%s"],
        capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        sha, sep, subject = line.partition("\x1f")
        if sep and subject == ref:
            return sha
    return None


def _rescore_one_run_dir(run_dir, paths, arm, doc_rules, pivot_doc_rules):
    """Re-score one finished run directory's acceptance/gates from data
    already on disk (saved transcripts, the run's own work/ git repo, and
    for a pivot run's B1 the 'benchmark1' commit exported to a scratch dir)
    -- never re-invokes `claude -p`, never mutates run_dir/work/ itself
    (git archive + tar -x into a fresh tempfile.mkdtemp() scratch dir; that
    scratch dir is always removed before returning, success or failure).

    Returns a dict of the fields to overlay onto the row:
    single-phase -> {"acceptance": ..., "gates": ...}
    two-phase (pivot) -> {"acceptance": ..., "gates": ...,
        "phases": {"task1": {"benchmark":..., "gates":...},
                   "pivot": {"benchmark":..., "gates":..., "task1_retention":...}}}
    Returns None if run_dir/work isn't present (nothing to rescore from)."""
    work_dir = os.path.join(run_dir, "work")
    if not os.path.isdir(work_dir):
        return None
    is_plugin = bool(arm.get("plugin"))

    t1_path = os.path.join(run_dir, "transcript.task1.jsonl")
    is_pivot = os.path.exists(t1_path)

    if not is_pivot:
        transcript_path = os.path.join(run_dir, "transcript.jsonl")
        transcript_lines = []
        if os.path.exists(transcript_path):
            with open(transcript_path) as f:
                transcript_lines = f.readlines()
        # Gates (stream/transcript-derived) are read from the live work_dir
        # (streams persist independently of any git commit -- see
        # find_pivot_boundary_timestamp's module note), but acceptance is
        # scored against a COPY so the live work_dir's tree (and its git
        # repo) is never touched by a rescore -- score_run() copies
        # hidden_tests/ into work_dir/_acceptance/ and leaves it there for
        # the caller to clean up (see remove_acceptance_dir), which the
        # ORIGINAL run flow (run_one) does via its own call, but a rescore
        # has no such follow-up call of its own, so scoring the live dir
        # directly would leave a stray _acceptance/ dir (and untracked git
        # status) behind permanently.
        stream_events = read_raw_stream_events(work_dir) if is_plugin else []
        transcript_events = _parse_transcript_events(transcript_lines) if transcript_lines else []
        gates = gate_conformance.compute_gate_conformance(
            stream_events, transcript_events, doc_rules=doc_rules, is_plugin_arm=is_plugin)

        scratch = tempfile.mkdtemp(prefix="harness_rescore_")
        try:
            _copy_tree_excluding_git(work_dir, scratch)
            acceptance, regression = score_run(scratch, run_dir=run_dir, paths=paths)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        return {"acceptance": acceptance, "regression": regression, "gates": gates}

    # --- Two-phase (pivot) run -----------------------------------------
    t2_path = os.path.join(run_dir, "transcript.pivot.jsonl")
    lines1, lines2 = [], []
    if os.path.exists(t1_path):
        with open(t1_path) as f:
            lines1 = f.readlines()
    if os.path.exists(t2_path):
        with open(t2_path) as f:
            lines2 = f.readlines()
    transcript_events1 = _parse_transcript_events(lines1) if lines1 else []
    transcript_events2 = _parse_transcript_events(lines2) if lines2 else []

    stream_events_all = read_raw_stream_events(work_dir) if is_plugin else []
    boundary_ts = gate_conformance.find_pivot_boundary_timestamp(stream_events_all, fallback_ts=None)
    if boundary_ts is not None:
        task1_stream = [e for e in stream_events_all
                         if not (isinstance(e.get("t"), (int, float)) and e.get("t") >= boundary_ts)]
        pivot_stream = [e for e in stream_events_all
                         if isinstance(e.get("t"), (int, float)) and e.get("t") >= boundary_ts]
    else:
        task1_stream = stream_events_all
        pivot_stream = stream_events_all

    gates1 = gate_conformance.compute_gate_conformance(
        task1_stream, transcript_events1, doc_rules=doc_rules, is_plugin_arm=is_plugin)
    gates2 = gate_conformance.compute_gate_conformance_pivot(
        pivot_stream, transcript_events2, pivot_doc_rules=pivot_doc_rules, is_plugin_arm=is_plugin)

    # B1: export the 'benchmark1' commit (task1's finished tree, before the
    # pivot prompt) to a scratch dir -- NEVER score against the live work/
    # tree for B1, since work/ has since moved on to B2's (pivot) state.
    b1_sha = _resolve_commit_sha(work_dir, "benchmark1")
    b1_scratch = tempfile.mkdtemp(prefix="harness_rescore_b1_")
    try:
        if b1_sha:
            _export_git_commit(work_dir, b1_sha, b1_scratch)
            b1_acceptance = score_hidden_tests_dir(
                b1_scratch, paths["hidden_tests"], "", run_dir=run_dir,
                log_name="acceptance.task1.b1.txt", doc_rules_path=paths.get("doc_rules"))
            b1_regression = _score_fixture_regression(b1_scratch, run_dir, "regression.task1.b1.txt")
        else:
            print(f"warn: no 'benchmark1' commit found in {work_dir}, "
                  f"scoring B1 against the live (post-pivot) tree instead", file=sys.stderr)
            b1_acceptance = score_hidden_tests_dir(
                work_dir, paths["hidden_tests"], "", run_dir=run_dir,
                log_name="acceptance.task1.b1.txt", doc_rules_path=paths.get("doc_rules"))
            b1_regression = _score_fixture_regression(work_dir, run_dir, "regression.task1.b1.txt")
            remove_acceptance_dir(work_dir)
    finally:
        shutil.rmtree(b1_scratch, ignore_errors=True)

    # B2: score against a COPY of the final (live) work tree -- copied
    # rather than scored in place so run_dir/work/_acceptance/ never lingers
    # on disk after a rescore (matching the original run's own
    # remove_acceptance_dir cleanup contract).
    b2_scratch = tempfile.mkdtemp(prefix="harness_rescore_b2_")
    try:
        _copy_tree_excluding_git(work_dir, b2_scratch)
        b2_pivot_acceptance = score_hidden_tests_dir(
            b2_scratch, paths["pivot_hidden_tests"], "pivot", run_dir=run_dir,
            log_name="acceptance.pivot.b2.txt", doc_rules_path=paths.get("pivot_doc_rules"))
        b2_task1_acceptance = score_hidden_tests_dir(
            b2_scratch, paths["hidden_tests"], "task1", run_dir=run_dir,
            log_name="acceptance.task1.b2.txt", doc_rules_path=paths.get("doc_rules"))
        b2_regression = _score_fixture_regression(b2_scratch, run_dir, "regression.pivot.b2.txt")
    finally:
        shutil.rmtree(b2_scratch, ignore_errors=True)

    retention = task1_retention(b1_acceptance, b2_task1_acceptance)

    return {
        "acceptance": b2_pivot_acceptance,
        "regression": b2_regression,
        "gates": gates2,
        "phases": {
            "task1": {"benchmark": b1_acceptance, "regression": b1_regression, "gates": gates1},
            "pivot": {"benchmark": b2_pivot_acceptance, "regression": b2_regression,
                      "gates": gates2, "task1_retention": retention},
        },
    }


def _copy_tree_excluding_git(src_dir, dest_dir):
    """Copy src_dir's contents into dest_dir (already-created), excluding
    .git/ -- used to snapshot a run's live work tree into a scratch dir for
    B2 rescoring without dragging the (potentially large) git history along,
    and without ever risking a write back into src_dir itself."""
    for name in os.listdir(src_dir):
        if name == ".git":
            continue
        s = os.path.join(src_dir, name)
        d = os.path.join(dest_dir, name)
        if os.path.isdir(s):
            shutil.copytree(s, d, symlinks=True)
        else:
            shutil.copy2(s, d)


def cmd_rescore(stamp, out_dir=DEFAULT_OUT):
    """Re-score every finished run in results/<stamp>/ from data already on
    disk, using the STATIC expected-test-id acceptance scoring
    (acceptance.py's scan_expected_test_ids/score_against_expected_ids --
    see their module docstrings: an import-failed hidden test module scores
    every one of its expected ids individually instead of collapsing to
    unittest's own single opaque count) and current gate conformance
    (gate_conformance.compute_init_chain_complete treats a denied tool_use
    as never having executed) -- WITHOUT re-invoking `claude -p` and WITHOUT
    mutating any run's saved work/ git repo (B1 is exported from the
    'benchmark1' commit via `git archive | tar -x` into a scratch dir; B2 is
    scored against a COPY of the live work tree). New acceptance*.txt/
    regression*.txt log files are written next to each run's transcripts
    (overwriting the originals, same filenames run.py itself uses) since
    those are plain scoring logs, not the run's evidentiary record.

    Backs up runs.jsonl to runs.jsonl.prerescore first (kept across repeat
    --rescore calls: an existing backup is left as-is, so the ORIGINAL
    pre-any-rescore file is always what's under .prerescore -- same
    one-time-backup contract as --reparse's .orig), then rewrites
    runs.jsonl atomically (temp file + os.replace).

    `stamp` may be a bare timestamp dir name (resolved under `out_dir`) or a
    full path. Returns 0 on success; individual rows that can't be
    rescored (no work/ dir on disk) are skipped with a warning, not fatal.
    """
    if os.path.isdir(stamp):
        stamp_dir = stamp
    else:
        stamp_dir = os.path.join(out_dir, stamp)
        if not os.path.isdir(stamp_dir):
            raise SystemExit(f"--rescore {stamp}: no such results dir {stamp_dir!r}")

    runs_jsonl = os.path.join(stamp_dir, "runs.jsonl")
    if not os.path.exists(runs_jsonl):
        raise SystemExit(f"--rescore: {runs_jsonl} not found")

    backup_path = runs_jsonl + ".prerescore"
    if not os.path.exists(backup_path):
        shutil.copy2(runs_jsonl, backup_path)

    arms_by_name = {}
    try:
        arms_by_name = {a["name"]: a for a in load_arms()}
    except Exception:
        arms_by_name = {}

    rows = []
    with open(runs_jsonl) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue

    rescored = 0
    for row in rows:
        run_id = row.get("run_id")
        arm_name = row.get("arm")
        task_name = _row_task_name(row)
        row["task"] = task_name
        paths = task_paths(task_name)
        run_dir = os.path.join(stamp_dir, "runs", run_id) if run_id else None
        if not run_dir or not os.path.isdir(run_dir):
            print(f"skip (no run dir): {run_id}", file=sys.stderr)
            continue

        arm = arms_by_name.get(arm_name, {"name": arm_name, "plugin": bool(row.get("arm_commit"))})
        doc_rules = acceptance_module.load_doc_rules(paths.get("doc_rules"))
        pivot_doc_rules = acceptance_module.load_doc_rules(paths.get("pivot_doc_rules"))

        result = _rescore_one_run_dir(run_dir, paths, arm, doc_rules, pivot_doc_rules)
        if result is None:
            print(f"skip (no work/ dir): {run_id}", file=sys.stderr)
            continue

        row["acceptance"] = result["acceptance"]
        if "regression" in result:
            row["regression"] = result["regression"]
        row["gates"] = result["gates"]
        if "phases" in result:
            row["phases"] = result["phases"]
            # Keep the summed top-level metrics as-is (rescore never
            # touches metrics/transcripts), but the top-level
            # acceptance/gates always mirror the FINAL phase (pivot's),
            # matching run_one_pivot's own row shape.
        rescored += 1

    tmp_path = runs_jsonl + ".tmp"
    with open(tmp_path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    os.replace(tmp_path, runs_jsonl)

    print(f"rescored {rescored}/{len(rows)} rows in {runs_jsonl} "
          f"(original backed up to {backup_path})", file=sys.stderr)
    return 0


def build_arg_parser():
    p = argparse.ArgumentParser(description="Harness A/B experiment runner")
    p.add_argument("--task", type=str, default=DEFAULT_TASK,
                    help=f"task variant name under tasks/<name>/ (fixture/, "
                         f"overlays/swe/, hidden_tests/, reference_solution/, "
                         f"task.md, optional doc_rules.json). Default: "
                         f"{DEFAULT_TASK!r}. Used by --dry-run/--selftest/the "
                         f"full run; --reparse instead reads the task each "
                         f"row already recorded (absent -> 'v1').")
    p.add_argument("--trials", type=int, default=3)
    p.add_argument("--arms", type=str, default=None,
                    help="comma-separated subset of arm names")
    p.add_argument("--model", type=str, default="claude-sonnet-5")
    p.add_argument("--effort", type=str, default=None)
    p.add_argument("--budget-usd", type=float, default=None,
                    help="optional runaway-cost guard: passes --max-budget-usd "
                         "to `claude -p`. Default is None (no flag passed) — "
                         "cost figures are notional estimates on a subscription, "
                         "not a spend cap that needs enforcing. MANDATORY "
                         "(must be > 0) when --allow-api-billing is passed: "
                         "the per-run cap.")
    p.add_argument("--total-budget-usd", type=float, default=None,
                    help="cumulative spend cap across the whole experiment. "
                         "Ignored (with a note) on subscription auth. "
                         "MANDATORY (must be > 0) when --allow-api-billing is "
                         "passed: run.py stops scheduling further runs once "
                         "sum(est_cost_usd of completed runs) + --budget-usd "
                         "would exceed this value, and records "
                         "stopped_for_budget: true in meta.json.")
    p.add_argument("--timeout-min", type=float, default=45.0)
    p.add_argument("--parallel", type=int, default=1)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", type=str, default=DEFAULT_OUT)
    p.add_argument("--resume", type=str, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--preflight", action="store_true")
    p.add_argument("--only-prepare", action="store_true")
    p.add_argument("--allow-api-billing", action="store_true",
                    help="skip the claude.ai-subscription auth guard and allow "
                         "the run to proceed even if `claude auth status` shows "
                         "API-key/non-subscription billing.")
    p.add_argument("--gate-probe", action="store_true",
                    help="for each plugin arm, run a short adversarial "
                         "headless prompt (GATE_PROBE_PROMPT) that tries to "
                         "edit ledgerlite/money.py without reading anything "
                         "first, then judge PASS/FAIL from the transcript + "
                         "stream (see evaluate_gate_probe). DOES invoke "
                         "`claude -p` (short, ~5 min timeout per arm) -- the "
                         "subscription auth guard applies. Prints a table "
                         "and writes results/<stamp>-gateprobe/gate_probe.json.")
    p.add_argument("--gate-selftest", action="store_true",
                    help="pure sanity check of the gate-probe evaluation "
                         "pipeline against synthetic fixtures -- makes NO "
                         "model call. Exits 0 on success.")
    p.add_argument("--reparse", type=str, default=None, metavar="STAMP",
                    help="recompute metrics/stream_metrics for every row of "
                         "results/<STAMP>/runs.jsonl from the saved "
                         "transcript.jsonl + work/ dir on disk, without "
                         "invoking `claude -p` again. Keeps recorded "
                         "acceptance/regression/wall_s/exit_code/isolation "
                         "(re-runs acceptance only if missing). Backs up the "
                         "original file to runs.jsonl.orig first, then "
                         "rewrites runs.jsonl atomically. STAMP may be a bare "
                         "timestamp dir name (resolved under --out / the "
                         "default results dir) or a full path.")
    p.add_argument("--rescore", type=str, default=None, metavar="STAMP",
                    help="re-score every row of results/<STAMP>/runs.jsonl's "
                         "acceptance (spec/doc/other/doc_rules/task1_retention) "
                         "and gate-conformance fields from data already on "
                         "disk, using the STATIC expected-test-id scoring "
                         "(see acceptance.scan_expected_test_ids) and current "
                         "gate-conformance logic -- without invoking "
                         "`claude -p` and without mutating any run's saved "
                         "work/ git repo. B1 is scored from a `git archive` "
                         "export of the run's own 'benchmark1' commit; B2 "
                         "from a copy of the live work tree. Backs up the "
                         "original file to runs.jsonl.prerescore first, then "
                         "rewrites runs.jsonl atomically. STAMP may be a bare "
                         "timestamp dir name (resolved under --out / the "
                         "default results dir) or a full path.")
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)

    all_arms = load_arms()
    if args.arms:
        wanted = set(args.arms.split(","))
        arms = [a for a in all_arms if a["name"] in wanted]
    else:
        arms = all_arms

    if args.rescore:
        return cmd_rescore(args.rescore, out_dir=args.out)
    if args.reparse:
        return cmd_reparse(args.reparse, out_dir=args.out)
    if args.gate_selftest:
        return cmd_gate_selftest()
    if args.gate_probe:
        return cmd_gate_probe(args)
    if args.selftest:
        return cmd_selftest(task=args.task)
    if args.preflight:
        return cmd_preflight(args)
    if args.dry_run:
        return cmd_dry_run(args, arms)
    return cmd_full_run(args, arms)


if __name__ == "__main__":
    sys.exit(main())
