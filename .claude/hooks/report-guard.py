#!/usr/bin/env python3
"""report-guard.py — keep the report's number contract in front of whoever edits it.

PreToolUse  · states the contract before an edit under docs/report/ lands.
PostToolUse · runs the checker and reports drift the moment it appears.

**Neither blocks.** A hook that refused an edit would refuse every intermediate
state: registering a figure and marking it are two steps, and the middle one
does not resolve. Informing is what a hook is good at. The hard gate belongs in
CI, where it cannot be skipped with `--no-verify`.

Any failure inside this script exits 0. A broken guard must never be able to
stop work on the report, so every path out of here is non-blocking.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCOPE = "docs/report"
REGISTRY = Path("docs/report/figures.yaml")
TIMEOUT = 60

CONTRACT = """This file is under the report's number contract (docs/report/formats.md).

- Every figure printed here resolves from docs/report/figures.yaml. Never compute
  a number in prose: one worked out while writing is one nothing can check.
- A mark is the ref glued to the digits, before any closing markup:
  **553.83<!--FD26-->**. Units and the trust marker stay outside the pair.
- Add figures at the end of the registry. Deleting one renumbers every later ref
  of that kind, and the marks already written keep naming the old numbers.
- Run `report-kit figures check` from `docs/report/` before treating the edit as
  done. It comes from report-kit, pinned in `docs/report/requirements.txt`.

The full rules are in docs/report/formats.md; read it when a case is not obvious."""


def emit(event_name: str, context: str) -> None:
    json.dump({"hookSpecificOutput": {"hookEventName": event_name,
                                      "additionalContext": context}}, sys.stdout)
    sys.stdout.write("\n")


def project_dir(event: dict) -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".")


def in_scope(path: str) -> bool:
    return bool(path) and SCOPE in Path(path).as_posix()


def run_checker(root: Path) -> tuple[int, str]:
    """Run the pinned checker over the registry.

    Two details this depends on. `-m` rather than the `report-kit` console
    script: a hook does not inherit an interactive shell's PATH, and a checker
    that cannot be found would look exactly like a report with no problems.
    `--path` rather than the working directory: the command finds a registry by
    walking *up*, and the hook runs from the repository root, where the registry
    sits two levels down — it would find nothing and exit 2 on every edit.
    """
    registry = root / REGISTRY
    if not registry.is_file():
        return 0, ""
    done = subprocess.run(
        [sys.executable, "-m", "report_kit.cli",
         "figures", "--path", str(registry), "check"],
        capture_output=True, text=True, timeout=TIMEOUT)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def main() -> int:
    event = json.load(sys.stdin)
    if not in_scope((event.get("tool_input") or {}).get("file_path", "")):
        return 0

    name = event.get("hook_event_name", "")
    if name == "PreToolUse":
        emit(name, CONTRACT)
        return 0

    if name == "PostToolUse":
        code, output = run_checker(project_dir(event))
        if code == 0:
            return 0
        emit(name, "The report's number check is failing after this edit. "
                   "Fix it now rather than at the end — a stale figure is "
                   "invisible in a correct-looking table.\n\n" + output.strip())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
