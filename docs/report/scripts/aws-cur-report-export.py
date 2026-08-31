#!/usr/bin/env python3
"""aws-cur-report-export.py — sum AWS CUR 2.0 cost over one window.

Reads a CUR 2.0 Parquet export, keeps rows whose usage hour falls inside a window,
and sums one cost column grouped by keys you name. Group keys may be plain CUR
columns or user tags; tags resolve against both the CUR 2.0 map column
(resource_tags) and the CUR 1.0 flat column (resource_tags_user_<key>).

CUR aggregates usage into clock hours. A window that does not start on the hour
still pulls whole hourly buckets, so run this on hour-aligned ranges.

Examples
--------
  # one hour, grouped by product and tier
  aws-cur-report-export.py --data s3://bill-export/cur2/ \
                --start 2026-09-01T14:00:00Z --hours 1 \
                --group line_item_product_code,tier

  # the same hour, only the ingestion pool, with the pod-level split
  aws-cur-report-export.py --data ./data/cur/ --start 2026-09-01T14:00:00Z \
                --tag tier=apps-compute --split

  # schema and tag coverage, no window
  aws-cur-report-export.py --data s3://bill-export/cur2/ --dry-run

Exit codes: 0 ok · 1 bad arguments or unreadable data · 2 required column missing
· 3 window empty.

Requires: pyarrow.
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone

try:
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.dataset as ds
    from pyarrow import fs as pafs
except ImportError:
    sys.exit("pyarrow is required: pip install pyarrow")

TIME_COL = "line_item_usage_start_date"
TYPE_COL = "line_item_line_item_type"
SPLIT_PARENT_COL = "split_line_item_parent_resource_id"
SPLIT_COST_COL = "split_line_item_split_cost"
SPLIT_UNUSED_COL = "split_line_item_unused_cost"

# Frozen in 00-baseline §2 Cost basis. Tax, credits, refunds and monthly fees are
# excluded: they land in an arbitrary hour and corrupt a window.
DEFAULT_TYPES = ("Usage", "DiscountedUsage", "SavingsPlanCoveredUsage")


# --------------------------------------------------------------------------- io

def open_dataset(path):
    """Open a local directory, a single file, or an s3:// prefix as one dataset."""
    if path.startswith("s3://"):
        filesystem, resolved = pafs.FileSystem.from_uri(path)
        return ds.dataset(resolved, filesystem=filesystem, format="parquet",
                          partitioning="hive")
    return ds.dataset(path, format="parquet", partitioning="hive")


def parse_instant(text):
    value = text.strip().replace("Z", "+00:00")
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def time_scalar(dataset, stamp):
    """Match the file's timestamp type, tz-aware or not."""
    field = dataset.schema.field(TIME_COL)
    if pa.types.is_timestamp(field.type) and field.type.tz is None:
        stamp = stamp.replace(tzinfo=None)
    return pa.scalar(stamp, type=field.type)


# ------------------------------------------------------------------- tag access

def tag_candidates(key):
    return (f"resource_tags_user_{key}", f"user_{key}", key)


def tag_array(table, key):
    """Return a string array for a user tag, or None if the key is not present."""
    for name in tag_candidates(key):
        if name in table.column_names:
            return table.column(name)
    if "resource_tags" in table.column_names:
        column = table.column("resource_tags")
        if pa.types.is_map(column.type):
            for name in tag_candidates(key):
                found = pc.map_lookup(column, query_key=name, occurrence="first")
                if pc.sum(pc.invert(pc.is_null(found))).as_py():
                    return found
    return None


def key_array(table, name):
    """Resolve a group key: a real column first, then a user tag."""
    if name in table.column_names:
        return table.column(name)
    found = tag_array(table, name)
    if found is None:
        sys.exit(f"[2] group key not found as a column or a tag: {name}")
    return found


# ------------------------------------------------------------------ aggregation

def to_strings(array):
    return [("" if v is None else str(v)) for v in array.to_pylist()]


