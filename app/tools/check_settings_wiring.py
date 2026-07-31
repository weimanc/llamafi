#!/usr/bin/env python3
"""check_settings_wiring.py — ADR-050 settings-ownership static gate.

M-SETTINGS-WIRE2 §6c: every AppSettings field must appear in
(a) SettingsStorage::load(), (b) SettingsStorage::save(), and
(c) >= 1 consumer file OUTSIDE app/src/settings/ + settingsStorage.* —
i.e. every persisted setting has a runtime owner that is not the
Settings UI. Automates the 2026-07-16 audit that found G1-G5.

Warn-only initially (exit 0 unless --strict): wired as a run/check
step; promote by flipping STRICT_DEFAULT once green in the field.
Allowlist: documented-reserved fields with no consumer yet by design.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "app" / "src"
HDR = SRC / "settingsStorage.h"
CPP = SRC / "settingsStorage.cpp"

# Documented-reserved (settingsStorage.h comments): no consumer by design.
# tzName: UI display companion of posixTz — the runtime consumer of the
# timezone is posixTz (boot configTzTime); tzName exists only so the
# Settings UI can show a human-readable zone name.
ALLOWLIST = {"teletextAutoAdvance", "tzName"}

STRICT_DEFAULT = False


def parse_fields():
    """Member names of struct AppSettings (top-level fields, incl. arrays)."""
    text = HDR.read_text()
    m = re.search(r"struct AppSettings \{(.*?)\n\};", text, re.S)
    if not m:
        sys.exit("check_settings_wiring: cannot find struct AppSettings")
    fields = []
    for line in m.group(1).splitlines():
        line = line.split("//")[0].strip()
        if not line or line.startswith(("#", "/", "*")):
            continue
        # e.g. "char posixTz[48];" / "float lat, lon;" / "PrLocation prLocs[PR_NUM_LOCS];"
        decl = re.match(r"[A-Za-z_][\w:<>]*\s+(.+);$", line)
        if not decl:
            continue
        for part in decl.group(1).split(","):
            name = re.sub(r"\[.*\]", "", part).strip().lstrip("*&")
            if re.fullmatch(r"[A-Za-z_]\w*", name):
                fields.append(name)
    return fields


def main():
    strict = STRICT_DEFAULT or "--strict" in sys.argv
    fields = parse_fields()

    cpp = CPP.read_text()
    load_i, save_i = cpp.find("void SettingsStorage::load"), cpp.find("void SettingsStorage::save")
    load_body, save_body = cpp[load_i:save_i], cpp[save_i:]

    consumer_files = [
        p for p in SRC.rglob("*")
        if p.suffix in (".h", ".cpp")
        and "settings" != p.parent.name
        and p.name not in ("settingsStorage.h", "settingsStorage.cpp")
    ]
    blobs = {p: p.read_text(errors="replace") for p in consumer_files}

    problems = []
    for f in fields:
        missing = []
        if f not in load_body:
            missing.append("load()")
        if f not in save_body:
            missing.append("save()")
        pat = re.compile(r"g_settings\s*\.\s*" + re.escape(f) + r"\b")
        consumers = [p.name for p, b in blobs.items() if pat.search(b)]
        if not consumers and f not in ALLOWLIST:
            missing.append("consumer outside settings/")
        if missing:
            problems.append((f, missing, consumers))

    print(f"check_settings_wiring: {len(fields)} AppSettings fields, "
          f"{len(ALLOWLIST)} allowlisted ({', '.join(sorted(ALLOWLIST))})")
    if not problems:
        print("check_settings_wiring: OK — every field wired (ADR-050)")
        return 0
    for f, missing, consumers in problems:
        print(f"  WARN {f}: missing {', '.join(missing)}"
              + (f" (consumers: {', '.join(consumers)})" if consumers else ""))
    print(f"check_settings_wiring: {len(problems)} field(s) unwired"
          + ("" if strict else " (warn-only — ADR-050 gate not yet promoted)"))
    return 1 if strict else 0


if __name__ == "__main__":
    sys.exit(main())
