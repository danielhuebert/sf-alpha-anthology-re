#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Inspect a CRI AFS archive (as used by X_DATA.BIN / Y_DATA.BIN on the
Street Fighter Alpha Anthology disc). Read-only.

Usage: afs_inspect.py <file.afs>

Prints the entry count, the metadata pointer, a sample of members with their
leading bytes, and a histogram of member magics so you can tell graphics
(TIM2/MOMO), audio and the MW game modules apart.
"""
import sys, struct, os, collections


def main(path):
    with open(path, "rb") as f:
        if f.read(4) != b"AFS\x00":
            print("not an AFS archive"); return
        count = struct.unpack("<I", f.read(4))[0]
        print(f"AFS: {count} entries, file size {os.path.getsize(path):,}")
        toc = [struct.unpack("<II", f.read(8)) for _ in range(count)]
        meta_off, meta_size = struct.unpack("<II", f.read(8))
        print(f"TOC ends at 0x{8 + count * 8:X}; "
              f"metadata pointer -> off=0x{meta_off:X} size=0x{meta_size:X} "
              f"({'present' if meta_off else 'none (anonymous members)'})")

        def magic(off, n=16):
            f.seek(off); return f.read(n)

        print("\n#     offset        size         first bytes")
        for i, (off, size) in enumerate(toc[:40]):
            mg = magic(off)
            asc = "".join(chr(b) if 32 <= b < 127 else "." for b in mg)
            print(f"{i:<5} 0x{off:<10X} 0x{size:<10X} {mg[:8].hex(' ')}  |{asc}|")
        if count > 40:
            print(f"... ({count - 40} more)")

        hist = collections.Counter()
        for off, size in toc:
            if size >= 4:
                hist[magic(off, 4)] += 1
        print("\nLeading-4-byte magics (count, total size):")
        sizes = collections.Counter()
        for (off, size) in toc:
            if size >= 4:
                sizes[magic(off, 4)] += size
        for mg, n in hist.most_common(16):
            asc = "".join(chr(b) if 32 <= b < 127 else "." for b in mg)
            print(f"  {mg.hex(' ')} |{asc}|  x{n:<4} total={sizes[mg]:,}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__); sys.exit(1)
    main(sys.argv[1])
