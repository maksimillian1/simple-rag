#!/usr/bin/env python3
"""inspect-metrics.py — read a point's exported Prometheus series and either
print a summary or flatten it to CSV.

export-metrics.py (called by run-ingestion-point.py / run-inference-point.py)
writes one JSON line per ref (M1, M2, ...), each holding the raw Prometheus
range-query result: a list of series, each a label set plus a
[timestamp, "value"] array. This is that file's counterpart for actually
looking at what landed — nothing reads these files today except by hand.

    ./inspect-metrics.py --file ../executions/01-ingestion/data/ingestion-n50-test.jsonl
    ./inspect-metrics.py --file ...jsonl --csv out.csv
    ./inspect-metrics.py --file ...jsonl --ref M9

Requires: nothing beyond the standard library.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

# Labels that identify the scrape target rather than what's being measured —
# dropped from the printed series label so the summary reads by what the
# series *is*, not which pod happened to report it.
NOISY_LABELS = {"instance", "job", "endpoint", "container", "__name__",
                 "namespace", "service", "pod"}


def label_summary(labels: dict) -> str:
    kept = {k: v for k, v in labels.items() if k not in NOISY_LABELS}
    if not kept:
        kept = labels
    return ", ".join(f"{k}={v}" for k, v in sorted(kept.items())) or "(no labels)"


def parse_values(values: list) -> list[tuple[float, float]]:
    out = []
    for ts, raw in values:
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        if v != v:  # NaN
            continue
        out.append((float(ts), v))
    return out


def load_lines(path: Path) -> list[dict]:
    if not path.is_file():
        sys.exit(f"not found: {path}")
    lines = []
    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            lines.append(json.loads(raw))
        except json.JSONDecodeError as e:
            sys.exit(f"{path}:{lineno} not valid JSON: {e}")
    return lines


def print_summary(lines: list[dict], only_ref: str | None) -> None:
    for entry in lines:
        ref = entry.get("metric", "?")
        if only_ref and ref != only_ref:
            continue
        query = entry.get("query", "")
        result = entry.get("result", [])
        print(f"\n{ref} · {query[:100]}{'...' if len(query) > 100 else ''}")
        print(f"  series: {len(result)}")
        if not result:
            print("  NO DATA")
            continue
        for series in result:
            points = parse_values(series.get("values", []))
            label = label_summary(series.get("metric", {}))
            if not points:
                print(f"  {label}: no numeric samples")
                continue
            vals = [v for _, v in points]
            print(f"  {label}: n={len(vals)} min={min(vals):.4g} "
                  f"max={max(vals):.4g} avg={statistics.fmean(vals):.4g} "
                  f"last={vals[-1]:.4g}")


def write_csv(lines: list[dict], only_ref: str | None, out_path: Path) -> tuple[int, int, int]:
    refs = series = rows = 0
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ref", "query", "series_labels", "timestamp_utc",
                         "timestamp_epoch", "value"])
        for entry in lines:
            ref = entry.get("metric", "?")
            if only_ref and ref != only_ref:
                continue
            query = entry.get("query", "")
            result = entry.get("result", [])
            refs += 1
            for s in result:
                label = label_summary(s.get("metric", {}))
                points = parse_values(s.get("values", []))
                series += 1
                for ts, v in points:
                    iso = datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ")
                    writer.writerow([ref, query, label, iso, ts, v])
                    rows += 1
    return refs, series, rows


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--file", required=True, help="the point's .jsonl export")
    p.add_argument("--ref", help="only this metric ref, e.g. M9")
    p.add_argument("--csv", help="also write a long-format CSV here")
    args = p.parse_args()

    path = Path(args.file)
    lines = load_lines(path)
    if not lines:
        sys.exit(f"{path}: no entries")

    if args.ref and not any(l.get("metric") == args.ref for l in lines):
        available = ", ".join(sorted(l.get("metric", "?") for l in lines))
        sys.exit(f"no ref {args.ref!r} in {path} — available: {available}")

    print_summary(lines, args.ref)

    if args.csv:
        out_path = Path(args.csv)
        refs, series, rows = write_csv(lines, args.ref, out_path)
        print(f"\n-> wrote {refs} refs, {series} series, {rows} rows -> {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
