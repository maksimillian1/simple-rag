#!/usr/bin/env python3
"""download-pdf-books-dataset.py — pull the zabiullah/pdf-books-collection
HuggingFace dataset onto this machine as individual PDF files.

The dataset ships as Parquet (21 splits, ~13 GB, one row per book with the
PDF bytes in a `pdf` binary column), not as raw files — a plain file
download would just give you parquet shards, not PDFs. This script:

  1. downloads every parquet shard in parallel via the public HF
     datasets-server API (no huggingface_hub / datasets dependency, no HF
     token required for a public dataset), with resume support so a
     re-run skips shards already on disk
  2. extracts the `pdf` column of every row to its own .pdf file, in
     parallel across shards (CPU-bound: parquet decompression)
  3. writes manifest.csv next to the PDFs with title/author/subject/
     language, for traceability back to the source row

    ./download-pdf-books-dataset.py
    ./download-pdf-books-dataset.py --out-dir tmp/ingest --extract-workers 8

Requires: requests, pyarrow, tqdm.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("requests is required: pip install requests")

try:
    import pyarrow.parquet as pq
except ImportError:
    sys.exit("pyarrow is required: pip install pyarrow")

try:
    from tqdm import tqdm
except ImportError:
    sys.exit("tqdm is required: pip install tqdm")

PARQUET_API = "https://datasets-server.huggingface.co/parquet"
DEFAULT_REPO = "zabiullah/pdf-books-collection"
COLUMNS = ["file_name", "title", "author", "subject", "language", "pdf"]

REPO_ROOT = Path(__file__).resolve().parents[3]


# --------------------------------------------------------------------------- list

def list_parquet_files(repo_id: str) -> list[dict]:
    resp = requests.get(PARQUET_API, params={"dataset": repo_id}, timeout=30)
    resp.raise_for_status()
    files = resp.json()["parquet_files"]
    if not files:
        sys.exit(f"no parquet files reported for {repo_id} — check the dataset id")
    return files


# --------------------------------------------------------------------------- download

def download_one(entry: dict, cache_dir: Path) -> Path:
    dest = cache_dir / entry["split"] / entry["filename"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size == entry["size"]:
        return dest  # already downloaded, resume-friendly re-run

    tmp_path = dest.with_suffix(dest.suffix + ".part")
    with requests.get(entry["url"], stream=True, timeout=60) as resp:
        resp.raise_for_status()
        with tmp_path.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
                fh.write(chunk)
    tmp_path.rename(dest)
    return dest


def download_all(files: list[dict], cache_dir: Path, workers: int) -> list[Path]:
    total_bytes = sum(f["size"] for f in files)
    paths: list[Path] = []
    with tqdm(total=total_bytes, unit="B", unit_scale=True, desc="download") as bar, \
         ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(download_one, f, cache_dir): f for f in files}
        for future in as_completed(futures):
            entry = futures[future]
            try:
                paths.append(future.result())
            except Exception as e:  # noqa: BLE001
                sys.exit(f"download failed for {entry['url']}: {e}")
            bar.update(entry["size"])
    return paths


# --------------------------------------------------------------------------- extract

def safe_filename(name: str, fallback: str) -> str:
    name = Path(name or fallback).name.strip() or fallback
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name)
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    if len(name) > 200:
        name = name[:196] + ".pdf"
    return name


def extract_shard(args: tuple[Path, Path, bool]) -> list[dict]:
    shard_path, out_dir, overwrite = args
    rows: list[dict] = []
    seen: dict[str, int] = {}
    parquet_file = pq.ParquetFile(shard_path)
    row_index = 0
    for batch in parquet_file.iter_batches(columns=COLUMNS, batch_size=8):
        cols = {name: batch.column(i) for i, name in enumerate(COLUMNS)}
        for i in range(batch.num_rows):
            pdf_bytes = cols["pdf"][i].as_py()
            name = safe_filename(cols["file_name"][i].as_py(),
                                  f"{shard_path.stem}-{row_index}")
            count = seen.get(name, 0)
            seen[name] = count + 1
            if count:
                stem = name[:-4]
                name = f"{stem}_{count}.pdf"

            out_path = out_dir / name
            if pdf_bytes and (overwrite or not out_path.exists()):
                out_path.write_bytes(pdf_bytes)

            rows.append({
                "file_name": name,
                "title": cols["title"][i].as_py(),
                "author": cols["author"][i].as_py(),
                "subject": cols["subject"][i].as_py(),
                "language": cols["language"][i].as_py(),
                "source_shard": shard_path.name,
                "bytes": len(pdf_bytes) if pdf_bytes else 0,
            })
            row_index += 1
    return rows


def extract_all(shard_paths: list[Path], out_dir: Path, workers: int,
                 overwrite: bool) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    jobs = [(p, out_dir, overwrite) for p in shard_paths]
    with tqdm(total=len(jobs), desc="extract") as bar, \
         ProcessPoolExecutor(max_workers=workers) as pool:
        for rows in pool.map(extract_shard, jobs):
            manifest.extend(rows)
            bar.update(1)
    return manifest


def write_manifest(manifest: list[dict], out_dir: Path) -> Path:
    path = out_dir / "manifest.csv"
    fields = ["file_name", "title", "author", "subject", "language",
              "source_shard", "bytes"]
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(manifest)
    return path


# --------------------------------------------------------------------------- main

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo-id", default=DEFAULT_REPO)
    p.add_argument("--out-dir", default=str(REPO_ROOT / "tmp" / "ingest"),
                   help="where extracted .pdf files and manifest.csv land")
    p.add_argument("--cache-dir", default=None,
                   help="where raw parquet shards are cached "
                        "(default: <out-dir>/.parquet-cache)")
    p.add_argument("--download-workers", type=int, default=8)
    p.add_argument("--extract-workers", type=int, default=None,
                   help="default: os.cpu_count()")
    p.add_argument("--overwrite", action="store_true",
                   help="re-extract PDFs that already exist in --out-dir")
    p.add_argument("--keep-cache", action="store_true", default=True,
                   help="keep downloaded parquet shards for a cheap re-run "
                        "(default: on)")
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    cache_dir = Path(args.cache_dir) if args.cache_dir else out_dir / ".parquet-cache"

    print(f"-> listing parquet shards for {args.repo_id}")
    files = list_parquet_files(args.repo_id)
    total_gb = sum(f["size"] for f in files) / 1e9
    print(f"-> {len(files)} shards, {total_gb:.2f} GB total")

    shard_paths = download_all(files, cache_dir, args.download_workers)

    print(f"-> extracting PDFs to {out_dir}")
    manifest = extract_all(shard_paths, out_dir, args.extract_workers, args.overwrite)
    manifest_path = write_manifest(manifest, out_dir)

    written = sum(1 for r in manifest if r["bytes"])
    total_pdf_gb = sum(r["bytes"] for r in manifest) / 1e9
    print(f"-> {written}/{len(manifest)} PDFs written, {total_pdf_gb:.2f} GB, "
          f"manifest at {manifest_path}")
    if not args.keep_cache:
        import shutil
        shutil.rmtree(cache_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
