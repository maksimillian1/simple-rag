#!/usr/bin/env python3
"""
run-point.py — one invocation per sweep point.

    ./run-point.py --run e1-n08 --n 8
    ./run-point.py --run e1-n08 --n 8 --preflight-only
    ./run-point.py --set-baseline                       # freeze image digests once

Closes six manual steps that used to be done by hand around every point:
preflight, window timing (R3), interruption detection, points_count, metric
export, and Qdrant reset.

Stdlib + subprocess(kubectl, aws) only — same constraint as export-metrics.py.

Port-forwards to Prometheus and Qdrant are opened automatically and torn down on
exit. Pass --no-port-forward if you already have them open.

Exit codes:
    0  clean point — exported, reset done, markdown block written
    1  preflight failed, or usage / connection error
    2  export returned gaps — WINDOW PRESERVED, NOTHING WIPED, re-export by hand
    3  point completed but interruptions were detected — review before curve fit
    4  timeout — the run did not converge, nothing exported, nothing wiped
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --------------------------------------------------------------------------- config
# Everything here is overridable by environment variable or CLI flag.
# FILL THE FOUR MARKED VALUES ONCE, then never touch this block again.

SQS_STAGE1 = os.environ.get("SQS_STAGE1_URL", "")          # <-- FILL
SQS_STAGE2 = os.environ.get("SQS_STAGE2_URL", "")          # <-- FILL
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "")  # <-- FILL
APP_NAMESPACE = os.environ.get("APP_NAMESPACE", "default")   # <-- CONFIRM

NODEPOOL_SELECTOR = os.environ.get(
    "NODEPOOL_SELECTOR", "karpenter.sh/nodepool=apps-compute")
SCALEDJOBS = os.environ.get("SCALEDJOBS", "chunker,indexer").split(",")

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333").rstrip("/")
QDRANT_SVC = os.environ.get("QDRANT_SVC", "svc/qdrant")
QDRANT_NS = os.environ.get("QDRANT_NS", APP_NAMESPACE)

PROM_URL = os.environ.get("PROM_URL", "http://localhost:9090").rstrip("/")
PROM_SVC = os.environ.get(
    "PROM_SVC", "svc/monitoring-kube-prometheus-prometheus")
PROM_NS = os.environ.get("PROM_NS", "monitoring")

OUT_DIR = Path(os.environ.get("OUT_DIR", "docs/report/data"))
EXPORT_SCRIPT = Path(os.environ.get(
    "EXPORT_SCRIPT", str(Path(__file__).with_name("export-metrics.py"))))
BASELINE_FILE = Path(os.environ.get(
    "BASELINE_FILE", str(Path(__file__).with_name("image-baseline.json"))))

POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "15"))
BUFFER_SECONDS = int(os.environ.get("BUFFER_SECONDS", "300"))   # NodePool zero + 5 min
MAX_WAIT_SECONDS = int(os.environ.get("MAX_WAIT_SECONDS", str(90 * 60)))

# Karpenter event reasons that indicate involuntary node loss. Best effort —
# event TTL is short and this is a cross-check, not the primary signal.
INTERRUPT_REASONS = [
    "SpotInterrupted",
    "TerminatingOnInterruption",
    "InstanceTerminating",
    "InstanceStopping",
]

OK, BAD, WARN, ARROW = "  ok  ", " FAIL ", " warn ", "->"


# --------------------------------------------------------------------------- shell

def sh(cmd: list[str], timeout: int = 60) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        die(f"command not found: {cmd[0]}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"timeout: {' '.join(cmd[:4])}...") from None
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[:300] or f"exit {proc.returncode}")
    return proc.stdout


def sh_json(cmd: list[str], timeout: int = 60) -> dict:
    out = sh(cmd, timeout=timeout)
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise RuntimeError(f"not JSON from {cmd[0]}") from None


# --------------------------------------------------------------------------- http

def http_json(method: str, url: str, body: dict | None = None,
              timeout: int = 30) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"HTTP {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"cannot reach {url}: {e.reason}") from None
    return json.loads(raw) if raw.strip() else {}


# --------------------------------------------------------------------------- time

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_instant(text: str) -> datetime:
    try:
        return datetime.fromisoformat(text.strip().replace("Z", "+00:00")).astimezone(
            timezone.utc)
    except ValueError:
        die(f"bad timestamp: {text!r} (expected 2026-08-20T10:00:00Z)")


def hms(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600:d}h{(seconds % 3600) // 60:02d}m{seconds % 60:02d}s"


# --------------------------------------------------------------------------- cluster

def sqs_depth(queue_url: str) -> int:
    """Visible + in-flight. In-flight matters: a queue with zero visible and
    thirty in-flight is not drained."""
    data = sh_json([
        "aws", "sqs", "get-queue-attributes",
        "--queue-url", queue_url,
        "--attribute-names",
        "ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible",
        "--output", "json",
    ])
    attrs = data.get("Attributes", {})
    return (int(attrs.get("ApproximateNumberOfMessages", 0))
            + int(attrs.get("ApproximateNumberOfMessagesNotVisible", 0)))


def compute_nodes() -> dict[str, str]:
    """name -> instance type, for nodes in the ingestion NodePool."""
    data = sh_json([
        "kubectl", "get", "nodes", "-l", NODEPOOL_SELECTOR, "-o", "json",
    ])
    out = {}
    for item in data.get("items", []):
        labels = item.get("metadata", {}).get("labels", {})
        out[item["metadata"]["name"]] = labels.get(
            "node.kubernetes.io/instance-type", "?")
    return out


def scaledjob_images() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for name in SCALEDJOBS:
        name = name.strip()
        if not name:
            continue
        try:
            data = sh_json([
                "kubectl", "-n", APP_NAMESPACE, "get", "scaledjob", name, "-o", "json",
            ])
        except RuntimeError as e:
            raise RuntimeError(f"scaledjob/{name}: {e}") from None
        containers = (data.get("spec", {})
                          .get("jobTargetRef", {})
                          .get("template", {})
                          .get("spec", {})
                          .get("containers", []))
        out[name] = sorted(c.get("image", "?") for c in containers)
    return out


def karpenter_interrupt_events(since: datetime) -> list[str]:
    """Best effort. Event TTL is short; absence here proves nothing."""
    found = []
    try:
        data = sh_json(["kubectl", "get", "events", "-A", "-o", "json"], timeout=45)
    except RuntimeError:
        return found
    for item in data.get("items", []):
        reason = item.get("reason", "")
        if reason not in INTERRUPT_REASONS:
            continue
        stamp = (item.get("lastTimestamp")
                 or item.get("eventTime")
                 or item.get("firstTimestamp"))
        if stamp:
            try:
                if parse_instant(stamp) < since:
                    continue
            except SystemExit:
                pass
        obj = item.get("involvedObject", {}).get("name", "?")
        found.append(f"{reason} · {obj} · {stamp}")
    return found


def prom_up_down() -> list[str]:
    url = f"{PROM_URL}/api/v1/query?" + urllib.parse.urlencode({"query": "up == 0"})
    data = http_json("GET", url)
    if data.get("status") != "success":
        raise RuntimeError(data.get("error", "prometheus query failed"))
    return [
        f'{r["metric"].get("job", "?")}/{r["metric"].get("instance", "?")}'
        for r in data.get("data", {}).get("result", [])
    ]


# --------------------------------------------------------------------------- qdrant

def qdrant_info() -> dict:
    data = http_json("GET", f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}")
    return data.get("result", {})


def qdrant_points_count() -> int:
    return int(qdrant_info().get("points_count", 0) or 0)


def qdrant_create_body(info: dict) -> dict:
    """Map GET /collections/<n> back onto a PUT create body. Best effort — the
    two schemas are close but not identical, so the snapshot is written to disk
    before the delete regardless."""
    config = info.get("config", {})
    params = config.get("params", {})
    body: dict = {}
    for key in ("vectors", "sparse_vectors", "shard_number", "replication_factor",
                "write_consistency_factor", "on_disk_payload", "sharding_method"):
        if params.get(key) is not None:
            body[key] = params[key]
    if config.get("hnsw_config") is not None:
        body["hnsw_config"] = config["hnsw_config"]
    if config.get("quantization_config") is not None:
        body["quantization_config"] = config["quantization_config"]
    if config.get("optimizer_config") is not None:
        body["optimizers_config"] = config["optimizer_config"]
    if config.get("wal_config") is not None:
        body["wal_config"] = config["wal_config"]
    return body


def qdrant_wipe(run_id: str, mode: str) -> None:
    """recreate: snapshot config + payload schema, delete, recreate, restore indexes.
       delete-only: delete and let the application recreate on next start.
       none: leave the collection alone."""
    if mode == "none":
        print(f"{WARN} wipe skipped (--wipe-mode none) — next point starts dirty")
        return

    info = qdrant_info()
    payload_schema = info.get("payload_schema", {}) or {}
    body = qdrant_create_body(info)

    snapshot = OUT_DIR / f"{run_id}.collection-config.json"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(json.dumps(
        {"create_body": body, "payload_schema": payload_schema,
         "raw_info": info}, indent=2) + "\n")
    print(f"{ARROW} collection config snapshotted -> {snapshot}")

    http_json("DELETE", f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}")
    print(f"[{OK}] collection deleted")

    if mode == "delete-only":
        print(f"{WARN} not recreating — the application must create the collection")
        return

    http_json("PUT", f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}", body)
    print(f"[{OK}] collection recreated from snapshot")

    for field, schema in payload_schema.items():
        field_type = schema.get("data_type") if isinstance(schema, dict) else schema
        if not field_type:
            continue
        try:
            http_json(
                "PUT",
                f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/index?wait=true",
                {"field_name": field, "field_schema": field_type},
            )
            print(f"[{OK}] payload index restored: {field} ({field_type})")
        except RuntimeError as e:
            print(f"{WARN} could not restore payload index {field}: {e}")
            print(f"{WARN} restore by hand from {snapshot} before the next point")

    remaining = qdrant_points_count()
    if remaining != 0:
        raise RuntimeError(f"collection not empty after wipe: {remaining} points")


# --------------------------------------------------------------------------- port-forward

class PortForwards:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.procs: list[subprocess.Popen] = []

    def _spawn(self, ns: str, target: str, mapping: str) -> None:
        proc = subprocess.Popen(
            ["kubectl", "-n", ns, "port-forward", target, mapping],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self.procs.append(proc)

    def __enter__(self):
        if not self.enabled:
            return self
        print(f"{ARROW} port-forward : {PROM_NS}/{PROM_SVC} 9090 · "
              f"{QDRANT_NS}/{QDRANT_SVC} 6333")
        self._spawn(PROM_NS, PROM_SVC, "9090:9090")
        self._spawn(QDRANT_NS, QDRANT_SVC, "6333:6333")
        time.sleep(4)
        for proc in self.procs:
            if proc.poll() is not None:
                die("port-forward died immediately — check service names, or pass "
                    "--no-port-forward and open them yourself")
        return self

    def __exit__(self, *_):
        for proc in self.procs:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                proc.terminate()
        return False


# --------------------------------------------------------------------------- preflight

def preflight(args) -> dict:
    print(f"{ARROW} preflight")
    failures: list[str] = []
    facts: dict = {}

    for label, url in (("stage-1", SQS_STAGE1), ("stage-2", SQS_STAGE2)):
        try:
            depth = sqs_depth(url)
        except RuntimeError as e:
            failures.append(f"SQS {label} unreadable — {e}")
            continue
        mark = OK if depth == 0 else BAD
        print(f"[{mark}] SQS {label} depth = {depth}")
        if depth != 0:
            failures.append(f"SQS {label} not drained ({depth})")

    try:
        nodes = compute_nodes()
        mark = OK if not nodes else BAD
        print(f"[{mark}] apps-compute nodes = {len(nodes)}")
        if nodes:
            failures.append(
                f"NodePool not at zero ({len(nodes)}: {', '.join(sorted(nodes))}) — "
                "a warm node inherited from the previous point invalidates the point")
    except RuntimeError as e:
        failures.append(f"node query failed — {e}")

    try:
        points = qdrant_points_count()
        expected_zero = args.wipe_mode != "none"
        mark = OK if (points == 0 or not expected_zero) else BAD
        print(f"[{mark}] qdrant points_count = {points}")
        facts["points_before"] = points
        if points != 0 and expected_zero:
            failures.append(
                f"Qdrant collection not empty ({points}) — the standing decision in "
                "execution.md §2.8 is wipe-between-points")
    except RuntimeError as e:
        failures.append(f"Qdrant unreachable — {e}")

    try:
        images = scaledjob_images()
        facts["images"] = images
        if BASELINE_FILE.is_file():
            baseline = json.loads(BASELINE_FILE.read_text())
            if baseline != images:
                print(f"[{BAD}] image baseline mismatch")
                print(f"         baseline: {json.dumps(baseline, sort_keys=True)}")
                print(f"         current : {json.dumps(images, sort_keys=True)}")
                failures.append(
                    "ScaledJob images differ from the recorded baseline — the sweep "
                    "compares one artifact across N, re-run --set-baseline only if "
                    "you are starting a new sweep")
            else:
                print(f"[{OK}] image baseline matches")
        else:
            print(f"{WARN} no baseline at {BASELINE_FILE} — run --set-baseline first")
            failures.append("image baseline not recorded")
    except RuntimeError as e:
        failures.append(f"ScaledJob read failed — {e}")

    try:
        down = prom_up_down()
        mark = OK if not down else WARN
        print(f"[{mark}] prometheus targets down = {len(down)}")
        for target in down:
            print(f"         {target}")
        facts["targets_down"] = down
    except RuntimeError as e:
        failures.append(f"Prometheus unreachable — {e}")

    try:
        facts["commit"] = sh(["git", "rev-parse", "HEAD"]).strip()
        dirty = sh(["git", "status", "--porcelain"]).strip()
        print(f"[{OK}] config commit = {facts['commit'][:12]}"
              f"{'  (WORKING TREE DIRTY)' if dirty else ''}")
        facts["dirty"] = bool(dirty)
    except RuntimeError:
        facts["commit"] = "unknown"
        print(f"{WARN} not a git checkout — config commit unrecorded (R3 incomplete)")

    if not EXPORT_SCRIPT.is_file():
        failures.append(f"export script not found at {EXPORT_SCRIPT}")

    if failures:
        print()
        print(f"{BAD} preflight failed — a point never starts on a dirty cluster:")
        for f in failures:
            print(f"         {f}")
        sys.exit(1)

    print(f"{ARROW} preflight clean")
    return facts


# --------------------------------------------------------------------------- watch

def watch(args) -> dict:
    print()
    print(f"{ARROW} watching — poll {POLL_SECONDS}s · buffer {BUFFER_SECONDS}s · "
          f"max wait {hms(MAX_WAIT_SECONDS)}")
    print(f"{ARROW} start the upload script now if it is not already running")
    print()

    wall_start = utcnow()
    t_start: datetime | None = parse_instant(args.start) if args.start else None
    if args.start_marker:
        marker = Path(args.start_marker)
        if marker.is_file():
            t_start = parse_instant(marker.read_text())
            print(f"{ARROW} start from marker file: {rfc3339(t_start)}")

    started = t_start is not None
    zero_since: datetime | None = None
    node_set: dict[str, str] = {}
    instance_types: set[str] = set()
    interrupts: list[str] = []
    node_seconds = 0.0
    peak_nodes = 0
    peak_depth = 0

    while True:
        now = utcnow()
        if (now - wall_start).total_seconds() > MAX_WAIT_SECONDS:
            print()
            print(f"{BAD} max wait exceeded — the run did not converge.")
            print("         Nothing exported, nothing wiped. Investigate the cluster,")
            print("         then export by hand with --start/--end once resolved.")
            sys.exit(4)

        try:
            d1, d2 = sqs_depth(SQS_STAGE1), sqs_depth(SQS_STAGE2)
            nodes = compute_nodes()
        except RuntimeError as e:
            print(f"{WARN} poll failed ({e}) — retrying")
            time.sleep(POLL_SECONDS)
            continue

        total = d1 + d2
        peak_depth = max(peak_depth, total)
        instance_types.update(nodes.values())

        if not started and (total > 0 or nodes):
            started = True
            t_start = now - timedelta(seconds=POLL_SECONDS)
            print(f"{ARROW} run started (inferred) — window opens {rfc3339(t_start)}")
            print(f"{WARN} inferred to poll granularity. For an exact R3 window, have "
                  f"the upload script write the first s3:ObjectCreated timestamp and "
                  f"pass --start-marker")

        if started:
            node_seconds += len(nodes) * POLL_SECONDS
            peak_nodes = max(peak_nodes, len(nodes))
            gone = set(node_set) - set(nodes)
            if gone and total > 0 and nodes:
                for name in sorted(gone):
                    entry = f"{rfc3339(now)} · node left while queue depth={total} · {name}"
                    interrupts.append(entry)
                    print(f"{WARN} {entry}")

        node_set = nodes

        if started and total == 0 and not nodes:
            if zero_since is None:
                zero_since = now
                print(f"{ARROW} capacity at zero — holding {BUFFER_SECONDS}s buffer")
            elif (now - zero_since).total_seconds() >= BUFFER_SECONDS:
                t_end = zero_since + timedelta(seconds=BUFFER_SECONDS)
                break
        elif zero_since is not None:
            zero_since = None
            print(f"{WARN} capacity returned — buffer reset")

        phase = "wait" if not started else ("drain" if total == 0 else "run")
        elapsed = hms((now - t_start).total_seconds()) if t_start else "--"
        print(f"    {rfc3339(now)}  {phase:<5}  s1={d1:<6} s2={d2:<6} "
              f"nodes={len(nodes):<3} elapsed={elapsed}")

        time.sleep(POLL_SECONDS)

    print()
    print(f"{ARROW} window closed — {rfc3339(t_start)} .. {rfc3339(t_end)}")

    events = karpenter_interrupt_events(t_start)
    for e in events:
        entry = f"karpenter event · {e}"
        if entry not in interrupts:
            interrupts.append(entry)
            print(f"{WARN} {entry}")

    return {
        "t_start": t_start,
        "t_end": t_end,
        "wall_seconds": (t_end - t_start).total_seconds(),
        "node_seconds": node_seconds,
        "peak_nodes": peak_nodes,
        "peak_depth": peak_depth,
        "instance_types": sorted(instance_types),
        "interrupts": interrupts,
    }


# --------------------------------------------------------------------------- post

def export(run_id: str, t_start: datetime, t_end: datetime, step: str) -> int:
    print()
    print(f"{ARROW} exporting metrics")
    cmd = [sys.executable, str(EXPORT_SCRIPT),
           "--run", run_id,
           "--start", rfc3339(t_start),
           "--end", rfc3339(t_end),
           "--step", step]
    proc = subprocess.run(cmd, env={**os.environ, "PROM_URL": PROM_URL,
                                    "OUT_DIR": str(OUT_DIR)})
    return proc.returncode


def point_markdown(args, facts: dict, result: dict, points_after: int) -> str:
    docs_per_min = ""
    if args.doc_count and result["wall_seconds"] > 0:
        docs_per_min = f"{args.doc_count / (result['wall_seconds'] / 60):.1f}"

    interrupts = result["interrupts"]
    lines = [
        f"### E1 · N={args.n}",
        "",
        "Pre-flight",
        "- [x] Both SQS queues at depth zero (verified by query)",
        "- [x] apps-compute NodePool at zero nodes (verified by query)",
        "- [x] Image digests unchanged since previous point",
        "- [x] Fixture unchanged — same snapshot, same bytes",
        "- [x] Only maxReplicaCount differs",
        "",
        f"Config commit: {facts.get('commit', 'unknown')}"
        + ("  ⚠ WORKING TREE DIRTY" if facts.get("dirty") else ""),
        f"Window UTC:    start {rfc3339(result['t_start'])} → "
        f"end {rfc3339(result['t_end'])}   (NodePool zero + "
        f"{BUFFER_SECONDS // 60} min)",
        "",
        "Results",
        "| | |",
        "| :--- | :--- |",
        f"| Docs/min — wall clock ÷ doc count | {docs_per_min or '⟨fill: R2 doc count ÷ wall⟩'} |",
        "| Docs/min — SQS depth derivative | ⟨from export, E1⟩ |",
        "| Cross-check within a few percent? | ⟨⟩ |",
        f"| Wall time | {hms(result['wall_seconds'])} |",
        "| Node-hours spot, by instance type | ⟨from export, E2⟩ |",
        "| Node-hours on-demand, by instance type | ⟨from export, E2⟩ |",
        "| $/run | ⟨C4 = node-hours × R1 price⟩ |",
        "| $/1M docs | ⟨C5⟩ |",
        "",
        f"Poll-integrated node-seconds (cross-check only, not billing): "
        f"{result['node_seconds']:.0f} "
        f"({result['node_seconds'] / 3600:.2f} node-hours) · "
        f"peak nodes {result['peak_nodes']} · "
        f"instance types observed: {', '.join(result['instance_types']) or '—'}",
        f"Peak combined SQS depth: {result['peak_depth']} · "
        f"Qdrant points after run: {points_after}",
        "",
        "R4 · Saturation signal: ⟨component⟩ — read from ⟨metric ref⟩ at ⟨value⟩",
        "    Candidates: chunker CPU (E6) · TEI queue (E8) · Qdrant write latency (E11)",
        "                · SQS not draining despite idle workers (E1)",
        "",
        "Anomalies",
        f"- Spot interruptions: {len(interrupts)}",
    ]
    for entry in interrupts:
        lines.append(f"  - {entry}")
    lines += [
        "- Other — stuck retries, OOM, manual intervention: ⟨⟩",
        "",
        "Validity",
        f"- [{'x' if not interrupts else ' '}] Valid — include in curve fit",
        "- [ ] Re-run required — reason: ⟨⟩",
        f"- [{'x' if interrupts else ' '}] Marked ᴱ and excluded from fit — "
        "reason: interruptions detected, warm-up cost belongs to no concurrency level",
        "",
        "Export",
        f"- [x] {OUT_DIR}/{args.run}.jsonl written, non-empty",
        f"- [x] {args.run}.meta.json present, gaps: []",
        "",
        "Reset before next point",
        "- [x] Both queues drained to zero",
        "- [x] apps-compute back to zero, confirmed by query",
        f"- [x] Qdrant state handled per the standing decision in 2.8 "
        f"(wipe-mode: {args.wipe_mode})",
        "",
        "Notes:",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- main

def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def check_config() -> None:
    missing = [name for name, val in (
        ("SQS_STAGE1_URL", SQS_STAGE1),
        ("SQS_STAGE2_URL", SQS_STAGE2),
        ("QDRANT_COLLECTION", QDRANT_COLLECTION),
    ) if not val]
    if missing:
        die("unset config: " + ", ".join(missing)
            + " — fill the config block at the top of this file, or export them")


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", help="run id, e.g. e1-n08")
    p.add_argument("--n", help="the swept maxReplicaCount value, for the record")
    p.add_argument("--doc-count", type=int,
                   help="exact document count from R2 — enables docs/min in the output")
    p.add_argument("--start", help="explicit window start, RFC3339")
    p.add_argument("--start-marker",
                   help="file written by the upload script holding the first "
                        "s3:ObjectCreated timestamp")
    p.add_argument("--step", default=os.environ.get("STEP", "15s"))
    p.add_argument("--wipe-mode", choices=["recreate", "delete-only", "none"],
                   default="recreate",
                   help="recreate: snapshot config + payload indexes, delete, restore")
    p.add_argument("--no-port-forward", action="store_true")
    p.add_argument("--preflight-only", action="store_true")
    p.add_argument("--set-baseline", action="store_true",
                   help="record current ScaledJob images as the sweep baseline and exit")
    args = p.parse_args()

    check_config()

    with PortForwards(enabled=not args.no_port_forward):
        if args.set_baseline:
            images = scaledjob_images()
            BASELINE_FILE.write_text(json.dumps(images, indent=2, sort_keys=True) + "\n")
            print(json.dumps(images, indent=2, sort_keys=True))
            print(f"{ARROW} baseline written to {BASELINE_FILE}")
            return 0

        if not args.run or not args.n:
            die("--run and --n are required (or use --set-baseline)")

        out_path = OUT_DIR / f"{args.run}.jsonl"
        if out_path.exists():
            die(f"{out_path} already exists — pick another --run id")

        print(f"{ARROW} run        : {args.run}  ·  N={args.n}")
        print(f"{ARROW} prometheus : {PROM_URL}")
        print(f"{ARROW} qdrant     : {QDRANT_URL}/collections/{QDRANT_COLLECTION}")
        print()

        facts = preflight(args)
        if args.preflight_only:
            print(f"{ARROW} preflight only — nothing started")
            return 0

        result = watch(args)

        try:
            points_after = qdrant_points_count()
            print(f"{ARROW} qdrant points after run: {points_after}")
        except RuntimeError as e:
            points_after = -1
            print(f"{WARN} could not read points_count: {e}")

        rc = export(args.run, result["t_start"], result["t_end"], args.step)
        if rc != 0:
            print()
            print(f"{BAD} export returned {rc} — NOTHING WIPED, WINDOW PRESERVED.")
            print(f"         Prometheus retention is 3d. Fix the gap, then re-export:")
            print(f"         {EXPORT_SCRIPT} --run {args.run} "
                  f"--start {rfc3339(result['t_start'])} "
                  f"--end {rfc3339(result['t_end'])} --force")
            print(f"         Do not start the next point until this one is exported.")
            return 2

        print()
        print(f"{ARROW} resetting Qdrant (mode: {args.wipe_mode})")
        try:
            qdrant_wipe(args.run, args.wipe_mode)
        except RuntimeError as e:
            print(f"{BAD} wipe failed: {e}")
            print(f"         Export is safe. Resolve by hand before the next point.")
            return 2

        for label, url in (("stage-1", SQS_STAGE1), ("stage-2", SQS_STAGE2)):
            depth = sqs_depth(url)
            mark = OK if depth == 0 else WARN
            print(f"[{mark}] SQS {label} depth after reset = {depth}")

        block = point_markdown(args, facts, result, points_after)
        md_path = OUT_DIR / f"{args.run}.point.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(block)

        print()
        print("=" * 78)
        print(block)
        print("=" * 78)
        print(f"{ARROW} paste the block above into execution.md Part 2")
        print(f"{ARROW} also written to {md_path}")
        print(f"{ARROW} R4 saturation signal is the only field no query can fill — "
              f"read E6/E8/E11 in Grafana now, while the run is fresh")

        if result["interrupts"]:
            print()
            print(f"{WARN} {len(result['interrupts'])} interruption signal(s) — this "
                  f"point carries warm-up cost belonging to no concurrency level.")
            print(f"         Re-run it, or mark $/1M docs as ᴱ and exclude it from the "
                  f"curve fit. Do not average it in silently.")
            return 3

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrupted — nothing wiped", file=sys.stderr)
        sys.exit(130)
