#!/usr/bin/env python3
"""Read-only GR IV Wi-Fi Web API probe for the camera's own hotspot.

Only GET /v1/ping and GET /v1/debug/revisions are sent. The fixed
192.168.0.1 address comes from this firmware's WLAN startup code. No
firmware upload, property change, shell command or SD access is possible.
"""

import hashlib
import http.client
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


CAMERA_IP = "192.168.0.1"
PORTS = (80, 8000, 8080, 8888)
PATHS = ("/v1/ping", "/v1/debug/revisions")
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "devkit-output" / "usb-factory-20261001"


def wifi_ipv4():
    result = subprocess.run(("ifconfig", "en0"), check=True, capture_output=True, text=True)
    addresses = re.findall(r"\binet (\d+\.\d+\.\d+\.\d+)\b", result.stdout)
    matches = [address for address in addresses if re.fullmatch(r"192\.168\.0\.(?:[2-9]|[1-9]\d|1\d\d|2[0-4]\d|25[0-4])", address)]
    if len(matches) != 1:
        raise RuntimeError("Mac Wi-Fi (en0) is not on the camera's 192.168.0.x hotspot; connect it first")
    return matches[0]


def get(port, path):
    if path not in PATHS or port not in PORTS:
        raise ValueError("request is outside the fixed read-only allowlist")
    connection = http.client.HTTPConnection(CAMERA_IP, port, timeout=2)
    try:
        connection.request("GET", path, headers={"Accept": "application/json", "Connection": "close"})
        response = connection.getresponse()
        body = response.read(8193)
        if len(body) > 8192:
            raise RuntimeError("camera response exceeds the 8 KiB read limit")
        return {
            "port": port,
            "path": path,
            "status": response.status,
            "content_type": response.getheader("Content-Type", ""),
            "body_length": len(body),
            "body_sha256": hashlib.sha256(body).hexdigest(),
            "body_text": body.decode("utf-8", "replace"),
        }
    finally:
        connection.close()


def main():
    local_ip = wifi_ipv4()
    print(f"Mac Wi-Fi address: {local_ip}; camera target: {CAMERA_IP}", flush=True)
    results = []
    selected_port = None
    for port in PORTS:
        try:
            reply = get(port, PATHS[0])
            results.append(reply)
            print(f"GET {CAMERA_IP}:{port}{PATHS[0]} -> HTTP {reply['status']}", flush=True)
            if reply["status"] == 200:
                selected_port = port
                break
        except (OSError, http.client.HTTPException, RuntimeError) as error:
            results.append({"port": port, "path": PATHS[0], "error": f"{type(error).__name__}: {error}"})
            print(f"GET {CAMERA_IP}:{port}{PATHS[0]} -> {type(error).__name__}", flush=True)

    if selected_port is not None:
        try:
            reply = get(selected_port, PATHS[1])
            results.append(reply)
            print(f"GET {CAMERA_IP}:{selected_port}{PATHS[1]} -> HTTP {reply['status']}", flush=True)
        except (OSError, http.client.HTTPException, RuntimeError) as error:
            results.append({"port": selected_port, "path": PATHS[1], "error": f"{type(error).__name__}: {error}"})
            print(f"GET {CAMERA_IP}:{selected_port}{PATHS[1]} -> {type(error).__name__}", flush=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    output = OUTPUT_DIR / f"wifi-readonly-{stamp}.json"
    report = {"camera_ip": CAMERA_IP, "mac_wifi_ip": local_ip, "requests": results}
    with output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"Saved: {output}")
    return 0 if selected_port is not None else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Probe stopped: {error}", file=sys.stderr)
        sys.exit(2)