def group_sum(table, keys, cost_column):
    """Sum cost_column by keys. Returns rows sorted by cost, descending."""
    columns = [to_strings(key_array(table, k)) for k in keys]
    costs = table.column(cost_column).to_pylist()
    totals, counts = {}, {}
    for index, cost in enumerate(costs):
        bucket = tuple(column[index] for column in columns)
        totals[bucket] = totals.get(bucket, 0.0) + (cost or 0.0)
        counts[bucket] = counts.get(bucket, 0) + 1
    rows = [list(bucket) + [round(total, 6), counts[bucket]]
            for bucket, total in totals.items()]
    rows.sort(key=lambda row: row[-2], reverse=True)
    return rows


def column_sum(table, name):
    if name not in table.column_names:
        return None
    return round(pc.sum(table.column(name)).as_py() or 0.0, 6)


# ---------------------------------------------------------------------- output

def emit(rows, header, fmt, stream=sys.stdout):
    if fmt == "json":
        json.dump([dict(zip(header, row)) for row in rows], stream, indent=2)
        stream.write("\n")
        return
    if fmt == "csv":
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)
        return
    widths = [len(str(h)) for h in header]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    line = "  ".join(str(h).ljust(widths[i]) for i, h in enumerate(header))
    stream.write(line.rstrip() + "\n")
    stream.write("  ".join("-" * w for w in widths) + "\n")
    for row in rows:
        stream.write("  ".join(str(c).ljust(widths[i])
                               for i, c in enumerate(row)).rstrip() + "\n")


# ------------------------------------------------------------------- dry run

def dry_run(dataset, tag_keys):
    schema = dataset.schema
    print(f"files: {len(dataset.files)}")
    print(f"columns: {len(schema)}\n")
    for field in schema:
        print(f"  {field.name}: {field.type}")
    print()
    for name in (TIME_COL, TYPE_COL, SPLIT_PARENT_COL, SPLIT_COST_COL,
                 SPLIT_UNUSED_COL):
        print(f"  {'present' if name in schema.names else 'MISSING'}  {name}")
    if TIME_COL not in schema.names:
        sys.exit("[2] the time column is missing; this is not a CUR 2.0 export")

    sample = dataset.head(200_000)
    print(f"\nsample rows: {sample.num_rows}")
    for key in tag_keys:
        found = tag_array(sample, key)
        if found is None:
            print(f"  tag {key}: NOT RESOLVED")
            continue
        strings = to_strings(found)
        filled = sum(1 for v in strings if v)
        share = 100.0 * filled / len(strings) if strings else 0.0
        print(f"  tag {key}: resolved, non-empty on {share:.1f} % of sampled rows")
    return 0


