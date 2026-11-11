# Street Fighter Alpha Anthology (PS2) — reverse-engineering notes

Notes from taking apart the **Street Fighter Alpha Anthology** disc (PlayStation 2,
US release `SLUS-21317`, in Japan *Street Fighter Zero: Fighters' Generation*), with
one question in mind:

> Can the arcade games on this disc — in particular the secret **Hyper Street Fighter
> Alpha** — be used as a source of CPS-2 ROM data, e.g. to feed a static-recompilation
> project like [cps2recomp](https://github.com/tmcleroy/cps2recomp)?

Short answer: **no, and the reason is interesting.** The games on the disc do **not**
appear to run as interpreted CPS-2 (Motorola 68000) programs at all. They run as
**native PlayStation-2 MIPS code**, reusing the original games' *data* (graphics,
tables, text) but not their *code*. There is no resident 68000 program image to
extract. This write-up documents the file formats, the per-game modules, how to
identify them, why the payloads can't be disassembled statically, and the dynamic
(PCSX2 RAM-dump) analysis that settled the emulation-vs-port question.

**This repository contains no game data** — only analysis notes and the scripts used
to produce them. You need your own legally obtained disc image to reproduce anything.

---

## TL;DR

- The two giant files `X_DATA.BIN` (≈200 MB) and `Y_DATA.BIN` (≈1.8 GB) are **AFS
  archives** (CRI Middleware container; the main ELF uses CRI's `adxf_`/`adxt_`
  functions). AFS is an uncompressed container, not a compression format.
- `X_DATA.BIN` (553 members) holds PS2 presentation graphics (**TIM2** textures,
  **MOMO** containers) **plus** the arcade data blobs **plus** ten `MW` game modules.
- `Y_DATA.BIN` (588 members) is **CRI ADX streamed audio** (48 kHz; member header field
  `00 00 BB 80` = 48000) — music and voices.
- The games live in ten `MW` containers inside `X_DATA.BIN`: `b_usa.bin` (the shell)
  and **`ro1_usa.bin` … `ro9_usa.bin`** (nine selectable game modules). Each module
  **starts with MIPS code** (`27 bd ff f0` = `addiu sp,sp,-16`) and the bulk is
  **compressed**.
- `ro9_usa.bin` (the largest module, 3.5 MB, Alpha-3-based, referencing both "ZERO 3"
  and "ALPHA 3") is the best candidate for **Hyper Street Fighter Alpha**. See the
  confidence notes below — this is a *metadata* identification, not a code-level proof.
- The compressed modules can't be disassembled statically. We dumped PCSX2's **32 MB
  EE RAM** while Hyper SF Alpha was running and searched it. Result: **on the order of
  1 MB of coherent MIPS code, zero disassemblable 68000 code** in any byte order, and **no
  resident 68000 program ROM** (plaintext or encrypted). Only the CPS-2 *data* (e.g. the
  `"SZ3J ZERO 3"` / `"SZ3U ALPHA 3"` region table) is present, as plain MIPS-accessible
  data structures.
- Conclusion: the Anthology's games run as **native code, not low-level 68000
  emulation**. Whether hand-ported or recompiled offline, there is **no 68000 program
  being interpreted from a resident image**, so there is nothing clean to extract for a
  CPS-2 recomp. (The development technique is not officially documented; this is an
  inference from the running image.)

---

## Disc layout (US, `SLUS-21317`)

Root of the extracted ISO:

| File | Size | What it is |
|---|---:|---|
| `SLUS_213.17` | 572 KB | EE main ELF — the shell/front-end (and, presumably, the native game runtime) |
| `MODULE.BIZ` | 191 KB | MOMO-wrapped **IOP driver modules** (`loadcore`, `modload`, `Sio2dDrv`, `_Synthesizer_Module`) — not game code |
| `SYSDATA.BIZ` | 615 KB | System/shell data (fonts/UI/config); offset table header, no game strings |
| `X_DATA.BIN` | 200,214,528 | **AFS archive**: PS2 graphics + arcade data + the game modules |
| `Y_DATA.BIN` | 1,823,404,032 | **AFS archive**: CRI ADX streamed audio (48 kHz) |
| `*.IRX`, `IOPRP.IMG`, `0FLIST.*`, `HDDRC*.BIN` | small | PS2 IOP modules / loaders / HDD support |

`SYSTEM.CNF` boots `cdrom0:\SLUS_213.17`.

---

## AFS container format

Both `X_DATA.BIN` and `Y_DATA.BIN` start with `41 46 53 00` = **`AFS\0`**.

```
offset  size  field
0x00    4     "AFS\0"
0x04    4     uint32  file count (LE)
0x08    8*N   TOC: for each file -> {uint32 offset, uint32 size} (LE)
...     8     {uint32 offset, uint32 size} pointer to a filename directory
                (here 0/0 = no directory; members are identified by content only)
```

- `X_DATA.BIN`: **553** members. `Y_DATA.BIN`: **588** members.
- File offsets are `0x800`-aligned (PS2 CD sector size).
- No filename directory on this disc, so members are anonymous — you identify them by
  their magic bytes / embedded strings.

See `scripts/afs_inspect.py`.

### `X_DATA.BIN` member types (by leading 4 bytes)

| Magic | Count | Meaning |
|---|---:|---|
| `80 04 54 49` (`..TI`, TIM2) | 206 | PS2 **TIM2** textures (UI/presentation) |
| `00 00 00 00` | 189 | Large data blobs (4–8 MB), entropy 5–7 — the **arcade graphics** (CPS-2 tile data) |
| `4D 4F 4D 4F` (`MOMO`) | 37 | Capcom MOMO texture/asset containers |
| `02 00 4D 57` (`..MW`) | 10 | **The game modules** (see below) |
| misc | — | palettes, small tables, etc. |

### `Y_DATA.BIN` members — CRI ADX audio

Every member begins `80 00 xx xx 03 12 04 02 00 00 BB 80 …`. The constant field at
offset 8 is `0x0000BB80` = **48000** (sample rate). Member 0 is near-silent
(entropy ≈ 0.007); the rest sit around entropy 7.0 (ADPCM-style, not 8.0/encrypted).
The EE ELF streams these through CRI ADX (`adxt_StartAfs`, `adxf_GetPtStat`, …). So
`Y_DATA.BIN` is the **soundtrack + voices**, not game code.

---

## The game modules: `MW` containers

Ten `X_DATA.BIN` members carry magic `02 00 "MW" "o3" <index>`. Each wraps **one named
file**, and that file **begins with MIPS code** (the classic `27 bd ff f0` =
`addiu $sp,$sp,-16` prologue, big function body with `jal`/`sd $ra`). The contained
files are:

| MW index | Member # | Filename | Size | Identified as | Confidence |
|---:|---:|---|---:|---|---|
| 1 | 203 | `b_usa.bin` | 41,738 | **Shell / boot / menu** (lists all titles) | certain |
| 2 | 206 | `ro1_usa.bin` | 1,037,144 | **Street Fighter Alpha** (`SFZ`, `ALPHA!`, 1995) | high |
| 3 | 224 | `ro2_usa.bin` | 1,804,536 | **Street Fighter Alpha 2** (`ZERO`/`ALPHA 2`, 1996) | high |
| 4 | 253 | `ro3_usa.bin` | 2,369,958 | **Street Fighter Alpha 3** (`SZ3` all 7 regions; `ISM`/`Saikyo`/`Shadaloo`) | high |
| 5 | 348 | `ro4_usa.bin` | 1,847,602 | **Zero 2 Alpha / Alpha 2 Gold** (`zero2alp`, 1996) | high |
| 6 | 350 | `ro5_usa.bin` | 2,834,876 | **Alpha 3** (2nd revision/variant; `SZ3` + `ISM`) | medium |
| 7 | 526 | `ro6_usa.bin` | 1,852,844 | **Zero 2 Alpha** (variant, 1996) | medium |
| 8 | 536 | `ro7_usa.bin` | 1,498,996 | **Super Gem Fighter / Pocket Fighter** (`pocket`, `GEM`, 1997) | high |
| 9 | 543 | `ro8_usa.bin` | 1,831,114 | **Alpha-2-family variant** (1996) | medium |
| 10 | 544 | `ro9_usa.bin` | 3,502,644 | **Hyper Street Fighter Alpha** (largest; `SZ3`; references `ZERO 3` + `ALPHA 3`) | best candidate |

The US compilation exposes six games (Alpha 1/2/2-Gold/3, Super Gem Fighter, and the
secret Hyper SF Alpha). Nine `ro` modules means **three are revision/region variants**
the version menu can toggle; the exact split of ro3/ro5 (Alpha 3) and ro8 (Alpha-2
family) is not pinned down here.

See `scripts/identify_modules.py`.

### Gotchas when identifying modules (saves you time)

- **`SZ3H` is not "Hyper"** — it's the CPS-2 **region code for Hispanic**. The Alpha 3
  region codes are `SZ3J` (Japan), `SZ3U` (USA), `SZ3A` (Asia), `SZ3B` (Brazil),
  `SZ3E` (Europe), `SZ3H` (Hispanic), `SZ3N` (Oceania). Every Alpha 3 build has all of
  them; it tells you nothing about Hyper.
- **`HYPER SHINCHAN` / `URUMA`** appears in almost every module — it's a shared QSound
  credit string, not a game title. Ignore it when searching for "HYPER".
- Game titles on screen are **graphics (TIM2)**, not ASCII, so you won't find
  `"HYPER STREET FIGHTER ALPHA"` as a string. Identify by region/ID codes, years, and
  module size instead.

### Why `ro9` is the Hyper SF Alpha candidate

- It is the **largest** module (3.5 MB) — larger than a plain Alpha 3 program
  (~2.4–2.8 MB). Hyper SF Alpha's defining feature is *edition select* (pick each
  character's Alpha-1/2/3 incarnation), which needs the extra cross-version data.
- It is **Alpha-3-engine-based** (`SZ3` codes) and references both `ZERO 3` (JP name)
  and `ALPHA 3` (US name) in one module.

This remains a **metadata** argument. A code-level proof (finding the edition-select
table) was blocked — see below.

---

## Are the CPS-2 programs extractable? No — the modules are compressed

Inside each `ro*_usa.bin`, after the MIPS wrapper you find readable CPS-2 *data*
strings (e.g. `SFZ!SFA!`, `QSound technology is pr…`, `@1995,2006 CAPCOM`). Tempting —
but the program **code** is **compressed**. Evidence (`scripts/compression_test.py`):

| Test | Real decrypted CPS-2 program (control) | `ro*` module |
|---|---|---|
| Longest run of identical 4-byte longs | **191×** | 8× |
| Runs of ≥16 identical longs | **26** | **0** |
| 68000 exception vector table | present (repeated default vector) | **none** (any byte order) |
| Linear 68000 disassembly | coherent (`jsr`/`bsr`/flow) | **incoherent noise** |

Compressed data has essentially no long repeats; the complete absence of any
long-run in the modules (vs 26 in a real CPS-2 program) is the tell. Entropy alone
does **not** distinguish them (a real CPS-2 program chip is ~6.8, similar to the
modules) — the long-run test and the vector-table test are what settle it. The MIPS
code at the front of each module is the decompressor.

> Note on CPS-2 encryption: an authentic CPS-2 program ROM has its **opcodes
> encrypted** (plaintext *data*, high-entropy *code*). A naive "readable strings ⇒
> decrypted" assumption is wrong. Here, neither a decrypted nor an encrypted 68000
> program is present — the payload is simply compressed native-code-and-data.

---

## Dynamic analysis: dumping PCSX2 EE RAM

To see the decompressed, running game we dumped PlayStation-2 main memory from PCSX2.

1. Run the disc in PCSX2, reach Hyper SF Alpha (title screen and/or in a match).
2. Make a save state (`F1`). On macOS these land in
   `~/Library/Application Support/PCSX2/sstates/` as `SLUS-21317 (…).NN.p2s`.
3. A `.p2s` is a **ZIP**, but PCSX2 compresses the entries with **Zstandard
   (method 93)** — macOS `unzip`/`bsdtar` can't read it. Extract the raw zstd stream for
   `eeMemory.bin` (32 MiB) from the ZIP central directory and run `zstd -d`.
   See `scripts/extract_savestate_ram.py`.

Savestate contents: `eeMemory.bin` (33,554,432 = 32 MiB EE RAM), `iopMemory.bin`
(2 MiB), `vu*Memory.bin`, `GS.bin`, `SPU2.bin`, `Screenshot.png`, etc.

### What is in the 32 MB EE RAM

- The CPS-2 game **data** is there, in **normal byte order**: the Alpha-3 region table
  at ≈`0x666700`, laid out as ~0x30-byte entries:
  ```
  … 98 09 04 00  "SZ3J ZERO 3 "  …
  … 98 09 04 02  "SZ3U ALPHA 3 " …
  ```
  plus `SFZ`/`SFA`/`ALPHA 3`/`ZERO 3` strings elsewhere. These are plain,
  low-entropy, MIPS-accessible data structures — reused assets.
- **No 68000 program.** We scanned all 32 MB for a 68000 vector table (big-endian,
  16-bit word-swap, and 32-bit byte-swap) and for 68000 control-flow density:
  **nothing** — at most 2–5 "flow" instructions per KB, i.e. noise.
- **On the order of 1 MB of coherent MIPS code** across hundreds of regions (the exact
  figure depends on the detection threshold in `scan_cpu.py`), with real calls, stack
  frames and branches (thousands of them). This is the native engine actually executing.

See `scripts/scan_cpu.py`.

### The decisive point

A low-level 68000 emulator **must** keep the 68000 program resident to fetch opcodes
from. It isn't there — not as plaintext, not as a large encrypted/compressed block, not
in any byte order. Meanwhile the EE is full of real MIPS code and the game's *data* is
present as native structures. The only consistent reading is:

> **The Anthology's games execute as native PlayStation-2 MIPS code, not as interpreted
> 68000 programs.** The original games' data was carried over; their logic was
> re-implemented or recompiled to run natively.

We can't tell *hand-port* from *static recompilation* from the running image alone, and
the development technique is not officially documented. But either way there is no
resident 68000 program, so the "dump the CPS-2 ROM from emulated memory" plan does not
apply to this disc.

---

## Conclusions

1. `X_DATA.BIN` / `Y_DATA.BIN` are **AFS archives**: graphics/modules and ADX audio.
2. The games are ten **MW modules** (`b_usa` + `ro1..ro9`), each a **MIPS module with a
   compressed payload**.
3. The payloads **cannot** be statically disassembled as 68000 (compressed), and the
   running image contains **no 68000 program** — only native MIPS code plus reused
   CPS-2 data.
4. Therefore the Anthology is **not a usable source of CPS-2 ROMs**. For the arcade
   games this doesn't matter (dump the real PCBs). For **Hyper Street Fighter Alpha**,
   which has no arcade release, this disc is the only copy — but it exists here as
   native PS2 code + data, so bringing it to a CPS-2 recomp would be a full
   reimplementation, not an extraction.
5. `ro9_usa.bin` is the best-supported **metadata** identification of Hyper SF Alpha; a
   code-level proof was not achievable by these means.

Nice irony: turning CPS-2 logic into native code is exactly what
[cps2recomp](https://github.com/tmcleroy/cps2recomp) does today. Capcom shipped a
closed-source, MIPS-targeted version of the same idea on the PS2 back in 2006.

---

## Reproduction

Requirements: Python 3.9+, [`capstone`](https://pypi.org/project/capstone/) (with
M68K + MIPS support, v4+), and the `zstd` CLI (for the save-state step). A legally
obtained disc image of your own, extracted to a folder.

```bash
python3 -m venv .venv && .venv/bin/pip install capstone
# 1) list an AFS archive and classify its members
.venv/bin/python scripts/afs_inspect.py /path/to/X_DATA.BIN
# 2) find and identify the MW game modules
.venv/bin/python scripts/identify_modules.py /path/to/X_DATA.BIN
# 3) show that a given module's payload is compressed (vs a real CPS-2 program)
.venv/bin/python scripts/compression_test.py /path/to/extracted_module.bin [/path/to/real_cps2_prog.bin]
# 4) pull eeMemory.bin out of a PCSX2 .p2s save state
.venv/bin/python scripts/extract_savestate_ram.py "/path/to/SLUS-21317 (xxxxxxxx).01.p2s" ./eeMemory.bin
# 5) scan a memory dump for 68000 vs MIPS code
.venv/bin/python scripts/scan_cpu.py ./eeMemory.bin
```

The scripts take file paths as arguments and never ship or require game data.

---

## Caveats / open questions

- **Port vs recompilation** is unresolved. "Native MIPS, no resident 68000" is strongly
  supported; the exact technique is not.
- The **ro3/ro5/ro8** variant split (which Alpha 3 / Alpha 2 revision is which) is not
  pinned down.
- A full code-level proof of the Hyper-specific edition-select logic would mean reverse
  engineering the **native MIPS engine** (e.g. tracing in the PCSX2 EE debugger from the
  version-table reads at ≈`0x666700`). That's a separate, substantial project.
- Numbers (sizes, member counts, offsets) are from the specific US `SLUS-21317` dump
  analyzed here; other regions/revisions will differ.

## Legal / ethical note

This repository documents file formats and contains **no game data, ROMs, keys, save
files, or extracted bytes**. Reproducing the analysis requires a disc image you own.
Nothing here circumvents CPS-2 encryption or distributes copyrighted material.

## License

Documentation and scripts in this repo: MIT (see `LICENSE`). Trademarks and game
content belong to Capcom.
