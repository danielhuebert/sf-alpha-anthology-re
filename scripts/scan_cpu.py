#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Scan a memory/ROM dump for Motorola 68000 vs MIPS code density.

Usage: scan_cpu.py <dump.bin>

The point of this script (run on a PCSX2 eeMemory.bin captured from the Alpha
Anthology) is the contrast: the EE RAM is full of coherent MIPS code and contains
NO disassemblable 68000 code in any byte order. A low-level CPS-2 emulator would
have to keep the 68000 program resident; it isn't there -> the games run natively.

Needs capstone with M68K + MIPS support (v4+).
"""
import sys, array, collections
import capstone

M68K = capstone.Cs(capstone.CS_ARCH_M68K,
                   capstone.CS_MODE_BIG_ENDIAN | capstone.CS_MODE_M68K_000)
MIPS = capstone.Cs(capstone.CS_ARCH_MIPS,
                   capstone.CS_MODE_MIPS64 | capstone.CS_MODE_LITTLE_ENDIAN)

M68K_FLOW = {"jsr", "bsr", "rts", "rte", "bra", "jmp", "dbra", "dbf",
             "beq", "bne", "bcc", "bcs", "bge", "blt", "bgt", "ble"}
MIPS_FLOW = {"jal", "jalr", "jr", "j", "beq", "bne", "blez", "bgtz",
             "bltz", "bgez", "bal", "b"}


def flow_density(md, buf, flowset):
    return sum(1 for i in md.disasm(buf, 0) if i.mnemonic in flowset)


def scan_68000(data):
    sw = array.array("H"); sw.frombytes(data); sw.byteswap()
    swapped = sw.tobytes()
    b32 = bytearray(len(data))
    for o in range(0, len(data) - 3, 4):
        b32[o:o + 4] = data[o:o + 4][::-1]
    best = {}
    for label, buf in [("big-endian", data), ("word-swap", swapped),
                       ("32-bit swap", bytes(b32))]:
        m = max((flow_density(M68K, buf[o:o + 1024], M68K_FLOW)
                 for o in range(0, len(buf) - 1024, 0x4000)), default=0)
        best[label] = m
    print("68000 control-flow per 1KB (max over dump):")
    for k, v in best.items():
        print(f"  {k:<12}: {v}   ({'noise / no 68000 code' if v < 10 else 'possible code'})")


def scan_mips(data):
    def is_zero(b):
        return b.count(0) > len(b) * 0.6
    regions = []; cur = None; total = 0
    for o in range(0, len(data) - 1024, 0x400):
        w = data[o:o + 1024]
        if is_zero(w):
            if cur:
                regions.append(cur); cur = None
            continue
        br = flow_density(MIPS, w, MIPS_FLOW)
        n = sum(1 for _ in MIPS.disasm(w, 0))
        codey = br >= 15 and n > 200
        if codey:
            cur = (cur[0], o + 1024) if cur else (o, o + 1024)
        elif cur:
            regions.append(cur); cur = None
    if cur:
        regions.append(cur)
    total = sum(e - s for s, e in regions)
    regions.sort(key=lambda r: -(r[1] - r[0]))
    print(f"\nMIPS code regions: {len(regions)}, total ~{total // 1024} KB")
    for s, e in regions[:8]:
        print(f"  0x{s:X}..0x{e:X}  ({(e - s) // 1024} KB)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__); sys.exit(1)
    data = open(sys.argv[1], "rb").read()
    print(f"dump: {len(data):,} bytes\n")
    scan_68000(data)
    scan_mips(data)
