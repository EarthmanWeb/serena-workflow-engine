#!/usr/bin/env python3
"""Validate state-machine/states.json as a single declarative graph.

Usage:
    python3 scripts/validate-graph.py [--json]

Checks (errors -> exit 1, warnings -> exit 0):
  - Every state's own `transitions` dict targets match its transitionMatrix row
    (same set of states, ignoring the special "(return_to_caller)" sentinel).
  - Every matrix edge target is either a real state or the return-to-caller
    sentinel.
  - Every state is reachable from SessionStart.
  - Every non-terminal state has at least one outgoing edge.
  - Every memories/wf/WF_X.md doc is either a states.json node or a declared
    subflow, and vice versa (every subflow/state name that documents itself
    has a memory doc) — reported as errors, since a docless state or a
    stateless doc is exactly the drift this validator exists to catch.
  - Every cycle (self-loop or multi-node SCC) has at least one edge covered
    by loopCaps (WARNING only — an uncapped cycle is a smell, not a hard
    failure, since new cycles may be added before their cap is tuned).
  - Ranks are present on every state (ERROR if missing).
  - readAdvance pairs: for every ordered pair (a, b) where rank(b) > rank(a),
    report whether a->b is an actual matrix edge (info only — readAdvance
    never invents an edge; it only rides existing ones).

Prints a compact adjacency list either way.

Pure functions (validate_graph, find_unreachable, find_sccs, ...) take an
already-loaded dict so tests can run them against small synthetic graphs
without touching the filesystem.
"""
import argparse
import glob
import json
import os
import sys

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATES_JSON_PATH = os.path.join(PLUGIN_ROOT, 'state-machine', 'states.json')
WF_MEMORIES_GLOB = os.path.join(PLUGIN_ROOT, 'memories', 'wf', 'WF_*.md')

RETURN_TO_CALLER = "(return_to_caller)"


def load_states_doc(path=STATES_JSON_PATH):
    with open(path, 'r') as f:
        return json.load(f)


def list_wf_memory_names(pattern=WF_MEMORIES_GLOB):
    names = []
    for path in glob.glob(pattern):
        base = os.path.basename(path)
        if base.endswith('.md'):
            names.append(base[:-3])
    return sorted(names)


def build_adjacency(doc):
    """Adjacency list from transitionMatrix, filtered to real graph edges
    (drops the return_to_caller sentinel and None placeholders)."""
    matrix = doc.get('transitionMatrix', {})
    adj = {}
    for src, targets in matrix.items():
        adj[src] = sorted({t for t in targets if t and t != RETURN_TO_CALLER})
    return adj


def find_unreachable(adj, start='SessionStart'):
    """BFS from `start`; returns the sorted list of graph nodes never
    reached. Nodes are every key in adj plus every value that appears as a
    target."""
    all_nodes = set(adj.keys())
    for targets in adj.values():
        all_nodes.update(targets)
    all_nodes.discard(start)

    seen = {start}
    frontier = [start]
    while frontier:
        node = frontier.pop()
        for nxt in adj.get(node, []):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)

    return sorted(all_nodes - seen)


