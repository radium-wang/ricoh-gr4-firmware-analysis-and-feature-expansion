#!/usr/bin/env python3
"""Build a one-boot GR IV SD probe for Linux bridge replies.

Offline builder only. The generated TTL never changes firmware or USB config.
It temporarily enables lcmd_resp only after reading its old RAM value, then
restores the old value before writing result files.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

from build_sd_bridge_gate import build_ttl


def make_ttl():
    script = build_ttl()
    for old, new in (
        ("BRTEST.TXT", "LRTEST.TXT"),
        ("BRBOOT.BIN", "LRBOOT.BIN"),
        ("BRPRE.BIN", "LRPRE.BIN"),
        ("BRPOST.BIN", "LRPOST.BIN"),
    ):
        script = script.replace(old, new)
    script = script.replace("bridge gate started", "Linux reply probe started")
    script = script.replace("bridge gate finished", "Linux reply probe finished")
    script = script.replace("mpause 10000", "mpause 45000", 1)
    begin = script.index("sendln 'is_linux_boot'")
    end = script.index("tag = 'bridge object read available'", begin)
    replacement = r"""reply_ok = 0
if bridge_ok = 1 then
    ufile = 'C:\LRPRE.BIN'
    uoff = 116
    call read_byte
    if uok = 1 then
        if uv >= 0 then
            if uv <= 1 then
                old_response = uv
                reply_ok = 1
            endif
        endif
    endif
endif
sendln 'is_linux_boot'
ready = result
tag = 'Linux readiness'
value = ready
call log_value
if ready = 1 then
    if reply_ok = 1 then
        if old_response = 0 then
            sendln 'lcmd_resp on'
        endif
        sendln 'lcmd "printf GR4_%s_READY LINUX"'
        marker_result = result
        marker_reply = inputstr
        sendln 'lcmd "/bin/uname -r"'
        uname_result = result
        uname_reply = inputstr
        if old_response = 0 then
            sendln 'lcmd_resp off'
        endif
        fileopen bf 'C:\LRTEST.TXT' 1
        filewriteln bf 'computed marker handler result (not execution proof)'
        int2str number marker_result
        filewriteln bf number
        filewriteln bf 'computed marker reply'
        filewriteln bf marker_reply
        filewriteln bf 'uname handler result (not execution proof)'
        int2str number uname_result
        filewriteln bf number
        filewriteln bf 'uname reply'
        filewriteln bf uname_reply
        fileclose bf
        mpause 5000
    endif
endif
tag = 'response flag read available'
value = reply_ok
call log_value
if bridge_ok = 1 then
    da = bridge_addr
    ds = 117
    dn = 'LRPOST.BIN'
    call dump_exact
endif
"""
    script = script[:begin] + replacement + script[end:]
    script = script.replace(
        "filesearch 'C:\\BRDONE.TXT'\n"
        "tag = 'Linux script marker exists'\n"
        "value = result\n"
        "call log_value\n",
        "",
    )
    marker = "GR4_LINUX_READY"
    assert marker not in script
    assert "sendln 'lcmd_resp on'" in script
    assert script.index("sendln 'lcmd_resp off'") < script.index("fileopen bf 'C:\\LRTEST.TXT' 1", begin)
    assert "SYS_reg" not in script
    assert "BRRUN.SH" not in script
    assert "BRDONE.TXT" not in script
    assert script.count("sendln 'lcmd ") == 2
    depth = 0
    labels = set(re.findall(r"^:([A-Za-z_][A-Za-z_0-9]*)$", script, re.M))
    calls = set(re.findall(r"^\s*call ([A-Za-z_][A-Za-z_0-9]*)$", script, re.M))
    assert calls <= labels
    for line in script.splitlines():
        line = line.strip()
        if line.startswith("if ") and line.endswith(" then"):
            depth += 1
        elif line == "endif":
            depth -= 1
            assert depth >= 0
    assert depth == 0
    return script


def build(output):
    output.mkdir(parents=True, exist_ok=False)
    script = make_ttl().encode("ascii")
    path = output / "script" / "startup.ttl"
    path.parent.mkdir()
    path.write_bytes(script)
    manifest = {
        "script/startup.ttl": {
            "size": len(script),
            "sha256": hashlib.sha256(script).hexdigest(),
        }
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))


if __name__ == "__main__":
    main()
