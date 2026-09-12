#!/usr/bin/env python
"""Gate pyright on a committed baseline instead of on zero errors.

The codebase has a backlog of type errors, so demanding zero would mean
never turning pyright on. This records how many errors exist today and
fails only when that number grows — new code has to be clean, and the
backlog can be paid down without blocking anything.

Usage::

    python scripts/check_pyright_baseline.py            # compare (CI)
    python scripts/check_pyright_baseline.py --update   # re-record

When the count drops, the baseline is tightened automatically so the
ratchet only ever moves one way.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = ROOT / "pyright_baseline.json"


def run_pyright() -> int:
    """Return pyright's error count, or exit non-zero if it cannot run."""
    proc = subprocess.run(
        [sys.executable, "-m", "pyright", "--outputjson"],
        cwd=ROOT, capture_output=True, text=True,
    )
    # pyright exits non-zero when it reports errors, which is expected here.
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print("Could not parse pyright output:", file=sys.stderr)
        print(proc.stdout[-2000:] or proc.stderr[-2000:], file=sys.stderr)
        raise SystemExit(2)
    return int(report.get("summary", {}).get("errorCount", 0))


def read_baseline() -> int | None:
    if not BASELINE.is_file():
        return None
    return int(json.loads(BASELINE.read_text())["errorCount"])


def write_baseline(count: int) -> None:
    BASELINE.write_text(
        json.dumps(
            {
                "errorCount": count,
                "_comment": (
                    "Pyright error backlog. CI fails if the count rises above "
                    "this. Regenerate with scripts/check_pyright_baseline.py "
                    "--update after fixing errors."
                ),
            },
            indent=2,
        )
        + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update", action="store_true", help="re-record the baseline",
    )
    args = parser.parse_args()

    count = run_pyright()

    if args.update or read_baseline() is None:
        write_baseline(count)
        print(f"Pyright baseline recorded: {count} errors")
        return 0

    baseline = read_baseline()
    assert baseline is not None

    if count > baseline:
        print(
            f"Pyright errors rose from {baseline} to {count}.\n"
            f"Fix the new errors, or run "
            f"`python scripts/check_pyright_baseline.py --update` if the "
            f"increase is deliberate.",
            file=sys.stderr,
        )
        return 1

    if count < baseline:
        # Deliberately does NOT rewrite the file here. In CI this runs against
        # an ephemeral checkout, so a "tightened" baseline would be discarded
        # and the message would be a lie told on every run. Tightening is a
        # local action that produces a commit.
        print(
            f"Pyright errors fell from {baseline} to {count}. "
            f"Tighten the baseline with "
            f"`python scripts/check_pyright_baseline.py --update` and commit it."
        )
        return 0

    print(f"Pyright errors unchanged at {count}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
