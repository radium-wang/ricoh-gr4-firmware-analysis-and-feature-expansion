#!/usr/bin/env python3
"""Analyze copied readback from the one-boot Linux reply probe, read-only."""

import argparse
import json
from pathlib import Path


def section(lines, label):
    try:
        at = lines.index(label)
    except ValueError:
        return None
    return lines[at + 1] if at + 1 < len(lines) else None


def analyze(directory):
    log = directory / "LRTEST.TXT"
    lines = log.read_text(errors="replace").splitlines() if log.exists() else []
    snapshots = {}
    for name in ("LRPRE.BIN", "LRPOST.BIN"):
        path = directory / name
        data = path.read_bytes() if path.exists() else b""
        snapshots[name] = {"size": len(data), "response_flag": data[116] if len(data) == 117 else None}
    before = snapshots["LRPRE.BIN"]["response_flag"]
    after = snapshots["LRPOST.BIN"]["response_flag"]
    marker = section(lines, "computed marker reply")
    uname = section(lines, "uname reply")
    return {
        "log_present": log.exists(),
        "finished": "Linux reply probe finished" in lines,
        "linux_readiness": section(lines, "Linux readiness"),
        "response_flag_read_available": section(lines, "response flag read available"),
        "snapshots": snapshots,
        "response_flag_restored": before is not None and before == after,
        "computed_marker_reply": marker,
        "uname_reply": uname,
        "linux_execution_proven": marker is not None and "GR4_LINUX_READY" in marker,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("readback", type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.readback), indent=2))


if __name__ == "__main__":
    main()
