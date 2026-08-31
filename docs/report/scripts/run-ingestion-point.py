#!/usr/bin/env python3
"""run-ingestion-point.py — one invocation per point of 01-ingestion.

    ./run-ingestion-point.py --run ingestion-n04 --n 4 --doc-count 12000
    ./run-ingestion-point.py --set-freeze          # record the image freeze once
    ./run-ingestion-point.py --run x --n 4 --preflight-only

Addresses come from scripts/env.yaml. Refs come from the execution's series.txt
and guards.txt. What must not move, and what closes the window, are the constants
below — frozen with the Plan and covered by the commit recorded in each point.

The window does not close at queue drain. It closes when the ingestion pool is at
zero nodes and the shared tier is back at its floor, plus the buffer: a node bills
before its first pod and after its last (01-ingestion/K1).

Exit codes:
    0  clean point — exported, reset done, block written
    1  preflight failed, or usage / connection error
    2  export returned gaps — WINDOW PRESERVED, NOTHING WIPED, re-export by hand
    3  point completed but interruptions or guard breaches were detected
    4  timeout — the run did not converge, nothing exported, nothing wiped

Requires: PyYAML, kubectl, aws.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labkit as lk                                            # noqa: E402

# --------------------------------------------------------------------------- frozen
# Frozen with the Plan. A change here is preparation, not a run: new commit,
# new freeze, and a note in the Journal. Printed at preflight so an uncommitted
# edit shows up in the point's log.

EXECUTION = "01-ingestion"

# Must not move across the grid. Digests land in ./image-freeze.json.
FREEZE = [
    "scaledjob/chunker",
    "scaledjob/indexer",
    "deployment/tei-embeddings",
]

# TEI is shared and elastic: the indexer drives the same deployment the query
# path drives, so a point must open at the floor and the window must not close
# until it returns there (01-ingestion/K5).
SHARED_TIER = "tei-embeddings"
SHARED_TIER_FLOOR = 2

# The five minutes named in §1 Window, held after the pool reaches zero.
BUFFER_SECONDS = 300

QUEUES = ("stage-1", "stage-2")


def print_constants() -> None:
    print(f"{lk.ARROW} frozen     : freeze={', '.join(FREEZE)}")
    print(f"{lk.ARROW}              shared tier={SHARED_TIER} floor="
          f"{SHARED_TIER_FLOOR} buffer={BUFFER_SECONDS}s")


# --------------------------------------------------------------------------- qdrant

def qdrant_info(url: str, collection: str) -> dict:
    return lk.http_json("GET", f"{url}/collections/{collection}").get("result", {})


def qdrant_points(url: str, collection: str) -> int:
    """R21. Exact: the estimate on GET /collections lags indexing."""
    body = lk.http_json(
        "POST", f"{url}/collections/{collection}/points/count", {"exact": True})
    return int(body.get("result", {}).get("count", 0) or 0)


def qdrant_create_body(info: dict) -> dict:
    """Map GET /collections/<n> back onto a PUT create body. Best effort — the
    two schemas are close but not identical, so the snapshot goes to disk before
    the delete regardless."""
    config = info.get("config", {})
    params = config.get("params", {})
    body: dict = {}
    for key in ("vectors", "sparse_vectors", "shard_number", "replication_factor",
                "write_consistency_factor", "on_disk_payload", "sharding_method"):
        if params.get(key) is not None:
            body[key] = params[key]
    for src, dst in (("hnsw_config", "hnsw_config"),
                     ("quantization_config", "quantization_config"),
                     ("optimizer_config", "optimizers_config"),
                     ("wal_config", "wal_config")):
        if config.get(src) is not None:
            body[dst] = config[src]
    return body


def qdrant_wipe(url: str, collection: str, mode: str, out_dir: Path,
                run_id: str) -> None:
    if mode == "none":
        print(f"{lk.WARN} wipe skipped — the next point starts dirty")
        return

    info = qdrant_info(url, collection)
    payload_schema = info.get("payload_schema", {}) or {}
    body = qdrant_create_body(info)

    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = out_dir / f"{run_id}.collection-config.json"
    snapshot.write_text(json.dumps(
        {"create_body": body, "payload_schema": payload_schema,
         "raw_info": info}, indent=2) + "\n")
    print(f"{lk.ARROW} collection config snapshotted -> {snapshot}")

    lk.http_json("DELETE", f"{url}/collections/{collection}")
    print(f"[{lk.OK}] collection deleted")
    if mode == "delete-only":
        print(f"{lk.WARN} not recreating — the application must create it")
        return

    lk.http_json("PUT", f"{url}/collections/{collection}", body)
    print(f"[{lk.OK}] collection recreated from snapshot")

    for field, schema in payload_schema.items():
        field_type = schema.get("data_type") if isinstance(schema, dict) else schema
        if not field_type:
            continue
        try:
            lk.http_json("PUT", f"{url}/collections/{collection}/index?wait=true",
                         {"field_name": field, "field_schema": field_type})
            print(f"[{lk.OK}] payload index restored: {field} ({field_type})")
        except RuntimeError as e:
            print(f"{lk.WARN} could not restore payload index {field}: {e}")
            print(f"{lk.WARN} restore by hand from {snapshot} before the next point")

    remaining = qdrant_points(url, collection)
    if remaining != 0:
        raise RuntimeError(f"collection not empty after wipe: {remaining} points")


# --------------------------------------------------------------------------- preflight

def preflight(env: lk.Env, args, freeze_file: Path) -> dict:
    print(f"{lk.ARROW} preflight")
    failures: list[str] = []
    facts: dict = {}

    for label in QUEUES:
        try:
            depth = lk.sqs_depth(env.need(f"sqs.{label}"))
        except RuntimeError as e:
            failures.append(f"SQS {label} unreadable — {e}")
            continue
        print(f"[{lk.OK if depth == 0 else lk.BAD}] SQS {label} depth = {depth}")
        if depth:
            failures.append(f"SQS {label} not drained ({depth})")

    try:
        nodes = lk.nodes_by_selector(env.need("nodepool_ingestion"))
        print(f"[{lk.OK if not nodes else lk.BAD}] ingestion pool nodes = {len(nodes)}")
        if nodes:
            failures.append(
                f"NodePool not at zero ({len(nodes)}: {', '.join(sorted(nodes))}) — "
                f"a node inherited from the previous point invalidates this one")
    except RuntimeError as e:
        failures.append(f"node query failed — {e}")

    try:
        replicas = lk.deployment_replicas(env.namespace, SHARED_TIER)
        print(f"[{lk.OK if replicas == SHARED_TIER_FLOOR else lk.BAD}] "
              f"{SHARED_TIER} replicas = {replicas} "
              f"(must open at {SHARED_TIER_FLOOR})")
        facts["shared_tier_at_open"] = replicas
        if replicas != SHARED_TIER_FLOOR:
            failures.append(
                f"{SHARED_TIER} at {replicas} rather than {SHARED_TIER_FLOOR} — a "
                f"point opening with the shared tier warm carries capacity it did "
                f"not pay for")
    except RuntimeError as e:
        failures.append(f"{SHARED_TIER} unreadable — {e}")

    url, collection = env.need("qdrant.url"), env.need("qdrant.collection")
    try:
        points = qdrant_points(url, collection)
        expect_empty = args.wipe_mode != "none"
        print(f"[{lk.OK if (points == 0 or not expect_empty) else lk.BAD}] "
              f"qdrant points = {points}")
        facts["points_before"] = points
        if points and expect_empty:
            failures.append(f"collection not empty ({points}) — the reset did not run")
    except RuntimeError as e:
        failures.append(f"Qdrant unreachable — {e}")

    try:
        images = lk.frozen_images(env.namespace, FREEZE)
        facts["images"] = images
        failures += lk.check_freeze(freeze_file, images)
    except RuntimeError as e:
        failures.append(f"freeze read failed — {e}")

    try:
        down = lk.prom_targets_down(env.prom_url)
        print(f"[{lk.OK if not down else lk.WARN}] prometheus targets down = "
              f"{len(down)}")
        for target in down:
            print(f"         {target}")
        facts["targets_down"] = down
    except RuntimeError as e:
        failures.append(f"Prometheus unreachable — {e}")

    facts.update(lk.git_facts())

    if failures:
        print()
        print(f"{lk.BAD} preflight failed — a point never starts on a dirty cluster:")
        for item in failures:
            print(f"         {item}")
        sys.exit(lk.EXIT_PREFLIGHT)

    print(f"{lk.ARROW} preflight clean")
    return facts


# --------------------------------------------------------------------------- watch

def watch(env: lk.Env, args) -> dict:
    poll = env.poll_seconds
    selector = env.need("nodepool_ingestion")
    queues = {label: env.need(f"sqs.{label}") for label in QUEUES}

    print()
    print(f"{lk.ARROW} watching — poll {poll}s · buffer {BUFFER_SECONDS}s · "
          f"max wait {lk.hms(env.max_wait_seconds)}")
    print(f"{lk.ARROW} start the upload script now if it is not already running")
    print()

    wall_start = lk.utcnow()
    t_start = lk.parse_instant(args.start) if args.start else None
    if args.start_marker:
        marker = Path(args.start_marker)
        if marker.is_file():
            t_start = lk.parse_instant(marker.read_text())
            print(f"{lk.ARROW} start from marker: {lk.rfc3339(t_start)}")

    started = t_start is not None
    zero_since = None
    node_set: dict[str, str] = {}
    instance_types: set[str] = set()
    interrupts: list[str] = []
    node_seconds = 0.0
    peak_nodes = peak_depth = 0
    peak_tier = SHARED_TIER_FLOOR

    while True:
        now = lk.utcnow()
        if (now - wall_start).total_seconds() > env.max_wait_seconds:
            print()
            print(f"{lk.BAD} max wait exceeded — the run did not converge.")
            print("         Nothing exported, nothing wiped. Investigate, then")
            print("         export by hand with --start / --end once resolved.")
            sys.exit(lk.EXIT_TIMEOUT)

        try:
            depths = {label: lk.sqs_depth(url) for label, url in queues.items()}
            nodes = lk.nodes_by_selector(selector)
            replicas = lk.deployment_replicas(env.namespace, SHARED_TIER)
        except RuntimeError as e:
            print(f"{lk.WARN} poll failed ({e}) — retrying")
            time.sleep(poll)
            continue

        total = sum(depths.values())
        peak_depth = max(peak_depth, total)
        peak_tier = max(peak_tier, replicas)
        instance_types.update(nodes.values())

        if not started and (total > 0 or nodes):
            started = True
            t_start = now - timedelta(seconds=poll)
            print(f"{lk.ARROW} run started (inferred) — window opens "
                  f"{lk.rfc3339(t_start)}")
            print(f"{lk.WARN} inferred to poll granularity. For an exact window have "
                  f"the upload script write the first s3:ObjectCreated timestamp and "
                  f"pass --start-marker")

        if started:
            node_seconds += len(nodes) * poll
            peak_nodes = max(peak_nodes, len(nodes))
            gone = set(node_set) - set(nodes)
            if gone and total > 0 and nodes:
                for name in sorted(gone):
                    entry = (f"{lk.rfc3339(now)} · node left while queue depth="
                             f"{total} · {name}")
                    interrupts.append(entry)
                    print(f"{lk.WARN} {entry}")
        node_set = nodes

        settled = (started and total == 0 and not nodes
                   and replicas <= SHARED_TIER_FLOOR)
        if settled:
            if zero_since is None:
                zero_since = now
                print(f"{lk.ARROW} pool at zero and {SHARED_TIER} back at "
                      f"{SHARED_TIER_FLOOR} — holding {BUFFER_SECONDS}s buffer")
            elif (now - zero_since).total_seconds() >= BUFFER_SECONDS:
                t_end = zero_since + timedelta(seconds=BUFFER_SECONDS)
                break
        elif zero_since is not None:
            zero_since = None
            print(f"{lk.WARN} capacity returned — buffer reset")

        phase = "wait" if not started else ("drain" if total == 0 else "run")
        elapsed = lk.hms((now - t_start).total_seconds()) if t_start else "--"
        depth_str = " ".join(f"{k}={v}" for k, v in sorted(depths.items()))
        print(f"    {lk.rfc3339(now)}  {phase:<5}  {depth_str}  "
              f"nodes={len(nodes):<3} {SHARED_TIER}={replicas:<3} elapsed={elapsed}")
        time.sleep(poll)

    print()
    print(f"{lk.ARROW} window closed — {lk.rfc3339(t_start)} .. {lk.rfc3339(t_end)}")

    for event in lk.interrupt_events(t_start):
        entry = f"karpenter event · {event}"
        if entry not in interrupts:
            interrupts.append(entry)
            print(f"{lk.WARN} {entry}")

    return {
        "t_start": t_start, "t_end": t_end,
        "wall_seconds": (t_end - t_start).total_seconds(),
        "node_seconds": node_seconds, "peak_nodes": peak_nodes,
        "peak_depth": peak_depth, "peak_shared_tier": peak_tier,
        "instance_types": sorted(instance_types), "interrupts": interrupts,
    }


# --------------------------------------------------------------------------- block

def point_block(args, facts, result, points_after, guard_failures) -> str:
    docs_min = ""
    if args.doc_count and result["wall_seconds"] > 0:
        docs_min = f"{args.doc_count / (result['wall_seconds'] / 60):.1f}"
    dirty = "  ⚠ WORKING TREE DIRTY" if facts.get("dirty") else ""

    lines = [
        f"#### {args.run} · N set = {args.n}",
        "",
        f"Commit: `{facts.get('commit', 'unknown')}`{dirty}",
        f"Window UTC: {lk.rfc3339(result['t_start'])} → "
        f"{lk.rfc3339(result['t_end'])} · {lk.hms(result['wall_seconds'])}",
        "",
    ]
    lines += lk.md_table([
        ("M5 · N reached", "⟨from export — peak and time-weighted mean⟩"),
        (f"M9 · {SHARED_TIER} peak replicas", str(result["peak_shared_tier"])),
        ("R21 · Qdrant points after run", str(points_after)),
        ("D22 · docs/min", docs_min or "⟨00-baseline §2 count ÷ wall time⟩"),
        ("M10 · compute $", "⟨cost pass⟩"),
        ("D23 · TEI $ net of floor", "⟨cost pass⟩"),
        ("D24 · $/run", "⟨cost pass⟩"),
        ("D25 · $/1M docs", "⟨cost pass⟩"),
    ])
    lines += [
        "",
        f"Poll-integrated node-seconds, cross-check only and not billing: "
        f"{result['node_seconds']:.0f} "
        f"({result['node_seconds'] / 3600:.2f} node-hours) · peak nodes "
        f"{result['peak_nodes']} · types "
        f"{', '.join(result['instance_types']) or '—'}",
        f"Peak combined queue depth: {result['peak_depth']}",
        "",
        "**R20 · Saturation signal** — ⟨component⟩, read from ⟨M6 · M15 · M17 · M1 "
        "not draining while M5 idle⟩ at ⟨value⟩",
        "",
        f"Interruptions: {len(result['interrupts'])}",
    ]
    lines += [f"  - {entry}" for entry in result["interrupts"]]
    lines += [
        f"Guards breached: {', '.join(guard_failures) or 'none'}",
        "",
        "Validity — ⟨valid · re-run, reason ⟨⟩ · marked ᴱ and excluded, reason ⟨⟩⟩",
        "Notes — ⟨⟩",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- main

def main() -> int:
    exec_dir = lk.execution_dir(EXECUTION)

    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", help="point id, e.g. ingestion-n04")
    p.add_argument("--n", help="the swept maxReplicaCount, for the record")
    p.add_argument("--doc-count", type=int,
                   help="frozen corpus count from 00-baseline §2")
    p.add_argument("--env", default=str(lk.default_env_path()))
    p.add_argument("--series", default=str(exec_dir / "series.txt"))
    p.add_argument("--guards", default=str(exec_dir / "guards.txt"))
    p.add_argument("--start", help="explicit window start, RFC3339")
    p.add_argument("--start-marker",
                   help="file holding the first s3:ObjectCreated timestamp")
    p.add_argument("--step", default="15s")
    p.add_argument("--wipe-mode", choices=["recreate", "delete-only", "none"],
                   default="recreate")
    p.add_argument("--no-port-forward", action="store_true")
    p.add_argument("--preflight-only", action="store_true")
    p.add_argument("--set-freeze", action="store_true",
                   help="record the current images as the sweep freeze and exit")
    args = p.parse_args()

    env = lk.Env(Path(args.env))
    out_dir = exec_dir / "data"
    freeze_file = exec_dir / "image-freeze.json"
    series_file, guards_file = Path(args.series), Path(args.guards)

    forwards = [lk.forward_spec(env, "prometheus"), lk.forward_spec(env, "qdrant")]
    with lk.PortForwards(forwards, enabled=not args.no_port_forward):
        if args.set_freeze:
            images = lk.frozen_images(env.namespace, FREEZE)
            freeze_file.parent.mkdir(parents=True, exist_ok=True)
            freeze_file.write_text(json.dumps(images, indent=2, sort_keys=True) + "\n")
            print(json.dumps(images, indent=2, sort_keys=True))
            print(f"{lk.ARROW} freeze written to {freeze_file}")
            return lk.EXIT_CLEAN

        if not args.run or not args.n:
            lk.die("--run and --n are required (or use --set-freeze)")
        if (out_dir / f"{args.run}.jsonl").exists():
            lk.die(f"{out_dir / (args.run + '.jsonl')} exists — pick another --run id")

        guards = lk.load_guards(guards_file)
        url, collection = env.need("qdrant.url"), env.need("qdrant.collection")

        print(f"{lk.ARROW} execution  : {EXECUTION}")
        print(f"{lk.ARROW} point      : {args.run}  ·  N={args.n}")
        print(f"{lk.ARROW} env        : {env.path}")
        print(f"{lk.ARROW} series     : {series_file}")
        print(f"{lk.ARROW} guards     : {guards_file} "
              f"({', '.join(g['ref'] for g in guards)})")
        print_constants()
        print()

        facts = preflight(env, args, freeze_file)
        if args.preflight_only:
            print(f"{lk.ARROW} preflight only — nothing started")
            return lk.EXIT_CLEAN

        result = watch(env, args)

        try:
            points_after = qdrant_points(url, collection)
            print(f"{lk.ARROW} R21 · qdrant points after run: {points_after}")
            if args.doc_count and points_after < args.doc_count:
                print(f"{lk.WARN} fewer points than the frozen corpus count "
                      f"({args.doc_count}) — the denominator lies, re-run the point")
        except RuntimeError as e:
            points_after = -1
            print(f"{lk.WARN} could not read the point count: {e}")

        rc = lk.run_export(series_file, args.run, result["t_start"],
                           result["t_end"], args.step, env.prom_url, out_dir)
        if rc != 0:
            print()
            print(f"{lk.BAD} export returned {rc} — NOTHING WIPED, WINDOW PRESERVED.")
            print(f"         Retention is short. Fix the gap, then re-export:")
            lk.reexport_hint(series_file, args.run, result["t_start"],
                             result["t_end"])
            print(f"         Do not start the next point until this one is exported.")
            return lk.EXIT_EXPORT_GAP

        print()
        guard_failures = lk.check_guards(env.prom_url, guards)

        print()
        print(f"{lk.ARROW} resetting Qdrant (mode: {args.wipe_mode})")
        try:
            qdrant_wipe(url, collection, args.wipe_mode, out_dir, args.run)
        except RuntimeError as e:
            print(f"{lk.BAD} wipe failed: {e}")
            print(f"         The export is safe. Resolve by hand before the next point.")
            return lk.EXIT_EXPORT_GAP

        for label in QUEUES:
            depth = lk.sqs_depth(env.need(f"sqs.{label}"))
            print(f"[{lk.OK if depth == 0 else lk.WARN}] SQS {label} after reset = "
                  f"{depth}")

        block = point_block(args, facts, result, points_after, guard_failures)
        record = {
            "execution": EXECUTION, "point": args.run, "n_set": args.n,
            "commit": facts.get("commit"), "dirty": facts.get("dirty"),
            "window": {"start": lk.rfc3339(result["t_start"]),
                       "end": lk.rfc3339(result["t_end"]),
                       "wall_seconds": result["wall_seconds"]},
            "doc_count": args.doc_count, "points_after": points_after,
            "peak_nodes": result["peak_nodes"],
            "peak_shared_tier": result["peak_shared_tier"],
            "instance_types": result["instance_types"],
            "interrupts": result["interrupts"],
            "guard_failures": guard_failures,
            "freeze": facts.get("images"),
        }
        md_path = lk.write_point(out_dir, args.run, block, record)

        print()
        print("=" * 78)
        print(block)
        print("=" * 78)
        print(f"{lk.ARROW} paste the block into the Journal · also at {md_path}")
        print(f"{lk.ARROW} R20 is the only field no query fills — read it in Grafana "
              f"now, while the window is still in retention")

        return lk.report_validity(result["interrupts"], guard_failures)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrupted — nothing wiped", file=sys.stderr)
        sys.exit(130)
