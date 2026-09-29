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
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
ARMS_JSON = os.path.join(HERE, "arms.json")
FIXTURE_DIR = os.path.join(HERE, "fixture")
OVERLAY_SWE_DIR = os.path.join(HERE, "overlays", "swe")
HIDDEN_TESTS_DIR = os.path.join(HERE, "hidden_tests")
REFERENCE_SOLUTION_DIR = os.path.join(HERE, "reference_solution")
TASK_MD = os.path.join(HERE, "task.md")
WORK_ROOT = os.path.join(HERE, ".work")
ARMS_WORK_DIR = os.path.join(WORK_ROOT, "arms")
DEFAULT_OUT = os.path.join(HERE, "results")

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


def build_command(task_text, model, budget_usd, plugin_dir=None, effort=None):
    """Build the `claude -p ...` argv list (no shell).

    budget_usd is optional (None by default at the CLI level): when None,
    no --max-budget-usd flag is passed at all — cost figures are notional
    estimates on a subscription, not a spend cap that needs enforcing. Pass
    a number to add an optional runaway-cost guard.
    """
    cmd = [
        "claude", "-p", task_text,
        "--output-format", "stream-json",
        "--verbose",
        "--model", model,
        "--setting-sources", "project,local",
        "--dangerously-skip-permissions",
        "--no-session-persistence",
    ]
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


def read_task_text():
    if not os.path.exists(TASK_MD):
        raise SystemExit(f"missing {TASK_MD} (fixture track not ready)")
    with open(TASK_MD) as f:
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


def make_run_workdir(run_dir, arm):
    work_dir = os.path.join(run_dir, "work")
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    shutil.copytree(FIXTURE_DIR, work_dir)
    if arm.get("plugin") and os.path.isdir(OVERLAY_SWE_DIR):
        _copy_overlay(OVERLAY_SWE_DIR, work_dir)
    _run(["git", "init", "-q"], cwd=work_dir)
    _run(["git", "-c", "user.name=harness-ab", "-c", "user.email=harness-ab@localhost",
          "add", "-A"], cwd=work_dir)
    _run(["git", "-c", "user.name=harness-ab", "-c", "user.email=harness-ab@localhost",
          "commit", "-qm", "fixture"], cwd=work_dir)
    return work_dir


def _copy_overlay(src, dst):
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        target_dir = os.path.join(dst, rel) if rel != "." else dst
        os.makedirs(target_dir, exist_ok=True)
        for fname in files:
            shutil.copy2(os.path.join(root, fname), os.path.join(target_dir, fname))


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


def run_unittest_dir(run_root, test_dir_rel, top_level, timeout_s=300):
    """Run `python3 -m unittest discover` and return (rc, stdout, stderr)."""
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", test_dir_rel,
           "-t", top_level, "-p", "test_*.py"]
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


def score_run(work_dir, run_dir=None):
    """Copy hidden tests -> _acceptance/, run acceptance + regression tests.

    When run_dir is given, also persists the raw stdout/stderr of each pass
    to <run_dir>/acceptance.txt and <run_dir>/regression.txt, and populates
    acceptance["failed_tests"] / regression["failed_tests"] (short test ids
    parsed from FAIL:/ERROR: summary lines)."""
    acceptance_dir = os.path.join(work_dir, "_acceptance")
    if os.path.isdir(HIDDEN_TESTS_DIR):
        if os.path.exists(acceptance_dir):
            shutil.rmtree(acceptance_dir)
        shutil.copytree(HIDDEN_TESTS_DIR, acceptance_dir)
        rc, out, err = run_unittest_dir(work_dir, "_acceptance", ".")
    else:
        rc, out, err = (-1, "", "hidden_tests/ not present")
    acceptance = parse_unittest_output(out + "\n" + err)
    acceptance["exit_code"] = rc
    acceptance["failed_tests"] = parse_failed_test_ids(out + "\n" + err)
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
            timeout_min, out_lock=None):
    arm_name = arm["name"]
    run_id = f"{arm_name}-t{trial}"
    run_dir = os.path.join(stamp_dir, "runs", run_id)
    os.makedirs(run_dir, exist_ok=True)

    work_dir = make_run_workdir(run_dir, arm)
    task_text = read_task_text()

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

    acceptance, regression = score_run(work_dir, run_dir=run_dir)
    stream_metrics = read_stream_metrics(work_dir) if arm.get("plugin") else \
        {"stream_event_counts": {}, "final_workflow_state": None}
    isolation = isolation_check(arm, metrics)

    row = {
        "run_id": run_id,
        "arm": arm_name,
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
        "acceptance": acceptance,
        "regression": regression,
        "isolation": isolation,
    }
    return row


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def cmd_selftest():
    if not os.path.isdir(FIXTURE_DIR) or not os.path.isdir(REFERENCE_SOLUTION_DIR):
        print("SELFTEST SKIP: fixture/ or reference_solution/ not present yet", file=sys.stderr)
        return 1
    if not os.path.isdir(HIDDEN_TESTS_DIR):
        print("SELFTEST SKIP: hidden_tests/ not present yet", file=sys.stderr)
        return 1

    tmp = os.path.join(WORK_ROOT, "selftest-" + uuid.uuid4().hex[:8])
    os.makedirs(tmp, exist_ok=True)
    work_dir = os.path.join(tmp, "work")
    shutil.copytree(FIXTURE_DIR, work_dir)
    _copy_overlay(REFERENCE_SOLUTION_DIR, work_dir)

    acceptance, regression = score_run(work_dir)
    print(json.dumps({"acceptance": acceptance, "regression": regression}, indent=2))

    ok = acceptance.get("ok") and acceptance.get("total", 0) > 0 and regression.get("ok")
    if not ok:
        print("SELFTEST FAILED", file=sys.stderr)
        return 1
    print("SELFTEST OK", file=sys.stderr)
    return 0


