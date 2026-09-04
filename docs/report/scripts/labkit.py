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
import tempfile
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

# InstanceTerminating fires on every node teardown Karpenter itself decides
# on — WhenEmpty/WhenEmptyOrUnderutilized consolidation included, which only
# ever disrupts a node already at pod-count 0 — so on its own it says nothing
# about whether work was actually disrupted. Confirmed empirically
# (01-ingestion/ingestion-n50-test, 2026-09-01): two InstanceTerminating
# nodes had zero chunker/indexer containers ever scheduled to them (M4). The
# other three reasons below are the account/EC2 side losing the instance
# involuntarily — that's what actually invalidates a window (K1).
FORCED_REASONS = [
    "SpotInterrupted",
    "TerminatingOnInterruption",
    "InstanceStopping",
]
INTERRUPT_REASONS = FORCED_REASONS + ["InstanceTerminating"]


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

    def namespace_for(self, workload: str) -> str:
        """Per-workload override, e.g. namespaces.tei-embeddings. Falls back to
        the generic `namespace` key — correct only when every FREEZE/GATE
        workload for this execution actually lives in one namespace."""
        return str(self.get(f"namespaces.{workload}", None) or self.namespace)

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


SUBST_TOKEN = re.compile(r"\{(\w+)\}")


def _substitute(text: str, subs: dict, path: Path, ref: str) -> str:
    """Fill {name} placeholders, e.g. {rate}. Uses a narrow token pattern rather
    than str.format(): a PromQL label matcher like {namespace="x",reason="y"}
    is also wrapped in braces, and str.format() would try to parse it as a
    substitution and fail on the first one that isn't a bare identifier."""
    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key not in subs:
            die(f"{path}: guard {ref} references unknown substitution '{key}'")
        return str(subs[key])
    return SUBST_TOKEN.sub(repl, text)


def load_guards(path: Path, substitutions: dict | None = None) -> list[dict]:
    """ref|bound|promql. Bound is one or both of 'min <v>' and 'max <v>'.
    Substitutions fill {name} placeholders in bounds and queries — the only
    place a per-point value is allowed into a frozen file."""
    subs = substitutions or {}
    guards = []
    for ref, bound, query in read_ref_file(path, 3):
        bound = _substitute(bound, subs, path, ref)
        query = _substitute(query, subs, path, ref)
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