def find_sccs(adj):
    """Tarjan's SCC algorithm. Returns list of SCCs (each a list of nodes),
    including singleton SCCs. A cycle is any SCC with len > 1, or a
    singleton with a self-loop."""
    index_counter = [0]
    stack = []
    lowlink = {}
    index = {}
    on_stack = {}
    result = []

    all_nodes = set(adj.keys())
    for targets in adj.values():
        all_nodes.update(targets)

    def strongconnect(node):
        index[node] = index_counter[0]
        lowlink[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack[node] = True

        for succ in adj.get(node, []):
            if succ not in index:
                strongconnect(succ)
                lowlink[node] = min(lowlink[node], lowlink[succ])
            elif on_stack.get(succ):
                lowlink[node] = min(lowlink[node], index[succ])

        if lowlink[node] == index[node]:
            scc = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                scc.append(w)
                if w == node:
                    break
            result.append(scc)

    sys.setrecursionlimit(max(1000, len(all_nodes) * 4 + 100))
    for node in sorted(all_nodes):
        if node not in index:
            strongconnect(node)

    return result


def find_cycles(adj):
    """Cycle-bearing node sets: multi-node SCCs, plus singletons with a
    self-loop (A->A)."""
    cycles = []
    for scc in find_sccs(adj):
        if len(scc) > 1:
            cycles.append(sorted(scc))
        elif len(scc) == 1 and scc[0] in adj.get(scc[0], []):
            cycles.append(scc)
    return cycles


def parse_loop_cap_key(key):
    """Parse a loopCaps key into (a, b, bidirectional)."""
    if '<->' in key:
        a, b = key.split('<->', 1)
        return a, b, True
    if '->' in key:
        a, b = key.split('->', 1)
        return a, b, False
    return None, None, False


def cycle_edges(cycle_nodes, adj):
    """All directed edges (a, b) with both endpoints in cycle_nodes and a->b
    a real adjacency edge."""
    node_set = set(cycle_nodes)
    edges = []
    for a in cycle_nodes:
        for b in adj.get(a, []):
            if b in node_set:
                edges.append((a, b))
    return edges


def cycle_is_capped(cycle_nodes, adj, loop_caps):
    """True if at least one edge within this cycle is covered by loopCaps
    (directed or bidirectional key)."""
    edges = set(cycle_edges(cycle_nodes, adj))
    for key in loop_caps:
        a, b, bidi = parse_loop_cap_key(key)
        if a is None:
            continue
        if (a, b) in edges:
            return True
        if bidi and (b, a) in edges:
            return True
    return False


def validate_graph(doc, wf_memory_names=None):
    """Run all checks against an already-loaded states.json dict.

    wf_memory_names: optional list of WF_* memory basenames (no extension),
    for the doc<->state/subflow cross-check. Omit to skip that check (used
    by synthetic-graph tests that don't have a memories/wf/ directory).

    Returns {"errors": [...], "warnings": [...], "info": [...], "adjacency": {...}}.
    """
    errors = []
    warnings = []
    info = []

    states = doc.get('states', {})
    matrix = doc.get('transitionMatrix', {})
    subflows = set(doc.get('subflows', []))
    loop_caps = {k: v for k, v in doc.get('loopCaps', {}).items() if k != 'description'}
    adj = build_adjacency(doc)

    # 1. node transitions vs matrix row parity.
    for name, info_dict in states.items():
        node_targets = {t for t in info_dict.get('transitions', {}).values() if t and t != RETURN_TO_CALLER}
        matrix_targets = {t for t in matrix.get(name, []) if t and t != RETURN_TO_CALLER}
        if node_targets != matrix_targets:
            only_node = sorted(node_targets - matrix_targets)
            only_matrix = sorted(matrix_targets - node_targets)
            errors.append(
                f"{name}: node transitions vs transitionMatrix mismatch "
                f"(only in node.transitions: {only_node}; only in matrix: {only_matrix})"
            )

    # 2. every edge target is a real state (or the sentinel).
    all_state_names = set(states.keys())
    for src, targets in matrix.items():
        for t in targets:
            if t is None or t == RETURN_TO_CALLER:
                continue
            if t not in all_state_names:
                errors.append(f"transitionMatrix['{src}'] targets unknown state '{t}'")

    # 3. reachability from SessionStart.
    unreachable = find_unreachable(adj, start='SessionStart')
    real_unreachable = [n for n in unreachable if n in all_state_names]
    for n in real_unreachable:
        errors.append(f"{n} is unreachable from SessionStart")

    # 4. every non-terminal state has an out-edge.
    for name, info_dict in states.items():
        if info_dict.get('terminal'):
            continue
        targets = [t for t in matrix.get(name, []) if t]
        if not targets:
            errors.append(f"{name} has no outgoing transitions and is not marked terminal")

    # 5. wf memory docs <-> states/subflows cross-check.
    if wf_memory_names is not None:
        documented = set(wf_memory_names)
        declared = all_state_names | subflows
        docless = sorted(declared - documented)
        stateless = sorted(documented - declared)
        for name in docless:
            errors.append(f"{name} is a declared state/subflow but has no memories/wf/{name}.md")
        for name in stateless:
            errors.append(f"memories/wf/{name}.md exists but {name} is neither a state nor a declared subflow")

    # 6. cycles must have at least one capped edge (warning only).
    for cycle in find_cycles(adj):
        if not cycle_is_capped(cycle, adj, loop_caps):
            warnings.append(f"uncapped cycle: {cycle} (no loopCaps entry covers any edge in it)")

    # 7. ranks present.
    missing_rank = sorted(name for name, info_dict in states.items() if 'rank' not in info_dict)
    for name in missing_rank:
        errors.append(f"{name} has no 'rank' field")

    # 8. readAdvance pairs info: for every (a, b) with rank(b) > rank(a),
    # report whether it's an actual matrix edge.
    ranks = {name: info_dict.get('rank') for name, info_dict in states.items() if 'rank' in info_dict}
    for a, ra in ranks.items():
        for b, rb in ranks.items():
            if a == b or rb is None or ra is None or rb <= ra:
                continue
            is_edge = b in matrix.get(a, [])
            info.append(f"readAdvance candidate {a}(rank {ra}) -> {b}(rank {rb}): {'matrix edge' if is_edge else 'NOT a matrix edge, so a read never takes it'}")

    # 9. readBackward allowlist validity: each declared backward-read target
    # must (a) be a declared transition target of that state (both in its
    # own node.transitions values AND in transitionMatrix[state] — the parity
    # check in #1 above already keeps those two in sync), (b) have rank <=
    # the state's own rank (it would not need to be in readBackward
    # otherwise — is_forward_read_transition only consults it when
    # to_rank < from_rank), and (c) never be WF_CLARIFY or a subflow (a read
    # must never auto-enter the gate, and a subflow is not an FSM node a read
    # could land on).
    for name, info_dict in states.items():
        read_backward = info_dict.get('readBackward', [])
        if not read_backward:
            continue
        own_rank = info_dict.get('rank')
        node_targets = {t for t in info_dict.get('transitions', {}).values() if t and t != RETURN_TO_CALLER}
        matrix_targets = {t for t in matrix.get(name, []) if t and t != RETURN_TO_CALLER}
        for target in read_backward:
            if target == 'WF_CLARIFY':
                errors.append(f"{name}.readBackward lists WF_CLARIFY — a read must never auto-enter the CLARIFY gate")
                continue
            if target in subflows:
                errors.append(f"{name}.readBackward lists '{target}', which is a subflow, not an FSM state")
                continue
            if target not in node_targets or target not in matrix_targets:
                errors.append(
                    f"{name}.readBackward lists '{target}', which is not a declared "
                    f"transition target of {name} (transitions + transitionMatrix)"
                )
                continue
            target_rank = ranks.get(target)
            if own_rank is None or target_rank is None:
                errors.append(f"{name}.readBackward lists '{target}' but rank is missing for {name} or {target}")
                continue
            if target_rank > own_rank:
                errors.append(
                    f"{name}.readBackward lists '{target}' (rank {target_rank}), which is "
                    f"HIGHER than {name}'s own rank ({own_rank}) — that is already a forward "
                    f"read, readBackward is only for backward/same-rank declared exits"
                )

    return {"errors": errors, "warnings": warnings, "info": info, "adjacency": adj}


def format_adjacency(adj):
    lines = []
    for src in sorted(adj.keys()):
        targets = adj[src]
        lines.append(f"  {src} -> {', '.join(targets) if targets else '(none)'}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Validate the workflow state graph")
    parser.add_argument('--json', action='store_true', help='Emit JSON instead of text')
    args = parser.parse_args()

    doc = load_states_doc()
    wf_names = list_wf_memory_names()
    result = validate_graph(doc, wf_memory_names=wf_names)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("Adjacency list:")
        print(format_adjacency(result["adjacency"]))
        print()
        if result["errors"]:
            print(f"ERRORS ({len(result['errors'])}):")
            for e in result["errors"]:
                print(f"  ERROR: {e}")
        else:
            print("ERRORS: none")
        print()
        if result["warnings"]:
            print(f"WARNINGS ({len(result['warnings'])}):")
            for w in result["warnings"]:
                print(f"  WARNING: {w}")
        else:
            print("WARNINGS: none")
        print()
        print(f"INFO: {len(result['info'])} readAdvance candidate pair(s) evaluated")
        for i in result["info"]:
            print(f"  INFO: {i}")

    sys.exit(1 if result["errors"] else 0)


if __name__ == '__main__':
    main()
