#!/usr/bin/env python3
"""prepare-cluster-for-ingestion.py — force the ingestion pool, and the
Qdrant collection it writes to, back to what 01-ingestion/run-ingestion-point.py's
preflight requires (both SQS queues empty, apps-compute at zero nodes,
tei-embeddings back at its floor, collection empty), instead of waiting on
organic drain between points.

Order is fixed, not configurable, and matters:

    1. clean S3    — remove leftover objects under the sample's prefix, so
                      nothing already-landed can fire a stray event later.
    2. purge SQS   — stops KEDA from creating new chunker/indexer Jobs for
                      whatever is still queued, before step 3 kills the ones
                      already running. Reversed, a killed pod's in-flight
                      message would just spawn a replacement immediately.
    3. kill pods   — delete the chunker/indexer Jobs (and their pods) outright
                      rather than waiting for them to finish on their own.
                      Deleting the Job, not just the pod, stops the ScaledJob
                      controller from recreating it.
    4. reset Qdrant — delete the collection if it holds any points. Not
                      recreated here: apps/indexer/src/haystack_pipeline.py
                      builds it with `QdrantDocumentStore(..., replication_factor=2,
                      quantization_config=...)` on its own next write, and that
                      is the one place the real schema is defined — approximating
                      it a second time in ops tooling is a schema to keep in
                      sync for no benefit. Safe only once nothing is still
                      writing, which step 3 (plus the wait below, when not
                      --no-wait) already guarantees.

Steps 1-4 return fast. What is usually slow is what happens next, on its own,
which this script only watches rather than forces: Karpenter's own
consolidation removes now-empty apps-compute nodes (`consolidateAfter: 5m`),
and tei-embeddings scales back down to its floor once KEDA's scaleDown
stabilization window closes (also 5m). The default --wait-timeout accounts
for both running back to back, not for either one specifically.

    ./prepare-cluster-for-ingestion.py                  # clean, kill, reset, wait for drain
    ./prepare-cluster-for-ingestion.py --no-wait         # fire and return
    ./prepare-cluster-for-ingestion.py --s3-prefix foo/  # a different corpus prefix

Called automatically by run-ingestion-point.py at the end of a point, once its
data is exported — readying the cluster for the next point, not this one —
unless --no-prepare is given there. Also meant to be run by hand, independently
of any point, e.g. before the first one.

Requires: kubectl, aws.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labkit as lk                                            # noqa: E402

# See the matching comment in run-ingestion-point.py: without this, stdout is
# fully block-buffered whenever it isn't a TTY, and progress here (e.g. the
# wait_for_floor poll loop) sits unseen until exit — indistinguishable from a
# hang, both run standalone and when launched as a subprocess.
sys.stdout.reconfigure(line_buffering=True)

DEFAULT_S3_PREFIX = "ingestion-sample/"
QUEUES = ("stage-1", "stage-2")
WORKLOADS = ("chunker", "indexer")
SHARED_TIER = "tei-embeddings"
SHARED_TIER_FLOOR = 2

# Karpenter's apps-compute consolidateAfter (5m) plus tei-embeddings' KEDA
# scaleDown stabilizationWindowSeconds (5m), plus slack for node termination
# and the poll cadence itself — the two don't run concurrently from a cold
# start, since TEI only starts cooling once indexer load actually stops.
DEFAULT_WAIT_TIMEOUT = 900

REPO_ROOT = lk.REPORT_ROOT.parents[1]


def resolve_bucket() -> str:
    """Same resolution upload-dir-to-s3.py uses, kept independent rather than
    imported: a one-function duplication is cheaper than a cross-script
    import for something this small."""
    try:
        out = subprocess.run(
            ["terraform", "output", "-raw", "rag_s3_bucket"],
            cwd=REPO_ROOT / "terraform", capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        lk.die(f"--bucket not given and could not resolve it from terraform output: {e}")
    bucket = out.stdout.strip()
    if not bucket:
        lk.die("terraform output rag_s3_bucket returned nothing")
    return bucket


def clean_s3(bucket: str, prefix: str) -> None:
    print(f"{lk.ARROW} cleaning s3://{bucket}/{prefix}")
    try:
        out = lk.sh(["aws", "s3", "rm", f"s3://{bucket}/{prefix}", "--recursive"],
                    timeout=180)
    except RuntimeError as e:
        print(f"{lk.WARN} s3 cleanup failed: {e}")
        return
    removed = len([l for l in out.splitlines() if l.strip()])
    print(f"[{lk.OK}] removed {removed} object(s)" if removed
          else f"[{lk.OK}] nothing to remove")


def purge_queues(env: lk.Env) -> None:
    """Purge is asynchronous on AWS's side — up to 60s before depth actually
    reads zero, and AWS refuses a second purge on the same queue within that
    window. Both are handled by wait_for_floor polling rather than here."""
    for label in QUEUES:
        url = env.need(f"sqs.{label}")
        print(f"{lk.ARROW} purging SQS {label}")
        try:
            lk.sh(["aws", "sqs", "purge-queue", "--queue-url", url], timeout=30)
            print(f"[{lk.OK}] purge requested for {label}")
        except RuntimeError as e:
            if "PurgeQueueInProgress" in str(e):
                print(f"{lk.WARN} {label} already purging (60s cooldown) — leaving it")
            else:
                print(f"{lk.WARN} purge failed for {label}: {e}")


def reset_qdrant(env: lk.Env) -> bool:
    """Delete-only. The app recreates the collection with the real schema on
    its own next write (see module docstring) — this just clears it."""
    url, collection = env.need("qdrant.url"), env.need("qdrant.collection")
    print(f"{lk.ARROW} checking qdrant collection {collection!r}")
    try:
        body = lk.http_json(
            "POST", f"{url}/collections/{collection}/points/count", {"exact": True})
        count = int(body.get("result", {}).get("count", 0) or 0)
    except RuntimeError as e:
        if "HTTP 404" in str(e):
            # No collection at all is the same end state as an empty one —
            # the indexer creates it fresh on its next write either way.
            print(f"[{lk.OK}] already empty (no collection)")
            return True
        print(f"{lk.WARN} qdrant unreachable, leaving it: {e}")
        return False

    if count == 0:
        print(f"[{lk.OK}] already empty")
        return True

    print(f"{lk.ARROW} deleting collection ({count} points) — the indexer "
          f"recreates it with the right schema on its next write")
    try:
        lk.http_json("DELETE", f"{url}/collections/{collection}")
    except RuntimeError as e:
        print(f"{lk.WARN} delete failed: {e}")
        return False
    print(f"[{lk.OK}] collection deleted")
    return True


def kill_pods(env: lk.Env) -> None:
    for workload in WORKLOADS:
        ns = env.namespace_for(workload)
        print(f"{lk.ARROW} killing {workload} jobs in {ns}")
        try:
            out = lk.sh(["kubectl", "-n", ns, "delete", "jobs",
                         "-l", f"app={workload}", "--wait=false",
                         "--ignore-not-found=true"], timeout=60)
            print(f"[{lk.OK}] {out.strip() or 'nothing to delete'}")
        except RuntimeError as e:
            print(f"{lk.WARN} kill failed for {workload}: {e}")


def wait_for_floor(env: lk.Env, timeout: int) -> bool:
    poll = env.poll_seconds
    selector = env.need("nodepool_ingestion")
    deadline = time.time() + timeout
    print(f"{lk.ARROW} watching for pool at zero and {SHARED_TIER} at floor "
          f"{SHARED_TIER_FLOOR} (timeout {lk.hms(timeout)})")
    while time.time() < deadline:
        try:
            nodes = lk.nodes_by_selector(selector)
            replicas = lk.deployment_replicas(env.namespace_for(SHARED_TIER), SHARED_TIER)
            depths = {label: lk.sqs_depth(env.need(f"sqs.{label}")) for label in QUEUES}
        except RuntimeError as e:
            print(f"{lk.WARN} poll failed ({e}) — retrying")
            time.sleep(poll)
            continue

        depth_str = " ".join(f"{k}={v}" for k, v in sorted(depths.items()))
        print(f"    nodes={len(nodes):<3} {SHARED_TIER}={replicas:<3} {depth_str}")

        if not nodes and replicas <= SHARED_TIER_FLOOR and sum(depths.values()) == 0:
            print(f"[{lk.OK}] cluster at floor")
            return True
        time.sleep(poll)

    print(f"{lk.BAD} timed out waiting for floor — check Karpenter and the "
          f"tei-embeddings HPA by hand")
    return False


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--env", default=str(lk.default_env_path()))
    p.add_argument("--bucket", default=None,
                   help="default: resolved from terraform output, as upload-dir-to-s3.py does")
    p.add_argument("--s3-prefix", default=DEFAULT_S3_PREFIX)
    p.add_argument("--no-wait", action="store_true",
                   help="fire and return — don't watch for drain")
    p.add_argument("--wait-timeout", type=int, default=DEFAULT_WAIT_TIMEOUT)
    p.add_argument("--no-port-forward", action="store_true",
                   help="assume something else already forwards Qdrant locally")
    args = p.parse_args()

    env = lk.Env(Path(args.env))
    bucket = args.bucket or resolve_bucket()

    with lk.PortForwards([lk.forward_spec(env, "qdrant")],
                          enabled=not args.no_port_forward):
        print(f"{lk.ARROW} preparing cluster for 01-ingestion")
        clean_s3(bucket, args.s3_prefix)
        purge_queues(env)
        kill_pods(env)
        qdrant_ok = reset_qdrant(env)

    if args.no_wait:
        print(f"{lk.ARROW} --no-wait — not watching drain")
        return lk.EXIT_CLEAN if qdrant_ok else lk.EXIT_TIMEOUT

    floor_ok = wait_for_floor(env, args.wait_timeout)
    return lk.EXIT_CLEAN if (qdrant_ok and floor_ok) else lk.EXIT_TIMEOUT


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        sys.exit(130)
