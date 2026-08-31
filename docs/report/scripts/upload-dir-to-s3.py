#!/usr/bin/env python3
"""upload-dir-to-s3.py — upload a directory of files to S3 as fast as
plain multipart + concurrency allows, with no extra AWS spend.

Speed comes from two free mechanisms: multipart splits each file into
parts uploaded over several TCP connections, and a thread pool uploads
several files at once. S3 Transfer Acceleration is deliberately not used
here — it is faster over a slow/distant link but bills an extra
$0.04-$0.08 per GB on top of normal PUT and storage costs, which plain
multipart concurrency does not.

Each S3 event on the raw-docs bucket fires the ingestion pipeline
(01-ingestion), so re-running this against a bucket that already has
objects is safe by default: existing keys are skipped via a HEAD check
rather than re-uploaded and re-queued.

    ./upload-dir-to-s3.py --bucket my-bucket
    ./upload-dir-to-s3.py --bucket my-bucket --prefix batch-1/ --dry-run

With no --bucket, it resolves the bucket from `terraform output
rag_s3_bucket` (run from the repo's terraform/ directory).

Requires: boto3, tqdm.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import boto3
    from boto3.s3.transfer import TransferConfig
    from botocore.exceptions import ClientError
except ImportError:
    sys.exit("boto3 is required: pip install boto3")

try:
    from tqdm import tqdm
except ImportError:
    sys.exit("tqdm is required: pip install tqdm")

REPO_ROOT = Path(__file__).resolve().parents[3]


def resolve_bucket() -> str:
    try:
        out = subprocess.run(
            ["terraform", "output", "-raw", "rag_s3_bucket"],
            cwd=REPO_ROOT / "terraform", capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        sys.exit(f"--bucket not given and could not resolve it from terraform "
                  f"output: {e}")
    bucket = out.stdout.strip()
    if not bucket:
        sys.exit("terraform output rag_s3_bucket returned nothing")
    return bucket


def object_exists(s3, bucket: str, key: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
            return False
        raise


def upload_one(s3, bucket: str, path: Path, key: str, content_type: str,
               config: TransferConfig, bar: tqdm) -> None:
    def progress(bytes_sent: int) -> None:
        bar.update(bytes_sent)

    s3.upload_file(str(path), bucket, key, Config=config,
                    ExtraArgs={"ContentType": content_type}, Callback=progress)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", default=str(REPO_ROOT / "tmp" / "ingest"),
                   help="local source directory")
    p.add_argument("--bucket", default=None,
                   help="target bucket (default: resolved from terraform output)")
    p.add_argument("--prefix", default="", help="key prefix inside the bucket")
    p.add_argument("--pattern", default="*.pdf", help="glob for files to upload")
    p.add_argument("--content-type", default="application/pdf")
    p.add_argument("--workers", type=int, default=16,
                   help="files uploaded concurrently")
    p.add_argument("--part-size-mb", type=int, default=16,
                   help="multipart chunk size and threshold")
    p.add_argument("--part-concurrency", type=int, default=4,
                   help="threads per file for multipart parts")
    p.add_argument("--overwrite", action="store_true",
                   help="re-upload keys that already exist in the bucket")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    bucket = args.bucket or resolve_bucket()
    src_dir = Path(args.dir)
    files = sorted(src_dir.glob(args.pattern))
    if not files:
        sys.exit(f"no files matching {args.pattern} under {src_dir}")

    total_bytes = sum(f.stat().st_size for f in files)
    print(f"-> {len(files)} files, {total_bytes / 1e9:.2f} GB, "
          f"target s3://{bucket}/{args.prefix}")

    if args.dry_run:
        for f in files:
            print(f"  would upload {f.name} -> s3://{bucket}/{args.prefix}{f.name}")
        return 0

    s3 = boto3.client("s3")
    config = TransferConfig(
        multipart_threshold=args.part_size_mb * 1024 * 1024,
        multipart_chunksize=args.part_size_mb * 1024 * 1024,
        max_concurrency=args.part_concurrency,
        use_threads=True,
    )

    to_upload: list[tuple[Path, str]] = []
    skipped = 0
    for f in files:
        key = f"{args.prefix}{f.name}"
        if not args.overwrite and object_exists(s3, bucket, key):
            skipped += 1
            continue
        to_upload.append((f, key))

    if skipped:
        print(f"-> skipping {skipped} objects already in the bucket "
              f"(--overwrite to force)")

    upload_bytes = sum(f.stat().st_size for f, _ in to_upload)
    start = time.time()
    failed: list[str] = []

    with tqdm(total=upload_bytes, unit="B", unit_scale=True, desc="upload") as bar, \
         ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(upload_one, s3, bucket, path, key, args.content_type,
                        config, bar): key
            for path, key in to_upload
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                future.result()
            except Exception as e:  # noqa: BLE001
                failed.append(key)
                print(f"  FAILED {key}: {e}", file=sys.stderr)

    elapsed = max(time.time() - start, 1e-6)
    throughput = upload_bytes / elapsed / 1e6
    print(f"-> uploaded {len(to_upload) - len(failed)}/{len(to_upload)} objects, "
          f"{upload_bytes / 1e9:.2f} GB in {elapsed:.0f}s ({throughput:.1f} MB/s)")
    if failed:
        print(f"-> {len(failed)} failed — re-run to retry (existing keys are "
              f"skipped, so this is safe)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
