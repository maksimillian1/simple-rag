#!/usr/bin/env python3
"""run-inference-point.py — one invocation per point of 02-inference.

    ./run-inference-point.py --run inference-r200 --rate 200 --duration 10m
    ./run-inference-point.py --set-freeze
    ./run-inference-point.py --run x --rate 50 --preflight-only

The axis is arrival rate and the autoscaler is under test (02-inference/K2).
Nothing inside the cluster is edited between points: replicas are an output, so
this script never scales anything. It opens the window, runs the generator, waits
for the serving tier to return to its floor, exports, and checks guards.

Two preflight predicates are inverted relative to ingestion. The collection must
be loaded rather than empty, and the serving deployments must sit at their floor
rather than be absent. A point opening with capacity already warm measures a
different system.

There is no reset: the collection under query is the same at every rate.

Exit codes:
    0  clean point — exported, block written
    1  preflight failed, or usage / connection error
    2  export returned gaps — WINDOW PRESERVED, re-export by hand
    3  point completed but a guard was breached — see §1 Validity
    4  the serving tier never returned to its floor inside the max wait

Requires: PyYAML, kubectl, and whatever the generator command needs.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labkit as lk                                            # noqa: E402

# --------------------------------------------------------------------------- frozen
# Frozen with the Plan. Printed at preflight so an uncommitted edit is visible in
# the point's log.

EXECUTION = "02-inference"

FREEZE = [
    "deployment/api",
    "deployment/tei-embeddings",
]

# Ceilings are set out of reach: a point that touches one measured the ceiling
# rather than the system, and is discarded (02-inference/K2).
GATES = [
    {"deployment": "api", "floor": 2, "ceiling": 50},
    {"deployment": "tei-embeddings", "floor": 2, "ceiling": 50},
]

# Retrieval latency is a function of what is indexed. Written back from
# 01-ingestion into 00-baseline §2 Envelope.
MIN_COLLECTION_POINTS = 0          # <-- set from 00-baseline §2 before freezing

# The served rate must track the offered rate, or the generator queued its own
# excess and the percentile describes the queue (02-inference/K3).
SERVED_RATE_FLOOR = 0.95

BUFFER_SECONDS = 300

# The generator produces load and nothing else. Served rate, errors and latency
# are read from Prometheus, never from its stdout: one instrument per figure, and
# it is the one named in the register.
GENERATOR = ["k6", "run", "--tag", "point={run}", "./load.js"]
GENERATOR_ENV = {"TARGET_RATE": "{rate}", "DURATION": "{duration}"}


def print_constants() -> None:
    gates = " ".join(f"{g['deployment']}[{g['floor']}..{g['ceiling']}]"
                     for g in GATES)
    print(f"{lk.ARROW} frozen     : freeze={', '.join(FREEZE)}")
    print(f"{lk.ARROW}              gates={gates} buffer={BUFFER_SECONDS}s "
          f"min points={MIN_COLLECTION_POINTS}")


# --------------------------------------------------------------------------- collection

def collection_points(url: str, collection: str) -> int:
    body = lk.http_json(
        "POST", f"{url}/collections/{collection}/points/count", {"exact": True})
    return int(body.get("result", {}).get("count", 0) or 0)


# --------------------------------------------------------------------------- preflight

def preflight(env: lk.Env, freeze_file: Path) -> dict:
    print(f"{lk.ARROW} preflight")
    failures: list[str] = []
    facts: dict = {}

    opening = {}
    for gate in GATES:
        name, floor = gate["deployment"], gate["floor"]
        try:
            replicas = lk.deployment_replicas(env.namespace_for(name), name)
        except RuntimeError as e:
            failures.append(f"{name} unreadable — {e}")
            continue
        opening[name] = replicas
        print(f"[{lk.OK if replicas == floor else lk.BAD}] {name} replicas = "
              f"{replicas} (must open at {floor})")
        if replicas != floor:
            failures.append(
                f"{name} at {replicas} rather than {floor} — this point would carry "
                f"capacity the previous point paid for")
    facts["replicas_at_open"] = opening

    url, name = env.need("qdrant.url"), env.need("qdrant.collection")
    try:
        points = collection_points(url, name)
        ok = points >= MIN_COLLECTION_POINTS
        print(f"[{lk.OK if ok else lk.BAD}] collection points = {points} "
              f"(at least {MIN_COLLECTION_POINTS})")
        facts["collection_points"] = points
        if not ok:
            failures.append(
                f"collection holds {points} against a required "
                f"{MIN_COLLECTION_POINTS} — retrieval latency is a function of what "
                f"is indexed")
    except RuntimeError as e:
        failures.append(f"collection unreachable — {e}")

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
        print(f"{lk.BAD} preflight failed:")
        for item in failures:
            print(f"         {item}")
        sys.exit(lk.EXIT_PREFLIGHT)

    print(f"{lk.ARROW} preflight clean")
    return facts


# --------------------------------------------------------------------------- generator

def run_generator(env: lk.Env, args, out_dir: Path) -> dict:
    subs = {"rate": str(args.rate), "duration": args.duration, "run": args.run,
            "base_url": str(env.need("api.base_url"))}
    cmd = [part.format(**subs) for part in GENERATOR]
    extra = {k: v.format(**subs) for k, v in GENERATOR_ENV.items()}
    extra["BASE_URL"] = subs["base_url"]

    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"{args.run}.generator.log"

    print(f"{lk.ARROW} generator  : {' '.join(cmd)}")
    t_start = lk.utcnow()
    with log_path.open("w") as handle:
        proc = subprocess.run(cmd, stdout=handle, stderr=subprocess.STDOUT,
                              env={**os.environ, **extra})
    t_generator_end = lk.utcnow()

    print(f"[{lk.OK if proc.returncode == 0 else lk.WARN}] generator exit "
          f"{proc.returncode} · log at {log_path}")
    if proc.returncode != 0:
        print(f"{lk.WARN} a non-zero generator exit does not invalidate the point on "
              f"its own — the guards decide")
    return {"t_start": t_start, "t_generator_end": t_generator_end,
            "generator_rc": proc.returncode, "generator_log": str(log_path)}


# --------------------------------------------------------------------------- settle

def wait_for_scale_in(env: lk.Env, run: dict) -> dict:
    """The window closes when every gated deployment is back at its floor, plus
    the buffer. Scale-in is billed and belongs to the point that caused it."""
    poll = env.poll_seconds
    floors = {g["deployment"]: g["floor"] for g in GATES}
    ceilings = {g["deployment"]: g["ceiling"] for g in GATES}

    print()
    print(f"{lk.ARROW} waiting for scale-in — poll {poll}s · buffer "
          f"{BUFFER_SECONDS}s")

    wall_start = lk.utcnow()
    at_floor_since = None
    peak = {name: 0 for name in floors}
    ceiling_hits: list[str] = []

    while True:
        now = lk.utcnow()
        if (now - wall_start).total_seconds() > env.max_wait_seconds:
            print()
            print(f"{lk.BAD} the serving tier never returned to its floor.")
            print("         Nothing exported. Investigate, then export by hand.")
            sys.exit(lk.EXIT_TIMEOUT)

        try:
            current = {name: lk.deployment_replicas(env.namespace_for(name), name)
                       for name in floors}
        except RuntimeError as e:
            print(f"{lk.WARN} poll failed ({e}) — retrying")
            time.sleep(poll)
            continue

        for name, value in current.items():
            peak[name] = max(peak[name], value)
            if value >= ceilings[name] and name not in ceiling_hits:
                ceiling_hits.append(name)
                print(f"{lk.WARN} {name} reached its configured ceiling "
                      f"({ceilings[name]}) — this point measures the ceiling rather "
                      f"than the system → K2")

        if all(current[name] <= floor for name, floor in floors.items()):
            if at_floor_since is None:
                at_floor_since = now
                print(f"{lk.ARROW} all gates at floor — holding {BUFFER_SECONDS}s "
                      f"buffer")
            elif (now - at_floor_since).total_seconds() >= BUFFER_SECONDS:
                t_end = at_floor_since + timedelta(seconds=BUFFER_SECONDS)
                break
        elif at_floor_since is not None:
            at_floor_since = None
            print(f"{lk.WARN} replicas rose again — buffer reset")

        state = " ".join(f"{n}={v}" for n, v in sorted(current.items()))
        print(f"    {lk.rfc3339(now)}  settle  {state}")
        time.sleep(poll)

    print()
    print(f"{lk.ARROW} window closed — {lk.rfc3339(run['t_start'])} .. "
          f"{lk.rfc3339(t_end)}")
    return {"t_end": t_end, "peak_replicas": peak, "ceiling_hits": ceiling_hits,
            "wall_seconds": (t_end - run["t_start"]).total_seconds()}


# --------------------------------------------------------------------------- block

def point_block(args, facts, run, settle, guard_failures) -> str:
    dirty = "  ⚠ WORKING TREE DIRTY" if facts.get("dirty") else ""
    lines = [
        f"#### {args.run} · offered rate = {args.rate} rps · {args.duration}",
        "",
        f"Commit: `{facts.get('commit', 'unknown')}`{dirty}",
        f"Window UTC: {lk.rfc3339(run['t_start'])} → {lk.rfc3339(settle['t_end'])} "
        f"· {lk.hms(settle['wall_seconds'])}",
        f"Generator ended: {lk.rfc3339(run['t_generator_end'])} · exit "
        f"{run['generator_rc']}",
        "",
    ]
    rows = [("Served rate", "⟨from export⟩"),
            ("p95 latency", "⟨from export⟩"),
            ("Error share", "⟨from export⟩")]
    rows += [(f"{name} peak replicas", str(value))
             for name, value in sorted(settle["peak_replicas"].items())]
    rows += [("Serving $ net of floor", "⟨cost pass⟩"),
             ("$/1M queries", "⟨cost pass⟩")]
    lines += lk.md_table(rows)
    lines += [
        "",
        f"Collection points at open: {facts.get('collection_points', '⟨⟩')}",
        f"Ceiling hits: {', '.join(settle['ceiling_hits']) or 'none'}",
        f"Guards breached: {', '.join(guard_failures) or 'none'}",
        "",
        "**Saturation signal** — ⟨component⟩, read from ⟨ref⟩ at ⟨value⟩",
        "",
        "Validity — ⟨valid · discarded, hit a configured ceiling · re-run, reason ⟨⟩⟩",
        "Notes — ⟨⟩",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- main

def main() -> int:
    exec_dir = lk.execution_dir(EXECUTION)

    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", help="point id, e.g. inference-r200")
    p.add_argument("--rate", help="offered arrival rate for this point")
    p.add_argument("--duration", default="10m", help="generator run length")
    p.add_argument("--env", default=str(lk.default_env_path()))
    p.add_argument("--series", default=str(exec_dir / "data" / "series.txt"))
    p.add_argument("--guards", default=str(exec_dir / "data" / "guards.txt"))
    p.add_argument("--step", default="15s")
    p.add_argument("--no-port-forward", action="store_true")
    p.add_argument("--preflight-only", action="store_true")
    p.add_argument("--set-freeze", action="store_true")
    args = p.parse_args()

    env = lk.Env(Path(args.env))
    out_dir = exec_dir / "data"
    freeze_file = exec_dir / "image-freeze.json"
    series_file, guards_file = Path(args.series), Path(args.guards)

    forwards = [lk.forward_spec(env, "prometheus"), lk.forward_spec(env, "qdrant"),
                lk.forward_spec(env, "api")]
    with lk.PortForwards(forwards, enabled=not args.no_port_forward):
        if args.set_freeze:
            images = lk.frozen_images(env, FREEZE)
            freeze_file.parent.mkdir(parents=True, exist_ok=True)
            freeze_file.write_text(json.dumps(images, indent=2, sort_keys=True) + "\n")
            print(json.dumps(images, indent=2, sort_keys=True))
            print(f"{lk.ARROW} freeze written to {freeze_file}")
            return lk.EXIT_CLEAN

        if not args.run or not args.rate:
            lk.die("--run and --rate are required (or use --set-freeze)")
        if (out_dir / f"{args.run}.jsonl").exists():
            lk.die(f"{out_dir / (args.run + '.jsonl')} exists — pick another --run id")

        try:
            rate_floor = float(args.rate) * SERVED_RATE_FLOOR
        except ValueError:
            lk.die(f"--rate must be a number, got {args.rate!r}")
        guards = lk.load_guards(guards_file, {"rate": args.rate,
                                              "rate_floor": f"{rate_floor:g}"})

        print(f"{lk.ARROW} execution  : {EXECUTION}")
        print(f"{lk.ARROW} point      : {args.run}  ·  rate={args.rate}")
        print(f"{lk.ARROW} env        : {env.path}")
        print(f"{lk.ARROW} series     : {series_file}")
        print(f"{lk.ARROW} guards     : {guards_file} "
              f"({', '.join(g['ref'] for g in guards)}) · served-rate floor "
              f"{rate_floor:g}")
        print_constants()
        print()

        facts = preflight(env, freeze_file)
        if args.preflight_only:
            print(f"{lk.ARROW} preflight only — nothing started")
            return lk.EXIT_CLEAN

        run = run_generator(env, args, out_dir)
        settle = wait_for_scale_in(env, run)

        rc = lk.run_export(series_file, args.run, run["t_start"], settle["t_end"],
                           args.step, env.prom_url, out_dir)
        if rc != 0:
            print()
            print(f"{lk.BAD} export returned {rc} — WINDOW PRESERVED.")
            lk.reexport_hint(series_file, args.run, run["t_start"], settle["t_end"],
                             out_dir)
            return lk.EXIT_EXPORT_GAP

        print()
        guard_failures = lk.check_guards(env.prom_url, guards)
        if settle["ceiling_hits"]:
            guard_failures.append("configured replica ceiling reached")

        block = point_block(args, facts, run, settle, guard_failures)
        record = {
            "execution": EXECUTION, "point": args.run,
            "offered_rate": args.rate, "duration": args.duration,
            "commit": facts.get("commit"), "dirty": facts.get("dirty"),
            "window": {"start": lk.rfc3339(run["t_start"]),
                       "end": lk.rfc3339(settle["t_end"]),
                       "generator_end": lk.rfc3339(run["t_generator_end"]),
                       "wall_seconds": settle["wall_seconds"]},
            "peak_replicas": settle["peak_replicas"],
            "ceiling_hits": settle["ceiling_hits"],
            "collection_points": facts.get("collection_points"),
            "generator_rc": run["generator_rc"],
            "guard_failures": guard_failures,
            "freeze": facts.get("images"),
        }
        md_path = lk.write_point(out_dir, args.run, block, record)

        print()
        print("=" * 78)
        print(block)
        print("=" * 78)
        print(f"{lk.ARROW} paste the block into the Journal · also at {md_path}")

        return lk.report_validity([], guard_failures)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        sys.exit(130)
