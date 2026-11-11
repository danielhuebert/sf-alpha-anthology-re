#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Show that a module payload is compressed, by contrast with a real CPS-2 program.

Usage: compression_test.py <module.bin> [<real_cps2_program.bin>]

Tests, for each file:
  * entropy (a real CPS-2 program chip is ~6.8, so entropy ALONE is not a tell);
  * the longest run of identical 4-byte longs and how many runs of >=16 there are
    (real ROM data is full of long repeats: fill regions, vector tables, repeated
    graphics; compressed data has essentially none);
  * a crude 68000 exception-vector-table probe.

On this disc the arcade modules show max-run 8 and zero runs >=16, while a real
decrypted CPS-2 program shows a 191x run and dozens of >=16 runs.
"""
import sys, math, collections, struct


def entropy(b):
    if not b:
        return 0.0
    c = collections.Counter(b); n = len(b)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def long_runs(data, thr=16):
    runs = []; prev = None; r = 0; st = 0; longest = (None, 0, 0)
    for o in range(0, len(data) - 4, 4):
        x = data[o:o + 4]
        if x == prev:
            r += 1
        else:
            if r > longest[1]:
                longest = (prev, r, st)
            if r >= thr:
                runs.append((st, prev.hex(" "), r))
            prev = x; r = 1; st = o
    return longest, runs


def has_vector_table(data):
    # any 2-byte-aligned offset where 256 big-endian longs look like a 68000
    # vector table (>=200 point to even addresses < 0x400000)
    for o in range(0, min(len(data), 0x400000) - 1024, 2):
        longs = struct.unpack(">256I", data[o:o + 1024])
        good = sum(1 for v in longs[2:] if 0 < v < 0x400000 and v % 2 == 0)
        if good >= 200:
            return o
    return None


def report(path):
    data = open(path, "rb").read()
    (lv, lr, lo), runs = long_runs(data)
    vt = has_vector_table(data)
    print(f"{path}")
    print(f"  size={len(data):,}  entropy={entropy(data):.3f}")
    print(f"  longest identical 4-byte run: {lr}x "
          f"[{lv.hex(' ') if lv else '-'}] @0x{lo:X}")
    print(f"  runs of >=16 identical longs: {len(runs)}")
    print(f"  68000 vector table: {'@0x%X' % vt if vt is not None else 'none'}")
    print(f"  -> verdict: {'looks UNCOMPRESSED (real ROM)' if len(runs) >= 5 or vt is not None else 'looks COMPRESSED'}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    for p in sys.argv[1:]:
        report(p); print()
