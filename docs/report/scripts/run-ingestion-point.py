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
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labkit as lk                                            # noqa: E402

# Line-buffer stdout unconditionally: Python fully block-buffers stdout the
# moment it isn't a TTY (backgrounded, piped through tee, redirected to a
# log file for a subagent to poll) — every print() below sits unseen until
# the process exits or the buffer fills, which looks identical to a hang.
sys.stdout.reconfigure(line_buffering=True)

# --------------------------------------------------------------------------- frozen
# Frozen with the Plan. A change here is preparation, not a run: new commit,
# new freeze, and a note in the Journal. Printed at preflight so an uncommitted
# edit shows up in the point's log.

EXECUTION = "01-ingestion"

# The corpus is the stratified sample (index.md §1 Held constant + Notes), not
# the full 1,041-file / 14.52 GB set — that made a point's window too long for
# a five-point sweep with resets in between.
REPO_ROOT = lk.REPORT_ROOT.parents[1]
UPLOAD_SCRIPT = lk.SCRIPTS_DIR / "upload-dir-to-s3.py"
PREPARE_SCRIPT = lk.SCRIPTS_DIR / "prepare-cluster-for-ingestion.py"
DEFAULT_UPLOAD_DIR = REPO_ROOT / "tmp" / "ingest-sample"
DEFAULT_UPLOAD_PREFIX = "ingestion-sample/"

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


# --------------------------------------------------------------------------- upload

def start_upload(args, out_dir: Path, run_id: str):
    """Launch the corpus upload as a detached subprocess and hand back both the
    process and the instant it was launched, for use as the window's exact
    start — precise up to subprocess-launch overhead, not full poll
    granularity. Runs concurrently with watch(), not before it: the pipeline
    starts reacting to the first uploaded object while later ones are still
    in flight, so waiting for the whole upload to finish first would open the
    window late and miss that lead-in.

    --overwrite is required, not optional: every point re-triggers the
    pipeline against the same keys, and upload-dir-to-s3.py skips existing
    keys by default, which would fire no s3:ObjectCreated past the first
    point.
    """
    upload_dir = Path(args.upload_dir)
    if not upload_dir.is_dir():
        lk.die(f"--upload-dir {upload_dir} does not exist")

    log_path = out_dir / f"{run_id}.upload.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("w")

    t_start = lk.utcnow()
    proc = subprocess.Popen(
        [sys.executable, str(UPLOAD_SCRIPT),
         "--dir", str(upload_dir), "--prefix", args.upload_prefix, "--overwrite"],
        stdout=log_file, stderr=subprocess.STDOUT)
    print(f"{lk.ARROW} upload started (pid {proc.pid}) — {upload_dir} -> "
          f"prefix {args.upload_prefix!r} · log: {log_path}")
    return proc, t_start, log_file


def check_upload(proc, log_file) -> None:
    log_file.close()
    rc = proc.poll()
    if rc is None:
        print(f"{lk.WARN} upload still running after the window closed — "
              f"check its log; a point should not open before objects land, "
              f"but does not have to finish uploading to close")
    elif rc != 0:
        print(f"{lk.BAD} upload exited {rc} — check its log before trusting "
              f"R21 against the frozen doc count")
    else:
        print(f"[{lk.OK}] upload finished cleanly")


# --------------------------------------------------------------------------- qdrant

def qdrant_points(url: str, collection: str) -> int:
    """R21. Exact: the estimate on GET /collections lags indexing.

    A dropped collection (prepare-cluster-for-ingestion.py deletes rather
    than empties it — see that script's module docstring) 404s here rather
    than counting 0. Same end state either way: nothing to invalidate a
    preflight over, and the indexer recreates it on its first write."""
    try:
        body = lk.http_json(
            "POST", f"{url}/collections/{collection}/points/count", {"exact": True})
    except RuntimeError as e:
        if "HTTP 404" in str(e):
            return 0
        raise
    return int(body.get("result", {}).get("count", 0) or 0)


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
        replicas = lk.deployment_replicas(env.namespace_for(SHARED_TIER), SHARED_TIER)
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
        print(f"[{lk.OK if points == 0 else lk.BAD}] qdrant points = {points}")
        facts["points_before"] = points
        if points:
            failures.append(f"collection not empty ({points}) — the reset did not run")
    except RuntimeError as e:
        failures.append(f"Qdrant unreachable — {e}")

    try:
        images = lk.frozen_images(env, FREEZE)
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

