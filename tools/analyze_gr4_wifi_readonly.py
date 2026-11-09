#!/usr/bin/env python3
"""Compare a GR IV Wi-Fi readback with the pinned local firmware image."""

import argparse
import hashlib
import json
from pathlib import Path

from audit_xpan_paths import EXPECTED_SHA256
from gr4_firmware_parts import find_parts
from inspect_initfs_readonly import SquashFS


def analyze(readback_path, firmware_path):
    readback_bytes = readback_path.read_bytes()
    readback = json.loads(readback_bytes)
    firmware = firmware_path.read_bytes()
    if hashlib.sha256(firmware).hexdigest() != EXPECTED_SHA256:
        raise ValueError("unexpected firmware image")
    if readback.get("camera_ip") != "192.168.0.1":
        raise ValueError("unexpected camera IP in readback")
    by_path = {item["path"]: item for item in readback["requests"]}
    if set(by_path) != {"/v1/ping", "/v1/debug/revisions"}:
        raise ValueError("unexpected endpoint list")
    for item in by_path.values():
        if item.get("port") != 80 or item.get("status") != 200:
            raise ValueError("unexpected HTTP port or response")
        body = item["body_text"].encode("utf-8")
        if len(body) != item["body_length"] or hashlib.sha256(body).hexdigest() != item["body_sha256"]:
            raise ValueError("readback body length or hash mismatch")
    ping = json.loads(by_path["/v1/ping"]["body_text"])
    if ping.get("errCode") != 200 or ping.get("errMsg") != "OK":
        raise ValueError("camera ping did not report OK")

    live_revisions = {}
    for line in by_path["/v1/debug/revisions"]["body_text"].splitlines():
        fields = line.split()
        if len(fields) != 3 or fields[2] in live_revisions:
            raise ValueError("unexpected revision response format")
        live_revisions[fields[2]] = line
    fs = SquashFS(find_parts(firmware)["initfs"].data)
    revision_dir = fs.resolve("/etc/revisions")
    local_revisions = {
        name: fs.read_file(fs.resolve("/etc/revisions/" + name)).decode("utf-8").strip()
        for name in fs.list_dir(revision_dir)
    }
    matches = {name: live_revisions.get(name) == value for name, value in local_revisions.items()}
    return {
        "readback_sha256": hashlib.sha256(readback_bytes).hexdigest(),
        "firmware_sha256": EXPECTED_SHA256,
        "camera_ping_ok": True,
        "camera_reported_datetime": ping.get("datetime"),
        "webapi_port": 80,
        "revision_count": len(live_revisions),
        "all_local_revisions_match": set(live_revisions) == set(local_revisions) and all(matches.values()),
        "revision_matches": matches,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("readback", type=Path)
    parser.add_argument("firmware", type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.readback, args.firmware), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