def pods_by_node(namespace: str, label_selector: str) -> dict[str, list[str]]:
    """node -> running pod names. Whether a node that just vanished actually
    had anything on it — the real signal for whether its loss disrupted
    work — rather than whether the system had backlog somewhere else at the
    time (queue depth alone conflates the two, see FORCED_REASONS)."""
    data = sh_json(["kubectl", "-n", namespace, "get", "pods", "-l", label_selector,
                    "--field-selector=status.phase=Running", "-o", "json"])
    out: dict[str, list[str]] = {}
    for item in data.get("items", []):
        node = item.get("spec", {}).get("nodeName")
        if not node:
            continue
        out.setdefault(node, []).append(item["metadata"]["name"])
    return out


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
    """Best effort. Event TTL is short, so absence here proves nothing.

    Returns every matching event, InstanceTerminating included — the caller
    decides what counts against validity. Use `entry.split(' · ')[0] in
    FORCED_REASONS` to tell an involuntary loss from ordinary consolidation."""
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
    """Opens what the runner asks for. Torn down on exit, including on a raise.

    `kubectl port-forward` has no reconnect logic of its own and is known to
    drop silently on a long-lived tunnel (idle timeout to the API server, a
    network blip, the target pod rescheduling) — a real risk over a run that
    can watch for the better part of an hour. `ensure_alive()` is the fix:
    call it periodically (the watch loop) and right before anything that
    depends on the tunnel (the R21 read, the Prometheus export) so a dead
    forward gets relaunched before it causes a gap instead of after."""

    def __init__(self, targets: list[dict], enabled: bool = True):
        self.enabled = enabled
        self.targets = [t for t in targets if t]
        self.procs: list[subprocess.Popen] = []
        self.logs: list[Path] = []

    def _launch(self, spec: dict) -> tuple[subprocess.Popen, Path]:
        log_path = Path(tempfile.gettempdir()) / (
            f"port-forward-{spec['namespace']}-"
            f"{spec['target'].replace('/', '_')}.log")
        log_file = log_path.open("w")
        proc = subprocess.Popen(
            ["kubectl", "-n", spec["namespace"], "port-forward",
             spec["target"], spec["mapping"]],
            stdout=subprocess.DEVNULL, stderr=log_file,
            start_new_session=True,
        )
        log_file.close()  # child inherited the fd; this process doesn't need it open
        return proc, log_path

    def __enter__(self):
        if not self.enabled or not self.targets:
            return self
        for spec in self.targets:
            print(f"{ARROW} port-forward : {spec['namespace']}/{spec['target']} "
                  f"{spec['mapping']}")
            proc, log_path = self._launch(spec)
            self.procs.append(proc)
            self.logs.append(log_path)
        time.sleep(4)
        for proc, spec in zip(self.procs, self.targets):
            if proc.poll() is not None:
                die(f"a port-forward died immediately ({spec['namespace']}/"
                    f"{spec['target']}) — check the service names in env.yaml, "
                    f"its log, or pass --no-port-forward and open them yourself")
        return self

    def ensure_alive(self) -> list[str]:
        """Relaunch any forward that died. Returns one message per restart,
        empty when everything is still up — call and print the result rather
        than assuming silence means nothing happened."""
        if not self.enabled:
            return []
        notices = []
        for i, proc in enumerate(self.procs):
            if proc.poll() is None:
                continue
            spec = self.targets[i]
            tail = ""
            try:
                tail = self.logs[i].read_text().strip().splitlines()[-1:]
                tail = f" — {tail[0]}" if tail else ""
            except OSError:
                pass
            notices.append(
                f"port-forward {spec['namespace']}/{spec['target']} died "
                f"(exit {proc.returncode}){tail} — relaunching")
            new_proc, new_log = self._launch(spec)
            time.sleep(2)
            if new_proc.poll() is not None:
                notices.append(
                    f"port-forward {spec['namespace']}/{spec['target']} "
                    f"failed to relaunch — see {new_log}")
            self.procs[i] = new_proc
            self.logs[i] = new_log
        return notices

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


def frozen_images(env: "Env", refs: list[str]) -> dict[str, list[str]]:
    """refs are 'kind/name'. The sweep compares one artifact across the grid, and
    this is what proves it did. Namespace is resolved per name — the FREEZE
    list is not guaranteed to sit in one namespace (chunker/indexer in
    rag-jobs, tei-embeddings in rag-platform, api in rag-api)."""
    out: dict[str, list[str]] = {}
    for ref in refs:
        if "/" not in ref:
            die(f"freeze entry must be kind/name, got {ref!r}")
        kind, name = ref.split("/", 1)
        path = CONTAINER_PATHS.get(kind.lower())
        if path is None:
            die(f"cannot read containers from kind {kind!r} — a ScaledObject "
                f"scales an existing workload, so freeze that workload instead")
        namespace = env.namespace_for(name)
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
                  t_end: datetime, out_dir: Path) -> None:
    """out_dir is required, not defaulted: run_export() passes it via the
    OUT_DIR env var rather than a flag, so a hint without --out-dir looks
    identical but silently lands in export-metrics.py's own default
    (docs/report/data) instead of next to this run's other files."""
    print(f"         {SCRIPTS_DIR / 'export-metrics.py'} --run {run_id} "
          f"--queries {series_file} --start {rfc3339(t_start)} "
          f"--end {rfc3339(t_end)} --out-dir {out_dir} --force")


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
