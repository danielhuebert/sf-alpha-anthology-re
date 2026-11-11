#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Extract eeMemory.bin (the 32 MiB PS2 EE RAM) from a PCSX2 .p2s save state.

Usage: extract_savestate_ram.py <savestate.p2s> <output.bin> [member]

A PCSX2 .p2s is a ZIP whose entries are compressed with Zstandard (method 93),
which macOS `unzip`/`bsdtar` cannot read. We locate the entry via the ZIP central
directory (Python's zipfile), read its raw compressed bytes, and decompress with
the `zstd` CLI (default) or the `zstandard` module if installed.

Default member is 'eeMemory.bin'. Other useful members: iopMemory.bin, GS.bin.
"""
import sys, os, struct, zipfile, subprocess, tempfile


def extract(zp, member, out):
    z = zipfile.ZipFile(zp)
    info = z.getinfo(member)
    print(f"{member}: method={info.compress_type} "
          f"comp={info.compress_size:,} raw={info.file_size:,}")
    with open(zp, "rb") as f:
        f.seek(info.header_offset)
        hdr = struct.unpack("<IHHHHHIIIHH", f.read(30))
        nlen, elen = hdr[9], hdr[10]
        f.seek(info.header_offset + 30 + nlen + elen)
        raw = f.read(info.compress_size)

    if info.compress_type == 0:  # stored
        open(out, "wb").write(raw); return
    if info.compress_type != 93:
        # let zipfile handle anything it supports (deflate etc.)
        open(out, "wb").write(z.read(member)); return

    # method 93 = zstd
    assert raw[:4] == b"\x28\xb5\x2f\xfd", "not a zstd frame"
    try:
        import zstandard
        open(out, "wb").write(zstandard.ZstdDecompressor().decompress(
            raw, max_output_size=info.file_size))
    except ImportError:
        with tempfile.NamedTemporaryFile(suffix=".zst", delete=False) as t:
            t.write(raw); tmp = t.name
        subprocess.run(["zstd", "-d", "-f", tmp, "-o", out], check=True)
        os.unlink(tmp)
    print(f"wrote {out} ({os.path.getsize(out):,} bytes)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    member = sys.argv[3] if len(sys.argv) > 3 else "eeMemory.bin"
    extract(sys.argv[1], member, sys.argv[2])
