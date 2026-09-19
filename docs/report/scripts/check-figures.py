#!/usr/bin/env python3
"""check-figures.py — fail the report when its numbers drift.

Three checks against docs/report/figures.yaml:

    retired   a number the report used to print appears in a scanned document.
              This is the error that keeps happening: a rate is revised, the
              new value lands in one file and the old one survives in four.
              Fails the run.

    coverage  a figure that declares appears_in is missing from that file, or
              present with a different value. Informational by default, since
              sections 2-4 of tasks.md have not propagated the new floor yet;
              --strict turns it into a failure.

    orphans   currency tokens in a document that match no figure. Opt-in with
              --orphans, always informational: the execution documents carry
              per-run costs that are not report-level figures.

Usage:
    ./check-figures.py
    ./check-figures.py --strict
    ./check-figures.py --orphans report.md
"""

import argparse
import pathlib
import re
import sys

import figures as figures_model

ROOT = figures_model.ROOT
MONEY = re.compile(r"\$\s?-?\d[\d,]*(?:\.\d+)?")


def scan_paths(doc):
    paths = []
    for entry in doc.get("scan", []):
        for path in sorted(ROOT.glob(entry)):
            if path.is_file():
                paths.append(path)
    return paths


def allowed(doc, pattern, rel, line):
    for item in doc.get("allow", []):
        if str(item.get("pattern")) != pattern:
            continue
        if item.get("file") and str(item["file"]) != rel:
            continue
        if item.get("must_contain") and str(item["must_contain"]) not in line:
            continue
        return True
    return False


def check_retired(doc, paths):
    hits = []
    for item in doc.get("retired", []):
        pattern = str(item["pattern"])
        for path in paths:
            rel = str(path.relative_to(ROOT))
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if pattern in line and not allowed(doc, pattern, rel, line):
                    hits.append((path, number, pattern, item.get("replaced_by", ""), line.strip()))
    return hits


def check_coverage(doc, values):
    rows = []
    for name, spec in doc["figures"].items():
        for rel in (spec or {}).get("appears_in", []):
            path = ROOT / rel
            wanted = figures_model.display(name, values[name], doc)
            if not path.exists():
                rows.append((name, rel, "NO FILE", wanted))
            elif wanted in path.read_text():
                rows.append((name, rel, "ok", wanted))
            else:
                rows.append((name, rel, "MISSING", wanted))
    return rows


def check_orphans(doc, values, rel):
    path = ROOT / rel
    if not path.exists():
        return None
    numeric = [v for v in values.values() if v is not figures_model.PENDING]
    known = {figures_model.display(n, v, doc) for n, v in values.items()}
    known |= {f"{v:,.0f}" for v in numeric}
    known |= {f"{v:,.2f}" for v in numeric}
    orphans = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        for token in MONEY.findall(line):
            bare = token.replace("$", "").strip()
            if bare not in known:
                orphans.setdefault(bare, []).append(number)
    return orphans


def main():
    parser = argparse.ArgumentParser(description="check the report against figures.yaml")
    parser.add_argument("--strict", action="store_true", help="missing coverage fails too")
    parser.add_argument("--orphans", help="list currency tokens in this file that match no figure")
    parser.add_argument("--path", help="alternative figures.yaml")
    args = parser.parse_args()

    doc = figures_model.load(args.path)
    values = figures_model.resolve(doc)
    paths = scan_paths(doc)
    failed = False

    print(f"scanned {len(paths)} documents, {len(doc['figures'])} figures\n")

    hits = check_retired(doc, paths)
    print("retired values")
    if hits:
        failed = True
        for path, number, pattern, replaced_by, line in hits:
            rel = path.relative_to(ROOT)
            new = figures_model.display(replaced_by, values[replaced_by], doc) if replaced_by in values else "?"
            print(f"  FAIL {rel}:{number}  {pattern} -> {replaced_by} = {new}")
            print(f"       {line[:120]}")
    else:
        print("  none")

    rows = check_coverage(doc, values)
    missing = [r for r in rows if r[2] != "ok"]
    print(f"\ncoverage: {len(rows) - len(missing)}/{len(rows)} figures present where declared")
    for name, rel, status, wanted in missing:
        print(f"  {status:<8} {name:<24} {wanted:>12}  expected in {rel}")
    if missing and args.strict:
        failed = True

    if args.orphans:
        orphans = check_orphans(doc, values, args.orphans)
        print(f"\norphan currency tokens in {args.orphans}")
        if orphans is None:
            print("  no such file")
        elif not orphans:
            print("  none")
        else:
            for token in sorted(orphans, key=lambda t: -len(orphans[t])):
                lines = ", ".join(str(n) for n in orphans[token][:6])
                print(f"  ${token:<12} lines {lines}")

    print()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