def cmd_dry_run(args, arms):
    if not os.path.exists(TASK_MD):
        print("DRY-RUN SKIP: task.md not present yet (fixture track not ready)", file=sys.stderr)
        return 1
    if not os.path.isdir(FIXTURE_DIR):
        print("DRY-RUN SKIP: fixture/ not present yet", file=sys.stderr)
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
    task_text = read_task_text()

    stamp = time.strftime("%Y%m%d-%H%M%S") + "-dryrun"
    stamp_dir = os.path.join(args.out, stamp)
    for arm in arms:
        arm_name = arm["name"]
        run_dir = os.path.join(stamp_dir, "runs", f"{arm_name}-t0")
        os.makedirs(run_dir, exist_ok=True)
        work_dir = make_run_workdir(run_dir, arm)
        plugin_dir = prepared[arm_name]["dir"] if arm.get("plugin") else None
        cmd = build_command(task_text, args.model, args.budget_usd,
                             plugin_dir=plugin_dir, effort=args.effort)
        print(f"=== {arm_name} ===")
        print(" ".join(cmd))

        if os.path.isdir(HIDDEN_TESTS_DIR):
            acceptance, regression = score_run(work_dir)
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


def cmd_full_run(args, arms):
    if not os.path.exists(TASK_MD):
        raise SystemExit("task.md not present yet (fixture track not ready)")

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
        stamp = time.strftime("%Y%m%d-%H%M%S")
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
                              args.effort, args.budget_usd, args.timeout_min)
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


def cmd_reparse(stamp, out_dir=DEFAULT_OUT):
    """Recompute `metrics` / `stream_metrics` for every row in an existing
    <out_dir>/<stamp>/runs.jsonl from the already-saved transcript.jsonl and
    work/ directory on disk, without re-invoking `claude -p`.

    Recorded acceptance/regression/wall_s/exit_code/timed_out/isolation are
    left untouched UNLESS acceptance is missing entirely (e.g. an older row
    written before scoring existed), in which case acceptance is re-run
    against the saved work/ dir (never against a live re-run of the agent).

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
        run_dir = os.path.join(stamp_dir, "runs", run_id) if run_id else None
        if not run_dir or not os.path.isdir(run_dir):
            print(f"skip (no run dir): {run_id}", file=sys.stderr)
            continue

        transcript_path = os.path.join(run_dir, "transcript.jsonl")
        if os.path.exists(transcript_path):
            with open(transcript_path) as f:
                lines = f.readlines()
            row["metrics"] = parse_transcript(lines)
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

        # Re-run acceptance if it's missing outright, OR present but missing
        # `failed_tests` (an older stamp written before that field existed —
        # the work/ dir is intact and re-scoring is local/fast, so --reparse
        # backfills it rather than leaving failed_tests absent forever).
        # Never re-run the agent itself, and never touch a present
        # acceptance/regression *result* (passed/total/ok) even if it looks
        # suspicious — --reparse only fixes metrics extraction, not scoring
        # outcomes.
        acceptance = row.get("acceptance")
        needs_rescore = (not acceptance or "total" not in acceptance or
                          "failed_tests" not in acceptance)
        if needs_rescore and os.path.isdir(work_dir):
            new_acceptance, new_regression = score_run(work_dir, run_dir=run_dir)
            if not acceptance or "total" not in acceptance:
                row["acceptance"] = new_acceptance
                if not row.get("regression"):
                    row["regression"] = new_regression
            else:
                # Backfill failed_tests only; keep the recorded pass/fail
                # result untouched.
                acceptance["failed_tests"] = new_acceptance.get("failed_tests", [])
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


def build_arg_parser():
    p = argparse.ArgumentParser(description="Harness A/B experiment runner")
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
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)

    all_arms = load_arms()
    if args.arms:
        wanted = set(args.arms.split(","))
        arms = [a for a in all_arms if a["name"] in wanted]
    else:
        arms = all_arms

    if args.reparse:
        return cmd_reparse(args.reparse, out_dir=args.out)
    if args.selftest:
        return cmd_selftest()
    if args.preflight:
        return cmd_preflight(args)
    if args.dry_run:
        return cmd_dry_run(args, arms)
    return cmd_full_run(args, arms)


if __name__ == "__main__":
    sys.exit(main())
