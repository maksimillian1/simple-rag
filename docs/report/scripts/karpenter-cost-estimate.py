#!/usr/bin/env python3
"""karpenter-cost-estimate.py — provisional per-window compute cost from node
lifecycle, without waiting on CUR.

CUR 2.0 (00-baseline §2: "source of record") lags real usage by roughly a day
before a line even appears, and 00-baseline §1 K3 asks for another 48h before
trusting it as final. That's fine for the once-per-campaign cost pass, but it
means you can't tell mid-sweep whether a point looked expensive. This script
answers that faster, for the one place it's cleanly possible: apps-compute and
apps-serving nodes are Karpenter-provisioned and fully torn down between
points (01-ingestion §1 Axis), so each node's own lifetime — read straight
from kube-state-metrics, seconds behind real time — times its price at that
time (on-demand list price, or the real Spot price paid, both from AWS's own
APIs) reconstructs the same number CUR would eventually show for M10 (compute)
and, for `apps-serving`, the input D23 needs (subtract 00-baseline's serving
floor rate yourself — this script reports the gross node cost, not net).

Does NOT replace CUR for M13/M14 (SQS/S3/NAT) or for the report's own cost
figures — treat this as a same-day cross-check, not the source of record.
Cross-check it against the real CUR read once available; if they agree within
a few percent, later sweeps can lean on this alone between points.

Usage:
    ./karpenter-cost-estimate.py --start 2026-09-03T15:19:31Z --end 2026-09-03T15:57:48Z \\
        --nodepool apps-compute

    ./karpenter-cost-estimate.py --last 40m --nodepool apps-compute --nodepool apps-serving \\
        --format csv

Stdlib + `aws` CLI on PATH (pricing + spot history) + Prometheus reachable
(see labkit.Env — same env.yaml every run script uses).

Exit codes: 0 clean · 1 usage/connection error · 2 one or more nodes priced
at $0 because neither pricing source had a rate for their instance type (the
total is a floor, not the real number — said loudly, not silently).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.parse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labkit as lk  # noqa: E402

PRICING_REGION_ENDPOINT = "us-east-1"  # AWS Pricing API is only served from here/ap-south-1
LOCATION_BY_REGION = {
    "eu-central-1": "EU (Frankfurt)",
}


def prom_query_range(prom_url: str, query: str, start: datetime, end: datetime,
                      step: str) -> list[dict]:
    params = {
        "query": query,
        "start": start.timestamp(),
        "end": end.timestamp(),
        "step": step,
    }
    url = f"{prom_url}/api/v1/query_range?" + urllib.parse.urlencode(params)
    data = lk.http_json("GET", url)
    if data.get("status") != "success":
        raise RuntimeError(data.get("error", "prometheus range query failed"))
    return data.get("data", {}).get("result", [])


def node_lifecycle(prom_url: str, nodepools: list[str], start: datetime, end: datetime,
                    step: str) -> list[dict]:
    """One row per node: name, nodepool, instance-id, and [first_seen,
    last_seen] clipped to [start, end]. Type/AZ/capacity-type come from EC2
    directly (resolve_instances below) — kube_node_info's `provider_id` is a
    built-in kube-state-metrics label, not gated by metricLabelsAllowlist, so
    this works on historical (already-terminated) nodes without needing that
    config change at all; the allowlist fix is a fallback for whenever EC2's
    own terminated-instance visibility window (about an hour) has passed."""
    pool_re = "|".join(nodepools)
    pool_query = f'kube_node_labels{{label_karpenter_sh_nodepool=~"{pool_re}"}}'
    pool_series = prom_query_range(prom_url, pool_query, start, end, step)

    timing: dict[str, dict] = {}
    for s in pool_series:
        labels = s["metric"]
        values = s.get("values", [])
        if not values:
            continue
        node = labels.get("node", "?")
        ts = [float(v[0]) for v in values]
        timing[node] = {
            "nodepool": labels.get("label_karpenter_sh_nodepool", "?"),
            "first_seen": max(start, datetime.fromtimestamp(min(ts), tz=timezone.utc)),
            "last_seen": min(end, datetime.fromtimestamp(max(ts), tz=timezone.utc)),
        }
    if not timing:
        return []

    info_series = prom_query_range(prom_url, "kube_node_info", start, end, step)
    provider_id: dict[str, str] = {}
    for s in info_series:
        node = s["metric"].get("node", "?")
        if node in timing and node not in provider_id:
            provider_id[node] = s["metric"].get("provider_id", "")

    rows = []
    for node, t in timing.items():
        pid = provider_id.get(node, "")
        instance_id = pid.rsplit("/", 1)[-1] if pid else None
        rows.append({"node": node, "instance_id": instance_id, **t})
    return rows


def resolve_instances(rows: list[dict]) -> None:
    """Fills instance_type/az/capacity_type on each row in place, via a single
    batched EC2 call — works for running instances and (for about an hour
    after termination) already-gone ones alike."""
    ids = sorted({r["instance_id"] for r in rows if r["instance_id"]})
    if not ids:
        return
    cmd = ["aws", "ec2", "describe-instances", "--instance-ids", *ids, "--output", "json"]
    try:
        data = lk.sh_json(cmd, timeout=30)
    except RuntimeError as e:
        print(f"{lk.WARN} describe-instances failed ({e}) — falling back to "
              f"kube_node_labels for whatever it has")
        return

    by_id = {}
    for res in data.get("Reservations", []):
        for inst in res.get("Instances", []):
            by_id[inst["InstanceId"]] = inst

    for r in rows:
        inst = by_id.get(r["instance_id"])
        if inst is None:
            r["instance_type"] = "?"
            r["az"] = "?"
            r["capacity_type"] = "?"
            continue
        r["instance_type"] = inst.get("InstanceType", "?")
        r["az"] = inst.get("Placement", {}).get("AvailabilityZone", "?")
        r["capacity_type"] = "spot" if inst.get("InstanceLifecycle") == "spot" else "on-demand"


_ondemand_cache: dict[str, float | None] = {}


def ondemand_hourly(instance_type: str, region: str) -> float | None:
    if instance_type in _ondemand_cache:
        return _ondemand_cache[instance_type]

    location = LOCATION_BY_REGION.get(region)
    if location is None:
        _ondemand_cache[instance_type] = None
        return None

    cmd = [
        "aws", "pricing", "get-products",
        "--service-code", "AmazonEC2",
        "--region", PRICING_REGION_ENDPOINT,
        "--filters",
        f"Type=TERM_MATCH,Field=instanceType,Value={instance_type}",
        f"Type=TERM_MATCH,Field=location,Value={location}",
        "Type=TERM_MATCH,Field=operatingSystem,Value=Linux",
        "Type=TERM_MATCH,Field=tenancy,Value=Shared",
        "Type=TERM_MATCH,Field=preInstalledSw,Value=NA",
        "Type=TERM_MATCH,Field=capacitystatus,Value=Used",
        "--output", "json",
    ]
    try:
        data = lk.sh_json(cmd, timeout=30)
    except RuntimeError:
        _ondemand_cache[instance_type] = None
        return None

    for price_list_entry in data.get("PriceList", []):
        product = json.loads(price_list_entry)
        terms = product.get("terms", {}).get("OnDemand", {})
        for term in terms.values():
            for dim in term.get("priceDimensions", {}).values():
                usd = dim.get("pricePerUnit", {}).get("USD")
                if usd:
                    rate = float(usd)
                    _ondemand_cache[instance_type] = rate
                    return rate

    _ondemand_cache[instance_type] = None
    return None


_spot_cache: dict[tuple[str, str], float | None] = {}


def spot_hourly(instance_type: str, az: str, at: datetime) -> float | None:
    key = (instance_type, az)
    if key in _spot_cache:
        return _spot_cache[key]

    window_start = at - timedelta(hours=1)
    cmd = [
        "aws", "ec2", "describe-spot-price-history",
        "--instance-types", instance_type,
        "--availability-zone", az,
        "--product-descriptions", "Linux/UNIX",
        "--start-time", lk.rfc3339(window_start),
        "--end-time", lk.rfc3339(at + timedelta(minutes=1)),
        "--output", "json",
    ]
    try:
        data = lk.sh_json(cmd, timeout=30)
    except RuntimeError:
        _spot_cache[key] = None
        return None

    history = data.get("SpotPriceHistory", [])
    if not history:
        _spot_cache[key] = None
        return None

    rate = float(history[0]["SpotPrice"])  # most recent ≤ end-time, API returns newest-first
    _spot_cache[key] = rate
    return rate


def price_row(row: dict, region: str) -> float | None:
    if row["capacity_type"] == "spot":
        return spot_hourly(row["instance_type"], row["az"], row["first_seen"])
    return ondemand_hourly(row["instance_type"], region)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Provisional Karpenter node-lifecycle cost estimate — see module "
                    "docstring for what this is and isn't a substitute for.")
    p.add_argument("--nodepool", action="append", required=True,
                    help="repeatable, e.g. --nodepool apps-compute --nodepool apps-serving")
    p.add_argument("--start", help="RFC3339 window start")
    p.add_argument("--end", help="RFC3339 window end")
    p.add_argument("--last", help="window ending now, e.g. 40m")
    p.add_argument("--step", default="15s")
    p.add_argument("--region", default="eu-central-1")
    p.add_argument("--env", default=str(lk.default_env_path()))
    p.add_argument("--format", choices=["table", "csv", "json"], default="table")
    args = p.parse_args()

    env = lk.Env(Path(args.env))
    prom_url = env.prom_url

    now = lk.utcnow()
    if args.last:
        unit = args.last[-1]
        n = float(args.last[:-1])
        delta = {"s": 1, "m": 60, "h": 3600}.get(unit)
        if delta is None:
            lk.die(f"--last: bad unit in {args.last!r} (expected s/m/h)")
        start, end = now - timedelta(seconds=n * delta), now
    elif args.start and args.end:
        start, end = lk.parse_instant(args.start), lk.parse_instant(args.end)
    else:
        lk.die("--start/--end or --last is required")

    # Diagnostics go to stderr so --format json/csv produce clean, pipeable
    # stdout. Unredirected in a terminal, stderr and stdout still interleave
    # visibly, so --format table reads exactly as before.
    def log(msg: str) -> None:
        print(msg, file=sys.stderr)

    log(f"{lk.ARROW} window   : {lk.rfc3339(start)} .. {lk.rfc3339(end)}")
    log(f"{lk.ARROW} nodepools: {', '.join(args.nodepool)}")
    log(f"{lk.ARROW} prom     : {prom_url}\n")

    rows = node_lifecycle(prom_url, args.nodepool, start, end, args.step)
    if not rows:
        log(f"{lk.WARN} no nodes seen in this window for these nodepools "
            f"(pool at zero the whole time, or Prometheus retention already expired it)")
        return 0
    resolve_instances(rows)

    priced_rows = []
    unpriced = 0
    for row in rows:
        hours = (row["last_seen"] - row["first_seen"]).total_seconds() / 3600
        rate = price_row(row, args.region)
        if rate is None:
            unpriced += 1
            rate = 0.0
        cost = hours * rate
        priced_rows.append({**row, "hours": hours, "rate": rate, "cost": cost})

    if args.format == "json":
        print(json.dumps([{
            **r,
            "first_seen": lk.rfc3339(r["first_seen"]),
            "last_seen": lk.rfc3339(r["last_seen"]),
        } for r in priced_rows], indent=2))
    elif args.format == "csv":
        print("node,nodepool,instance_type,capacity_type,az,hours,rate,cost")
        for r in priced_rows:
            print(f'{r["node"]},{r["nodepool"]},{r["instance_type"]},{r["capacity_type"]},'
                  f'{r["az"]},{r["hours"]:.4f},{r["rate"]:.4f},{r["cost"]:.4f}')
    else:
        for r in priced_rows:
            flag = " (unpriced!)" if r["rate"] == 0 else ""
            print(f'  {r["node"]:<55} {r["nodepool"]:<14} {r["instance_type"]:<14} '
                  f'{r["capacity_type"]:<10} {r["hours"]:>6.3f}h  x ${r["rate"]:.4f}/h '
                  f'= ${r["cost"]:.4f}{flag}')

    by_pool: dict[str, float] = defaultdict(float)
    for r in priced_rows:
        by_pool[r["nodepool"]] += r["cost"]

    log(f"\n{lk.ARROW} totals by nodepool:")
    for pool, cost in sorted(by_pool.items()):
        log(f"    {pool:<20} ${cost:.4f}")
    log(f"    {'ALL':<20} ${sum(by_pool.values()):.4f}")

    if unpriced:
        log(f"\n{lk.WARN} {unpriced} node(s) had no rate from either pricing source "
            f"(counted as $0) — the total above is a floor, not the real number")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