def watch(env: lk.Env, args, pf: lk.PortForwards) -> dict:
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
    node_workload: dict[str, list[str]] = {}
    instance_types: set[str] = set()
    interrupts: list[str] = []
    node_seconds = 0.0
    peak_nodes = peak_depth = 0
    peak_tier = SHARED_TIER_FLOOR
    workload_ns = env.namespace_for("indexer")

    while True:
        now = lk.utcnow()
        if (now - wall_start).total_seconds() > env.max_wait_seconds:
            print()
            print(f"{lk.BAD} max wait exceeded — the run did not converge.")
            print("         Nothing exported, nothing wiped. Investigate, then")
            print("         export by hand with --start / --end once resolved.")
            sys.exit(lk.EXIT_TIMEOUT)

        for notice in pf.ensure_alive():
            print(f"{lk.WARN} {notice}")

        try:
            depths = {label: lk.sqs_depth(url) for label, url in queues.items()}
            nodes = lk.nodes_by_selector(selector)
            replicas = lk.deployment_replicas(env.namespace_for(SHARED_TIER), SHARED_TIER)
            workload_now = lk.pods_by_node(workload_ns, "app in (chunker,indexer)")
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
            for name in sorted(gone):
                # WhenEmpty/WhenEmptyOrUnderutilized consolidation only ever
                # disrupts a node already at pod-count 0 — the node's own
                # last-seen workload, not whether the system had backlog
                # elsewhere, is what tells a real loss from ordinary
                # consolidation (confirmed against ingestion-n50-test: two
                # InstanceTerminating nodes, M4 showed zero chunker/indexer
                # containers ever scheduled to either).
                pods = node_workload.get(name)
                if pods:
                    entry = (f"{lk.rfc3339(now)} · node left with live pods on "
                              f"it ({', '.join(pods)}) · {name}")
                    interrupts.append(entry)
                    print(f"{lk.WARN} {entry}")
                else:
                    print(f"{lk.ARROW} node consolidated while idle (no live "
                          f"chunker/indexer pods) · {name}")
        node_set = nodes
        node_workload = workload_now

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
        forced = event.split(" · ")[0] in lk.FORCED_REASONS
        if forced:
            if entry not in interrupts:
                interrupts.append(entry)
                print(f"{lk.WARN} {entry}")
        else:
            print(f"{lk.ARROW} {entry} (ordinary consolidation, not counted "
                  f"against validity)")

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
    p.add_argument("--series", default=str(exec_dir / "data" / "series.txt"))
    p.add_argument("--guards", default=str(exec_dir / "data" / "guards.txt"))
    p.add_argument("--start", help="explicit window start, RFC3339 — "
                   "ignored unless --no-upload, since a self-launched upload's "
                   "own launch instant is more precise")
    p.add_argument("--start-marker",
                   help="file holding the first s3:ObjectCreated timestamp — "
                   "ignored unless --no-upload, same reason as --start")
    p.add_argument("--upload-dir", default=str(DEFAULT_UPLOAD_DIR),
                   help="corpus to upload before watching (default: the "
                   "01-ingestion sample)")
    p.add_argument("--upload-prefix", default=DEFAULT_UPLOAD_PREFIX)
    p.add_argument("--no-upload", action="store_true",
                   help="skip the automatic upload — upload the corpus "
                   "yourself, out of band, and pass --start or --start-marker")
    p.add_argument("--step", default="15s")
    p.add_argument("--no-port-forward", action="store_true")
    p.add_argument("--no-prepare", action="store_true",
                   help="skip the automatic cluster reset after export — "
                   "reset it yourself (prepare-cluster-for-ingestion.py) "
                   "before the next point, or rely on organic drain")
    p.add_argument("--prepare-timeout", type=int, default=None,
                   help="seconds prepare-cluster-for-ingestion.py waits for "
                   "the floor (default: its own)")
    p.add_argument("--preflight-only", action="store_true")
    p.add_argument("--set-freeze", action="store_true",
                   help="record the current images as the sweep freeze and exit")
    args = p.parse_args()

    env = lk.Env(Path(args.env))
    out_dir = exec_dir / "data"
    freeze_file = exec_dir / "image-freeze.json"
    series_file, guards_file = Path(args.series), Path(args.guards)

    forwards = [lk.forward_spec(env, "prometheus"), lk.forward_spec(env, "qdrant")]
    with lk.PortForwards(forwards, enabled=not args.no_port_forward) as pf:
        if args.set_freeze:
            images = lk.frozen_images(env, FREEZE)
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

        upload = None
        if args.no_upload:
            if not args.start and not args.start_marker:
                print(f"{lk.WARN} --no-upload with neither --start nor "
                      f"--start-marker — window start will be inferred at "
                      f"poll granularity")
        else:
            if args.start or args.start_marker:
                print(f"{lk.WARN} --start/--start-marker given without "
                      f"--no-upload — ignored, using the upload's own launch "
                      f"instant instead")
            proc, t_start, log_file = start_upload(args, out_dir, args.run)
            args.start = lk.rfc3339(t_start)
            args.start_marker = None
            upload = (proc, log_file)

        result = watch(env, args, pf)
        if upload:
            check_upload(*upload)

        for notice in pf.ensure_alive():
            print(f"{lk.WARN} {notice}")

        try:
            points_after = qdrant_points(url, collection)
            print(f"{lk.ARROW} R21 · qdrant points after run: {points_after}")
            if args.doc_count and points_after < args.doc_count:
                print(f"{lk.WARN} fewer points than the frozen corpus count "
                      f"({args.doc_count}) — the denominator lies, re-run the point")
        except RuntimeError as e:
            points_after = -1
            print(f"{lk.WARN} could not read the point count: {e}")

        for notice in pf.ensure_alive():
            print(f"{lk.WARN} {notice}")

        rc = lk.run_export(series_file, args.run, result["t_start"],
                           result["t_end"], args.step, env.prom_url, out_dir)
        if rc != 0:
            print()
            print(f"{lk.BAD} export returned {rc} — NOTHING WIPED, WINDOW PRESERVED.")
            print(f"         Retention is short. Fix the gap, then re-export:")
            lk.reexport_hint(series_file, args.run, result["t_start"],
                             result["t_end"], out_dir)
            print(f"         Do not start the next point until this one is exported.")
            return lk.EXIT_EXPORT_GAP

        print()
        guard_failures = lk.check_guards(env.prom_url, guards)

        print()
        if args.no_prepare:
            print(f"{lk.WARN} --no-prepare — cluster not reset, the next point "
                  f"starts dirty")
        else:
            print(f"{lk.ARROW} resetting cluster for the next point "
                  f"(prepare-cluster-for-ingestion.py)")
            prepare_cmd = [sys.executable, str(PREPARE_SCRIPT), "--env", args.env]
            if args.prepare_timeout is not None:
                prepare_cmd += ["--wait-timeout", str(args.prepare_timeout)]
            rc = subprocess.run(prepare_cmd).returncode
            if rc != 0:
                print(f"{lk.BAD} cluster reset did not complete cleanly — the "
                      f"export is safe, resolve by hand before the next point")
                return lk.EXIT_EXPORT_GAP

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
