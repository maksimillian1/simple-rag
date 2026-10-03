#!/usr/bin/env python3
"""Render a report document into rendered/ for publication.

Defaults to article.md, the source of the published article (tasks.md D10). The published
text is always this render, never the source file and never a paste out of report.md:

  python3 docs/report/scripts/render_article.py                 # article.md
  python3 docs/report/scripts/render_article.py report.md        # the full report
  python3 docs/report/scripts/render_article.py --no-check       # skip the registry gate

Three things happen. Figure marks (`$534.12<!--FD26-->`) are stripped, so the text reads
cleanly while the source keeps every number attached to figures.yaml. Repo-relative
pointers in inline code - `00-baseline`'s path, apps/indexer/src/main.py, adr/0017-*.md -
become permalinks pinned to the commit being rendered, so a reader outside the repository
can follow them and they do not rot. And the render is stamped with that commit.

It refuses to run while `report-kit figures check` is dirty: a published number that no
longer resolves is the failure this whole arrangement exists to prevent.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPORT_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = REPORT_DIR.parent.parent
MARK = re.compile(r"<!--\s*F[MRDE]\d+\s*-->")
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
CODE_SPAN = re.compile(r"`([^`\n]+)`")
FENCE = re.compile(r"^```", re.MULTILINE)
CHECK = [sys.executable, "-m", "report_kit.cli", "figures", "--path", "figures.yaml", "check"]


def git(*args):
    done = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else ""


def commit():
    sha = git("rev-parse", "HEAD") or "unknown"
    return f"{sha}-dirty" if git("status", "--porcelain") else sha


def permalink_base():
    url = git("remote", "get-url", "origin")
    if not url:
        return None
    url = re.sub(r"^git@([^:]+):", r"https://\1/", url)
    return url[: -len(".git")] if url.endswith(".git") else url


def link_pointers(text, base, sha):
    def one(match):
        path = match.group(1)
        start, end = match.span()
        if text[max(0, start - 1) : start] == "[" or text[end : end + 2] == "](":
            return match.group(0)
        if ".." in path or not re.fullmatch(r"[\w][\w./-]*\.[\w]+", path):
            return match.group(0)
        if not (REPO_ROOT / path).is_file():
            return match.group(0)
        return f"[`{path}`]({base}/blob/{sha}/{path})"

    # inline code inside a fenced block is sample text, not a pointer
    parts = FENCE.split(text)
    return "".join(p if i % 2 else CODE_SPAN.sub(one, p) for i, p in enumerate(parts))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", nargs="?", default="article.md", help="document under docs/report/")
    ap.add_argument("-o", "--out", help="output path (default: rendered/<source>)")
    ap.add_argument("--no-check", action="store_true", help="render even if the registry check fails")
    ap.add_argument("--no-links", action="store_true", help="leave pointers as inline code")
    args = ap.parse_args()

    source = REPORT_DIR / args.source
    if not source.is_file():
        sys.exit(f"no such document: {source}")

    if not args.no_check:
        done = subprocess.run(CHECK, cwd=REPORT_DIR, capture_output=True, text=True)
        if done.returncode != 0:
            sys.stderr.write(done.stdout + done.stderr)
            sys.exit("registry check is dirty - fix it or pass --no-check")

    sha = commit()
    text = COMMENT.sub("", MARK.sub("", source.read_text()))

    base = None if args.no_links else permalink_base()
    if base:
        text = link_pointers(text, base, sha)
        if sha.endswith("-dirty"):
            sys.stderr.write("warning: tree is dirty, so the permalinks resolve to nothing - commit before publishing\n")

    stamp = f"\nFigures as of `{sha}`, registry `docs/report/figures.yaml`, source `docs/report/{args.source}`.\n"
    text = text.rstrip() + "\n\n---\n" + stamp

    target = Path(args.out) if args.out else REPORT_DIR / "rendered" / args.source
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    print(target)


if __name__ == "__main__":
    main()
