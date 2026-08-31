#!/usr/bin/env python3
"""labkit.py — shared plumbing for report-kit run scripts.

Not executable. Imported by run-ingestion-point.py and run-inference-point.py.

Holds what is identical whatever is under test: env access, time formatting,
shell and HTTP wrappers, port-forwards, the ref-file parser, guard evaluation,
the image freeze, git facts, the export handoff, and the point block writer.

Does not hold preflight predicates, the watch loop, the close condition or the
reset. Those decide what is measured and live as Python in the runner.

Three inputs, three lifetimes:
    env.yaml     addresses          per cluster, not frozen
    series.txt   ref|promql         frozen with the Plan, exported to data/
    guards.txt   ref|bound|promql   frozen with the Plan, checked at close
Constants that say what must not move live in the runner itself.

Requires: PyYAML, for env.yaml only. A hand-rolled parser mis-reads nesting
silently, and this file decides which cluster gets touched.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

OK, BAD, WARN, ARROW = "  ok  ", " FAIL ", " warn ", "->"

# Identical across runners, so the Journal describes one contract.
EXIT_CLEAN = 0
EXIT_PREFLIGHT = 1
EXIT_EXPORT_GAP = 2
EXIT_SUSPECT = 3
EXIT_TIMEOUT = 4

REPORT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent

INTERRUPT_REASONS = [
    "SpotInterrupted",
    "TerminatingOnInterruption",
    "InstanceTerminating",
    "InstanceStopping",
]


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(EXIT_PREFLIGHT)


# --------------------------------------------------------------------------- env

class Env:
    """Addresses only. A missing key fails loudly rather than defaulting to
    something that happens to be reachable."""

    def __init__(self, path: Path):
        if not path.is_file():
            die(f"env file not found: {path}")
        self.path = path
        self.raw = yaml.safe_load(path.read_text()) or {}

    def get(self, dotted: str, default=None):
        node = self.raw
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def need(self, dotted: str):
        value = self.get(dotted)
        if value in (None, "", [], {}) or (isinstance(value, str)
                                           and value.startswith("⟨")):
            die(f"{self.path}: unset or placeholder value: {dotted}")
        return value

    @property
    def namespace(self) -> str:
        return str(self.need("namespace"))

    @property
    def prom_url(self) -> str:
        return str(self.need("prometheus.url")).rstrip("/")

    @property
    def poll_seconds(self) -> int:
        return int(self.get("poll_seconds", 15))

    @property
    def max_wait_seconds(self) -> int:
        return int(self.get("max_wait_seconds", 90 * 60))


def default_env_path() -> Path:
    return SCRIPTS_DIR / "env.yaml"


def execution_dir(execution: str) -> Path:
    return REPORT_ROOT / "executions" / execution


# --------------------------------------------------------------------------- time

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_instant(text: str) -> datetime:
    try:
        return datetime.fromisoformat(
            text.strip().replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        die(f"bad timestamp: {text!r} (expected 2026-08-20T10:00:00Z)")


def hms(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600:d}h{(seconds % 3600) // 60:02d}m{seconds % 60:02d}s"


# --------------------------------------------------------------------------- shell

def sh(cmd: list[str], timeout: int = 60) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        die(f"command not found: {cmd[0]}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"timeout: {' '.join(cmd[:4])}...") from None
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[:300] or f"exit {proc.returncode}")
    return proc.stdout


def sh_json(cmd: list[str], timeout: int = 60) -> dict:
    out = sh(cmd, timeout=timeout)
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise RuntimeError(f"not JSON from {cmd[0]}") from None


def http_json(method: str, url: str, body: dict | None = None,
              timeout: int = 30) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"HTTP {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"cannot reach {url}: {e.reason}") from None
    return json.loads(raw) if raw.strip() else {}


# --------------------------------------------------------------------------- ref files

def read_ref_file(path: Path, fields: int) -> list[list[str]]:
    """Shared parser for series.txt and guards.txt. Pipe-separated, '#' comments
    and blanks ignored. Refs are unique within a file — which is why the same ref
    exported as a series and checked as a guard lives in two files."""
    if not path.is_file():
        die(f"file not found: {path}")
    rows: list[list[str]] = []
    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|", fields - 1)]
        if len(parts) != fields:
            die(f"{path}:{lineno} expected {fields} '|'-separated fields, "
                f"got {len(parts)}")
        if any(not p for p in parts):
            die(f"{path}:{lineno} empty field")
        rows.append(parts)
    if not rows:
        die(f"{path} holds no entries")
    refs = [row[0] for row in rows]
    dupes = {r for r in refs if refs.count(r) > 1}
    if dupes:
        die(f"{path}: duplicate refs: {', '.join(sorted(dupes))}")
    return rows


BOUND_TOKEN = re.compile(r"(min|max)\s+(\S+)")


def load_guards(path: Path, substitutions: dict | None = None) -> list[dict]:
    """ref|bound|promql. Bound is one or both of 'min <v>' and 'max <v>'.
    Substitutions fill {name} placeholders in bounds and queries — the only
    place a per-point value is allowed into a frozen file."""
    subs = substitutions or {}
    guards = []
    for ref, bound, query in read_ref_file(path, 3):
        try:
            bound = bound.format(**subs)
            query = query.format(**subs)
        except KeyError as e:
            die(f"{path}: guard {ref} references unknown substitution {e}")
        found = BOUND_TOKEN.findall(bound)
        if not found:
            die(f"{path}: guard {ref} has no bound — expected 'min <v>' or "
                f"'max <v>', got {bound!r}")
        entry: dict = {"ref": ref, "query": query}
        for kind, value in found:
            try:
                entry[kind] = float(value)
            except ValueError:
                die(f"{path}: guard {ref} bound {kind} is not a number: {value!r}")
        guards.append(entry)
    return guards


# --------------------------------------------------------------------------- prometheus

def prom_query(prom_url: str, query: str) -> list[dict]:
    url = f"{prom_url}/api/v1/query?" + urllib.parse.urlencode({"query": query})
    data = http_json("GET", url)
    if data.get("status") != "success":
        raise RuntimeError(data.get("error", "prometheus query failed"))
    return data.get("data", {}).get("result", [])


def prom_scalar(prom_url: str, query: str) -> float | None:
    """Max over the returned series. None when the query returns nothing, which
    is an instrumentation gap and never a zero."""
    values = []
    for series in prom_query(prom_url, query):
        raw = series.get("value", [None, None])[1]
        if raw is not None:
            try:
                values.append(float(raw))
            except ValueError:
                pass
    return max(values) if values else None


def prom_targets_down(prom_url: str) -> list[str]:
    return [
        f'{r["metric"].get("job", "?")}/{r["metric"].get("instance", "?")}'
        for r in prom_query(prom_url, "up == 0")
    ]


def check_guards(prom_url: str, guards: list[dict]) -> list[str]:
    """Evaluated once, at window close. A guard returning nothing fails: an empty
    result is a gap, not a pass. Use `or vector(0)` where a zero is honest."""
    failures = []
    for guard in guards:
        ref = guard["ref"]
        try:
            value = prom_scalar(prom_url, guard["query"])
        except RuntimeError as e:
            print(f"[{BAD}] guard {ref} — query failed: {e}")
            failures.append(ref)
            continue
        if value is None:
            print(f"[{BAD}] guard {ref} — NO DATA (a gap, not a zero)")
            failures.append(ref)
            continue
        low, high = guard.get("min"), guard.get("max")
        breached = ((low is not None and value < low)
                    or (high is not None and value > high))
        bound = " · ".join(f"{k} {v:g}" for k, v in (("min", low), ("max", high))
                           if v is not None)
        print(f"[{BAD if breached else OK}] guard {ref} = {value:g}  [{bound}]")
        if breached:
            failures.append(ref)
    return failures


# --------------------------------------------------------------------------- cluster

def nodes_by_selector(selector: str) -> dict[str, str]:
    """name -> instance type."""
    data = sh_json(["kubectl", "get", "nodes", "-l", selector, "-o", "json"])
    return {
        item["metadata"]["name"]:
            item.get("metadata", {}).get("labels", {}).get(
                "node.kubernetes.io/instance-type", "?")
        for item in data.get("items", [])
    }


def deployment_replicas(namespace: str, name: str) -> int:
    data = sh_json(["kubectl", "-n", namespace, "get", "deployment", name,
                    "-o", "json"])
    return int(data.get("status", {}).get("replicas", 0) or 0)


def sqs_depth(queue_url: str) -> int:
    """Visible plus in-flight. A queue with zero visible and thirty in-flight is
    not drained."""
    data = sh_json([
        "aws", "sqs", "get-queue-attributes", "--queue-url", queue_url,
        "--attribute-names",
        "ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible",
        "--output", "json",
    ])
    attrs = data.get("Attributes", {})
    return (int(attrs.get("ApproximateNumberOfMessages", 0))
            + int(attrs.get("ApproximateNumberOfMessagesNotVisible", 0)))


def interrupt_events(since: datetime) -> list[str]:
    """Best effort. Event TTL is short, so absence here proves nothing."""
    found = []
    try:
        data = sh_json(["kubectl", "get", "events", "-A", "-o", "json"], timeout=45)
    except RuntimeError:
        return found
    for item in data.get("items", []):
        if item.get("reason", "") not in INTERRUPT_REASONS:
            continue
        stamp = (item.get("lastTimestamp") or item.get("eventTime")
                 or item.get("firstTimestamp"))
        if stamp:
            try:
                if parse_instant(stamp) < since:
                    continue
            except SystemExit:
                pass
        obj = item.get("involvedObject", {}).get("name", "?")
        found.append(f"{item['reason']} · {obj} · {stamp}")
    return found


# --------------------------------------------------------------------------- port-forward

class PortForwards:
    """Opens what the runner asks for. Torn down on exit, including on a raise."""

    def __init__(self, targets: list[dict], enabled: bool = True):
        self.enabled = enabled
        self.targets = [t for t in targets if t]
        self.procs: list[subprocess.Popen] = []

    def __enter__(self):
        if not self.enabled or not self.targets:
            return self
        for spec in self.targets:
            print(f"{ARROW} port-forward : {spec['namespace']}/{spec['target']} "
                  f"{spec['mapping']}")
            proc = subprocess.Popen(
                ["kubectl", "-n", spec["namespace"], "port-forward",
                 spec["target"], spec["mapping"]],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self.procs.append(proc)
        time.sleep(4)
        for proc in self.procs:
            if proc.poll() is not None:
                die("a port-forward died immediately — check the service names in "
                    "env.yaml, or pass --no-port-forward and open them yourself")
        return self

    def __exit__(self, *_):
        for proc in self.procs:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:                                  # noqa: BLE001
                proc.terminate()
        return False


def forward_spec(env: Env, prefix: str) -> dict | None:
    """Build a port-forward entry from an env block, or None when it names no
    service — a URL already reachable needs no tunnel."""
    service = env.get(f"{prefix}.service")
    if not service:
        return None
    return {"namespace": env.get(f"{prefix}.namespace", env.namespace),
            "target": service,
            "mapping": env.get(f"{prefix}.mapping", "")}


# --------------------------------------------------------------------------- freeze

CONTAINER_PATHS = {
    "scaledjob": ("spec", "jobTargetRef", "template", "spec", "containers"),
    "deployment": ("spec", "template", "spec", "containers"),
    "statefulset": ("spec", "template", "spec", "containers"),
    "daemonset": ("spec", "template", "spec", "containers"),
}


def _dig(node: dict, path) -> list:
    for key in path:
        node = node.get(key, {}) if isinstance(node, dict) else {}
    return node if isinstance(node, list) else []


def frozen_images(namespace: str, refs: list[str]) -> dict[str, list[str]]:
    """refs are 'kind/name'. The sweep compares one artifact across the grid, and
    this is what proves it did."""
    out: dict[str, list[str]] = {}
    for ref in refs:
        if "/" not in ref:
            die(f"freeze entry must be kind/name, got {ref!r}")
        kind, name = ref.split("/", 1)
        path = CONTAINER_PATHS.get(kind.lower())
        if path is None:
            die(f"cannot read containers from kind {kind!r} — a ScaledObject "
                f"scales an existing workload, so freeze that workload instead")
        try:
            data = sh_json(["kubectl", "-n", namespace, "get", kind, name,
                            "-o", "json"])
        except RuntimeError as e:
            raise RuntimeError(f"{ref}: {e}") from None
        out[ref] = sorted(c.get("image", "?") for c in _dig(data, path))
    return out


def check_freeze(freeze_file: Path, current: dict) -> list[str]:
    if not freeze_file.is_file():
        print(f"{WARN} no freeze at {freeze_file} — run --set-freeze first")
        return ["image freeze not recorded"]
    recorded = json.loads(freeze_file.read_text())
    if recorded != current:
        print(f"[{BAD}] image freeze mismatch")
        print(f"         frozen : {json.dumps(recorded, sort_keys=True)}")
        print(f"         current: {json.dumps(current, sort_keys=True)}")
        return ["images differ from the recorded freeze — re-run --set-freeze only "
                "when starting a new sweep"]
    loose = [k for k, v in current.items()
             if any("@sha256:" not in image for image in v)]
    if loose:
        print(f"{WARN} not pinned by digest: {', '.join(loose)} — a tag can move "
              f"under a frozen name")
    print(f"[{OK}] image freeze matches")
    return []


def git_facts() -> dict:
    facts = {}
    try:
        facts["commit"] = sh(["git", "rev-parse", "HEAD"]).strip()
        facts["dirty"] = bool(sh(["git", "status", "--porcelain"]).strip())
        print(f"[{OK}] commit = {facts['commit'][:12]}"
              f"{'  (WORKING TREE DIRTY)' if facts['dirty'] else ''}")
    except RuntimeError:
        facts["commit"], facts["dirty"] = "unknown", False
        print(f"{WARN} not a git checkout — the commit goes unrecorded")
    return facts


# --------------------------------------------------------------------------- export

def run_export(series_file: Path, run_id: str, t_start: datetime,
               t_end: datetime, step: str, prom_url: str, out_dir: Path) -> int:
    """The series file is passed explicitly. Never defaulted inside the exporter:
    a file picked up next to it belongs to whichever execution wrote it last."""
    script = SCRIPTS_DIR / "export-metrics.py"
    if not script.is_file():
        die(f"exporter not found: {script}")
    if not series_file.is_file():
        die(f"series file not found: {series_file}")
    print()
    print(f"{ARROW} exporting series · {series_file}")
    cmd = [sys.executable, str(script),
           "--run", run_id,
           "--queries", str(series_file),
           "--start", rfc3339(t_start),
           "--end", rfc3339(t_end),
           "--step", step]
    proc = subprocess.run(cmd, env={**os.environ, "PROM_URL": prom_url,
                                    "OUT_DIR": str(out_dir)})
    return proc.returncode


def reexport_hint(series_file: Path, run_id: str, t_start: datetime,
                  t_end: datetime) -> None:
    print(f"         {SCRIPTS_DIR / 'export-metrics.py'} --run {run_id} "
          f"--queries {series_file} --start {rfc3339(t_start)} "
          f"--end {rfc3339(t_end)} --force")


# --------------------------------------------------------------------------- point block

def md_table(rows: list[tuple[str, str]]) -> list[str]:
    return ["| | |", "| :--- | :--- |"] + [f"| {a} | {b} |" for a, b in rows]


def write_point(out_dir: Path, run_id: str, markdown: str, record: dict) -> Path:
    """Two artifacts per point. The markdown is pasted into the Journal; the JSON
    is what the cost pass reads its windows from, days later."""
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{run_id}.point.md"
    md_path.write_text(markdown if markdown.endswith("\n") else markdown + "\n")
    (out_dir / f"{run_id}.point.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n")
    return md_path


def report_validity(interrupts: list[str], guard_failures: list[str]) -> int:
    if interrupts:
        print()
        print(f"{WARN} {len(interrupts)} interruption signal(s) — this point carries "
              f"warm-up belonging to no level.")
        print(f"         Re-run it, or mark it ᴱ and exclude it from the curve fit. "
              f"Do not average it in silently.")
    if guard_failures:
        print()
        print(f"{WARN} guards breached: {', '.join(guard_failures)}")
        print(f"         Apply the matching row of §1 Validity before the point "
              f"enters the matrix.")
    return EXIT_SUSPECT if (interrupts or guard_failures) else EXIT_CLEAN
