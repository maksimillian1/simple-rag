#!/usr/bin/env python3
"""
export-metrics.py — snapshot Prometheus range queries before retention expires.

    ./export-metrics.py --run smoke --queries ../executions/01-ingestion/promql.txt \
                        --last 10m --dry-run

    ./export-metrics.py --run ingestion-n04 \
                        --queries ../executions/01-ingestion/promql.txt \
                        --start 2026-08-20T10:00:00Z --end 2026-08-20T10:25:00Z

Stdlib only — no curl, no jq, no pip install.
Prometheus reachable at $PROM_URL (default http://localhost:9090):
    kubectl -n monitoring port-forward svc/monitoring-kube-prometheus-prometheus 9090:9090

The query name is the register ref. It is printed before the run and carried into
the record, so a block pasted into a Journal names the refs it actually holds.

Exit codes:
    0  all queries returned data
    1  usage / connection error
    2  one or more queries returned no data, or referenced an unknown metric name
       (an empty result is an instrumentation gap, not a zero — fix before the real run)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROM_URL = os.environ.get("PROM_URL", "http://localhost:9090").rstrip("/")
TIMEOUT = int(os.environ.get("PROM_TIMEOUT", "60"))

OK, BAD, WARN, ARROW = "  ok  ", " FAIL ", " warn ", "->"


# --------------------------------------------------------------------------- http

def _get(path: str, params: dict) -> dict:
    url = f"{PROM_URL}{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"HTTP {e.code}: {body}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"cannot reach {PROM_URL}: {e.reason}") from None
    except json.JSONDecodeError:
        raise RuntimeError("response was not JSON — is this a Prometheus endpoint?") from None

    if payload.get("status") != "success":
        raise RuntimeError(payload.get("error", "unknown Prometheus error"))
    return payload["data"]


def healthy() -> None:
    try:
        with urllib.request.urlopen(f"{PROM_URL}/-/healthy", timeout=10):
            pass
    except Exception as e:
        die(f"Prometheus unreachable at {PROM_URL}: {e}")


# --------------------------------------------------------------------------- time

_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def parse_duration(text: str) -> timedelta:
    """'90s' '10m' '2h' '1d' -> timedelta"""
    m = re.fullmatch(r"(\d+)([smhd])", text.strip())
    if not m:
        die(f"bad duration: {text!r} (use 30s, 10m, 2h, 1d)")
    return timedelta(**{_UNITS[m.group(2)]: int(m.group(1))})


def rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_instant(text: str) -> datetime:
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        die(f"bad timestamp: {text!r} (expected 2026-08-20T10:00:00Z)")


# --------------------------------------------------------------------------- queries

def load_queries(path: Path) -> list[tuple[str, str]]:
    """One 'ref|promql' per line. '#' comments and blanks ignored."""
    if not path.is_file():
        die(f"query file not found: {path}")
    out: list[tuple[str, str]] = []
    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            die(f"{path}:{lineno} missing '|' separator")
        name, query = line.split("|", 1)
        name, query = name.strip(), query.strip()
        if not name or not query:
            die(f"{path}:{lineno} empty ref or query")
        out.append((name, query))
    if not out:
        die(f"{path} contains no queries")
    names = [n for n, _ in out]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        die(f"duplicate refs: {', '.join(sorted(dupes))}")
    return out


METRIC_TOKEN = re.compile(r"\b([a-zA-Z_:][a-zA-Z0-9_:]*)\s*(?=[{\[(]|\s|$)")
PROMQL_KEYWORDS = {
    "by", "without", "on", "ignoring", "group_left", "group_right", "offset", "bool",
    "and", "or", "unless", "sum", "avg", "min", "max", "count", "count_values",
    "stddev", "stdvar", "topk", "bottomk", "quantile", "rate", "irate", "increase",
    "delta", "idelta", "deriv", "predict_linear", "avg_over_time", "sum_over_time",
    "max_over_time", "min_over_time", "count_over_time", "quantile_over_time",
    "last_over_time", "histogram_quantile", "label_replace", "label_join", "abs",
    "ceil", "floor", "round", "clamp_max", "clamp_min", "time", "timestamp",
    "vector", "scalar", "absent", "absent_over_time", "changes", "resets", "le",
}


def known_metric_names() -> set[str]:
    try:
        return set(_get("/api/v1/label/__name__/values", {}))
    except RuntimeError:
        return set()


def unknown_metrics(query: str, known: set[str]) -> list[str]:
    """Catch typos in metric names before a run, not after it."""
    if not known:
        return []
    found = set()
    stripped = re.sub(r'"[^"]*"', '""', query)          # ignore string literals
    for token in METRIC_TOKEN.findall(stripped):
        if token in PROMQL_KEYWORDS or token.isdigit():
            continue
        found.add(token)
    return sorted(t for t in found if t not in known)


# --------------------------------------------------------------------------- checks

def preflight_targets() -> None:
    data = _get("/api/v1/query", {"query": "up == 0"})
    down = [
        f'{r["metric"].get("job", "?")}/{r["metric"].get("instance", "?")}'
        for r in data.get("result", [])
    ]
    if down:
        print(f"{WARN} scrape targets DOWN — these components cannot be named as constraints:")
        for d in down:
            print(f"         {d}")


def count_points(result: list) -> int:
    return sum(len(series.get("values", [])) for series in result)


# --------------------------------------------------------------------------- main

def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    p = argparse.ArgumentParser(add_help=True, description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", required=True, help="point id, e.g. ingestion-n04")
    p.add_argument("--queries", required=True,
                   help="path to the execution's promql.txt · never defaulted: a "
                        "file picked up next to this script belongs to whichever "
                        "execution wrote it last")
    p.add_argument("--start", help="RFC3339, e.g. 2026-08-20T10:00:00Z")
    p.add_argument("--end", help="RFC3339")
    p.add_argument("--last", help="window ending now, e.g. 25m")
    p.add_argument("--step", default=os.environ.get("STEP", "15s"))
    p.add_argument("--out-dir", default=os.environ.get("OUT_DIR", "docs/report/data"))
    p.add_argument("--dry-run", action="store_true", help="check only, write nothing")
    p.add_argument("--force", action="store_true", help="overwrite an existing run file")
    args = p.parse_args()

    if args.last:
        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - parse_duration(args.last)
    elif args.start and args.end:
        start_dt, end_dt = parse_instant(args.start), parse_instant(args.end)
    else:
        die("give --last, or both --start and --end")

    if start_dt >= end_dt:
        die("--start is not before --end")

    start, end = rfc3339(start_dt), rfc3339(end_dt)
    queries = load_queries(Path(args.queries))
    refs = [name for name, _ in queries]

    out_path = Path(args.out_dir) / f"{args.run}.jsonl"
    if out_path.exists() and not args.dry_run and not args.force:
        die(f"{out_path} already exists — pick another --run id, or pass --force")

    print(f"{ARROW} prometheus : {PROM_URL}")
    healthy()
    preflight_targets()

    known = known_metric_names()
    if not known:
        print(f"{WARN} could not list metric names — skipping typo check")

    print(f"{ARROW} window     : {start} .. {end}  step={args.step}")
    print(f"{ARROW} queries    : {args.queries} ({len(queries)})")
    print(f"{ARROW} refs       : {', '.join(refs)}")
    print(f"{ARROW} output     : {'(dry run)' if args.dry_run else out_path}")
    print()

    records, gaps = [], []
    for name, query in queries:
        missing = unknown_metrics(query, known)
        if missing:
            print(f"[{BAD}] {name} — unknown metric name(s): {', '.join(missing)}")
            gaps.append(name)
            continue
        try:
            data = _get("/api/v1/query_range", {
                "query": query, "start": start, "end": end, "step": args.step,
            })
        except RuntimeError as e:
            print(f"[{BAD}] {name} — {e}")
            gaps.append(name)
            continue

        result = data.get("result", [])
        points = count_points(result)
        if points == 0:
            print(f"[{BAD}] {name} — NO DATA")
            gaps.append(name)
            continue

        print(f"[{OK}] {name} — {len(result)} series, {points} points")
        records.append({
            "run": args.run, "metric": name, "query": query,
            "start": start, "end": end, "step": args.step, "result": result,
        })

    if not args.dry_run and records:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w") as fh:
            for rec in records:
                fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
        manifest = out_path.with_suffix(".meta.json")
        manifest.write_text(json.dumps({
            "run": args.run, "start": start, "end": end, "step": args.step,
            "prometheus": PROM_URL, "query_file": str(args.queries),
            "refs": refs,
            "exported_at": rfc3339(datetime.now(timezone.utc)),
            "queries_total": len(queries), "queries_with_data": len(records),
            "gaps": gaps,
        }, indent=2) + "\n")

    print()
    print(f"{ARROW} {len(records)}/{len(queries)} queries returned data")
    if gaps:
        print(f"{WARN} empty results are instrumentation gaps, not zeros — fix before the real run:")
        for g in gaps:
            print(f"         {g}")
        return 2
    if args.dry_run:
        print(f"{ARROW} dry run — nothing written")
    else:
        print(f"{ARROW} wrote {out_path} and {out_path.with_suffix('.meta.json')}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