# ----------------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(
        description="Sum AWS CUR 2.0 cost over one window.")
    parser.add_argument("--data", required=True,
                        help="local path or s3:// prefix of the CUR 2.0 export")
    parser.add_argument("--start", help="window start, ISO 8601 UTC")
    parser.add_argument("--hours", type=float, default=1.0,
                        help="window length in hours (default 1)")
    parser.add_argument("--end", help="window end, ISO 8601 UTC (overrides --hours)")
    parser.add_argument("--cost-column", default="line_item_unblended_cost",
                        help="one cost column, used everywhere (00-baseline §2)")
    parser.add_argument("--group", default="line_item_product_code,tier",
                        help="comma-separated group keys; columns or user tags")
    parser.add_argument("--tag", action="append", default=[], metavar="KEY=VALUE",
                        help="keep only rows carrying this tag value; repeatable")
    parser.add_argument("--types", default=",".join(DEFAULT_TYPES),
                        help="line item types summed")
    parser.add_argument("--split", action="store_true",
                        help="also break split cost allocation rows down by --split-key")
    parser.add_argument("--split-key", default="app",
                        help="pod label the split is grouped by (default app)")
    parser.add_argument("--include-split-rows", action="store_true",
                        help="do not exclude split child rows from the total")
    parser.add_argument("--format", choices=("table", "csv", "json"),
                        default="table")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the schema and tag coverage, read no window")
    args = parser.parse_args()

    group_keys = [k.strip() for k in args.group.split(",") if k.strip()]
    tag_filters = []
    for item in args.tag:
        if "=" not in item:
            sys.exit(f"[1] --tag expects KEY=VALUE, got {item}")
        key, _, value = item.partition("=")
        tag_filters.append((key.strip(), value.strip()))

    try:
        dataset = open_dataset(args.data)
    except Exception as error:                                # noqa: BLE001
        sys.exit(f"[1] cannot open {args.data}: {error}")

    if args.dry_run:
        keys = group_keys + [key for key, _ in tag_filters] + [args.split_key]
        sys.exit(dry_run(dataset, sorted(set(keys))))

    if not args.start:
        sys.exit("[1] --start is required unless --dry-run")
    start = parse_instant(args.start)
    end = parse_instant(args.end) if args.end else start + timedelta(hours=args.hours)
    if end <= start:
        sys.exit("[1] the window ends before it starts")
    if start.minute or start.second:
        print("warning: the window does not start on the hour; CUR buckets are "
              "clock hours and whole buckets are pulled in", file=sys.stderr)

    for name in (TIME_COL, args.cost_column):
        if name not in dataset.schema.names:
            sys.exit(f"[2] required column missing: {name}")

    expression = (
        (ds.field(TIME_COL) >= time_scalar(dataset, start))
        & (ds.field(TIME_COL) < time_scalar(dataset, end))
    )
    types = [t.strip() for t in args.types.split(",") if t.strip()]
    if TYPE_COL in dataset.schema.names and types:
        expression = expression & ds.field(TYPE_COL).isin(types)

    table = dataset.to_table(filter=expression)
    if table.num_rows == 0:
        sys.exit("[3] no rows in the window; check the window, the export prefix "
                 "and the line item types")

    for key, value in tag_filters:
        found = tag_array(table, key)
        if found is None:
            sys.exit(f"[2] tag not resolvable in this export: {key}")
        table = table.filter(pc.equal(found, pa.scalar(value)))
    if table.num_rows == 0:
        sys.exit("[3] the tag filter removed every row in the window")

    split_rows_present = SPLIT_PARENT_COL in table.column_names
    parents = table
    if split_rows_present and not args.include_split_rows:
        parent_column = table.column(SPLIT_PARENT_COL)
        is_parent = pc.or_(pc.is_null(parent_column),
                           pc.equal(parent_column, pa.scalar("")))
        parents = table.filter(is_parent)

    window_label = (f"{start:%Y-%m-%dT%H:%M}Z → {end:%Y-%m-%dT%H:%M}Z "
                    f"({(end - start).total_seconds() / 3600:g} h)")
    print(f"window   {window_label}")
    print(f"data     {args.data}")
    print(f"cost     {args.cost_column}  ·  types {','.join(types)}")
    print(f"rows     {table.num_rows} in window, {parents.num_rows} after the "
          f"split-child guard\n")

    rows = group_sum(parents, group_keys, args.cost_column)
    emit(rows, group_keys + ["cost", "rows"], args.format)

    total = round(sum(row[-2] for row in rows), 6)
    print(f"\ntotal    {total}")

    if split_rows_present:
        children = table.filter(pc.invert(
            pc.or_(pc.is_null(table.column(SPLIT_PARENT_COL)),
                   pc.equal(table.column(SPLIT_PARENT_COL), pa.scalar("")))))
        child_cost = column_sum(children, SPLIT_COST_COL)
        if child_cost is not None:
            print(f"split    {child_cost} over {children.num_rows} child rows "
                  f"({'excluded from' if not args.include_split_rows else 'inside'} "
                  f"the total)")
            unused = column_sum(children, SPLIT_UNUSED_COL)
            if unused is not None:
                print(f"unused   {unused}")
            if child_cost and total:
                drift = 100.0 * (child_cost - total) / total
                print(f"reconcile  split vs total: {drift:+.1f} %  "
                      f"(a large gap means the guard is wrong for this export)")
        if args.split and children.num_rows:
            print()
            split_rows = group_sum(children, [args.split_key], SPLIT_COST_COL)
            emit(split_rows, [args.split_key, "split_cost", "rows"], args.format)


if __name__ == "__main__":
    main()
