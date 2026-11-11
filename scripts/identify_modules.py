#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Find the 'MW' game modules inside X_DATA.BIN and identify which game each is.

Usage: identify_modules.py <X_DATA.BIN>

Each module is an AFS member with magic  02 00 "MW" "o3" <index>  wrapping one
named file (b_usa.bin, ro1_usa.bin .. ro9_usa.bin). The wrapped file begins with
MIPS code; the payload is compressed. We identify games by embedded ID/region
codes, copyright years and module size. See the README for the gotchas
(SZ3H = Hispanic region, not 'Hyper'; 'HYPER SHINCHAN' is a shared sound credit).
"""
import sys, struct, re


def main(path):
    with open(path, "rb") as f:
        f.seek(4); count = struct.unpack("<I", f.read(4))[0]
        toc = [struct.unpack("<II", f.read(8)) for _ in range(count)]
        mods = []
        for i, (off, size) in enumerate(toc):
            f.seek(off)
            if f.read(4) == b"\x02\x00MW":
                f.seek(off + 6); idx = f.read(1)[0]
                mods.append((idx, i, off, size))
        mods.sort()
        print(f"{len(mods)} MW modules\n")
        for idx, i, off, size in mods:
            f.seek(off); data = f.read(size)
            text = " ".join(s.decode("latin1")
                             for s in re.findall(rb"[ -~]{4,}", data))
            fn = [s.decode() for s in re.findall(rb"[A-Za-z0-9_]+\.bin", data)]
            ids = sorted({t for t in
                          ["SFZ", "SFA", "ZERO", "ALPHA", "POCKET", "GEM",
                           "zero2alp", "pocket"]
                          if re.search(re.escape(t), text, re.I)})
            sz3 = sorted(set(re.findall(r"SZ3[A-Z]", text)))
            ism = sorted(set(re.findall(r"\b(ISM|Saikyo|Shadaloo)\b", text, re.I)))
            years = sorted(set(re.findall(r"(?:19|20)\d\d", text)))
            name = fn[0] if fn else "?"
            print(f"MW idx {idx:>2}  {name:<13} {size:>9,}  "
                  f"ids={ids} sz3={sz3} ism={bool(ism)} years={years}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__); sys.exit(1)
    main(sys.argv[1])
