# CLAUDE.md — PE-16 Protocol Emulator ASIC

Project context for Claude Code. Read this file fully at the start of every session.

## How to work with me

- Be direct, technical and rigorous. No filler, no preamble. Push back when something is wrong.
- **Solo project, ~2 h/day.** Each session has ONE task with a testable exit condition. At session start, propose that task, based on the plan and the current repo state. At session end, append an entry to `docs/log.md` (date, what was done, what's next, open issues).
- Prefer small, verifiable increments. Never leave the repo in a state where CI is red without noting it in the log.

## The competition

- **Jane Street "Protocol Emulator ASIC" competition:** https://blog.janestreet.com/protocol-emulator-asic-competition/ (re-read it when rules matter; don't invent rules).
- **Goal:** a general-purpose protocol emulator ASIC. A small, reprogrammable, timing-exact coprocessor that implements pin-level protocols (UART, SPI, I2C, …) as loadable programs. It must stay reprogrammable after fabrication, so no fixed protocol blocks.
- **Target:** IHP SG13 130 nm (CMOS5L) via Tiny Tapeout, **6x4 tiles** (~24 K cells nominal), possibly 8x4.
- **Judging emphasis:** unique functionality, and novel design *and verification* methodology.
- **Deadline:** Mon 18 Jan 2027. **Internal freeze:** 10 Jan 2027. **Submit by:** 13 Jan 2027.

## Scope tiers (~210 h budget)

- **Must**
  - Reprogrammable timed core; UART, SPI (modes 0–3) and I2C (clock stretching, NACK) as firmware.
  - Program loading over SPI from the RP2040.
  - GDS passing at 6x4.
  - Verification report.
- **Should**
  - Generic primitives: CRC LFSR, bit-stuff counter, NRZI/Manchester, edge timestamp.
  - SWD demo.
  - `pe` MLIR dialect with static timing analysis and path balancing (fed by a small textual format or Python bindings).
  - Verification: sigrok oracle, mutation testing, timing-checker cross-validation.
- **Could**
  - USB low-speed bit/packet layer (only if M2 is on time).
  - Restricted-C frontend ("PE-C") via ClangIR/Polygeist lowering into the `pe` dialect.
  - RV32E+Xpe FPGA-only comparison study.
  - EQY equivalence checking; AI-generated tests gated by the ISS and formal checks.
- **Won't:** 10BASE-T in silicon (FPGA-only at most, and only if the G1 measurements allow).

Cut Could items first, then Should.

## Schedule and gates

| Phase | Dates | Content | Gate |
|---|---|---|---|
| 0 | → 4 Oct | Toolchain, TT template to GDS, area/fmax/I-O measurements, FPGA blinky | **G1:** memory tech, clock target, HDL, 10BASE-T go/no-go |
| 1 | 5–25 Oct | ISA spec, YAML single source, Python ISS, assembler, UART/SPI/I2C firmware in ISS, area model | **G2:** freeze ISA v0, lane count, memory depth, data width |
| 2 | 26 Oct–22 Nov | RTL core, SPI host interface, loader, differential testing, formal, FPGA bring-up | **M2:** UART/SPI/I2C on FPGA, loaded at runtime; GDS passes |
| 3 | 23 Nov–13 Dec | Primitives, SWD, `pe` dialect + timing pass, (USB LS) | **G3:** RTL feature freeze |
| 4 | 14 Dec–3 Jan | Area/timing closure, gate-level sim, DRC/LVS | — |
| 5 | 4–17 Jan | Datasheet, verification report, demos, submission | — |

## Architecture summary (full spec: `docs/isa-v0.md`)

**PE-16:** N lanes (2–4, fixed at G2) share a 128×16 program memory with 7-bit addresses. 16-bit instructions, opcode in `[15:12]`.

**Opcodes:**

| Op | Mnemonic | Op | Mnemonic |
|---|---|---|---|
| 0 | `JMP` (16 conditions + invert) | 5 | `FIFO` |
| 1 | `WAIT` | 6 | `SET` |
| 2 | `PIN` | 7 | `MOV` |
| 3 | `OUT` | 8 | `CALL`/`RET` |
| 4 | `IN` | 9 | `CTRL` |

A–F are reserved.

**Time model (the core idea):**
- **R1.** Every instruction costs exactly 1 cycle, except waits and blocking FIFO operations.
- **R2.** A per-lane 24-bit phase accumulator forms the tick grid. TICK fires on wrap; HALF fires when `ACC[23]` rises.
- **R3.** A `WAIT` finishes on its event; the instruction k steps later executes at event + k, with no jitter.
- **R4.** `sync` sets `ACC ← 0` on the event, anchoring the grid to an external edge.

Execution runs at full speed against absolute deadlines. There's no PIO-style clock divider.

**Per-lane state:** PC, RA, X, Y (16), OSR/ISR (16) with counts, LEN, T (down-counter), CAP (edge timestamp), LFSR (16), F flag, ACC, line config, sticky flags (EDGE, STUFF, OVF, SIG).

**Pins:** each lane sees an 8-pin window.
- An open-drain mask makes a write of 1 release the pin.
- `PIN` writes all masked pins simultaneously.
- `SAMPLE` sets F to the OR of the masked inputs.
- `OUT`/`IN DIFF` handle a complementary pin pair.

**Primitives expose events; programs decide.** For example, bit stuffing sets the `STUFF` flag and the program emits `OUT STUFFBIT` explicitly.

**Host interface:** an SPI slave, oversampled by the system clock (single clock domain, no CDC). It provides:
- program load and readback;
- per-lane enable, start PC, pin base and USER bit;
- shared tables: `INC[0..3]` and CRC profiles `[0..1]`;
- FIFOs of 16 data bits plus a 4-bit tag.

**Open G2 decisions:** lane count; memory depth; data width (16 vs 32; SWD/JTAG need 32-bit words); LFSR width; whether Manchester is kept; call-stack depth.

**Design decisions already taken (don't relitigate without new data):**
- A custom ISA, not RISC-V, for the silicon, because of area, multi-lane support and determinism by construction.
- A PIO-like concept, but with the tick-grid timing model and generic primitives.

## Repository layout

```
docs/       isa-v0.md, isa.yaml (single source of truth), register map, log.md, plan
iss/        cycle-accurate Python ISS (golden model, timing-exact)
asm/        assembler + macro library (generated tables from isa.yaml)
programs/   protocol firmware (*.pe)
dialect/    MLIR `pe` dialect, passes (timing analysis, path balancing), translation
rtl/core/   shared, technology-independent Verilog (pe_top, pe_lane, pe_decode, pe_tickgrid, pe_spi_host)
rtl/tech/asic/pe_mem.v   latch RAM or IHP SRAM
rtl/tech/fpga/pe_mem.v   inferred BRAM
tt/         tt_um_pe.v (Tiny Tapeout top, shared by the FPGA build)
fpga/       top_tangnano20k.v (PLL, reset, tristates, pins), .cst, build scripts
tb/         cocotb tests, BFMs, random program generator, ISS scoreboard
formal/     SymbiYosys configs + properties (per-instruction + microarchitecture)
fw/         RP2040 host/loader firmware
```

Tiny Tapeout requires `info.yaml` and `src/` at the root; keep the template structure working and point it at `rtl/`.

## RTL rules (portability FPGA ↔ ASIC)

- **Clocking and reset:** one clock and one synchronous reset. No gated or derived clocks; the tick grid is an enable.
- **Inputs:** synchronize all external inputs with 2 flip-flops.
- **Open-drain:** implemented as output-enable (drive 0 with OE on, or release).
- **Portability:** no vendor primitives, no `initial` for state, no `ifdef FPGA` in the core. Technology differences go only in `rtl/tech/*` and are selected by the file list.
- **Memory:** `pe_mem` has a precisely defined port behaviour (synchronous read, 1-cycle latency). Both implementations are tested against the same testbench.
- **Tiny Tapeout interface:** `ui_in`, `uo_out`, `uio_in`/`uio_out`/`uio_oe`, `ena`, `clk`, `rst_n`. No `inout` in `tt/` or `rtl/`.

## Verification strategy (a headline feature)

1. **Single-source spec:** `docs/isa.yaml` generates the RTL decode tables, ISS decoder, assembler and ODS. Never hand-edit generated files.
2. **Differential testing:** a timing-aware constrained-random program generator runs RTL against the ISS, comparing state and pins every cycle.
3. **Per-instruction formal**, riscv-formal style: a trace port plus one BMC property per opcode from an arbitrary starting state.
4. **Microarchitecture formal:** tick-grid exactness, lane isolation, wait liveness, FIFO safety, host interface, reset with no X-states.
5. **Protocol tests:** cocotb BFMs with error injection; sigrok decoders as an independent oracle for both simulation and FPGA captures.
6. **Verifying the verifier:**
   - mutation testing (Yosys mutate);
   - static timing predictions must equal the offsets observed in the ISS;
   - translation validation of compiled programs against the ISS.
7. **Implementation checks:** gate-level sim with X-propagation; Tiny Tapeout DRC/LVS/STA; optional EQY.
8. **Hardware-in-the-loop** on the Tang Nano 20K with a Pico host; BIST programs for silicon bring-up.

CI (GitHub Actions) runs the TT GDS flow, cocotb, formal and FPGA synthesis, and tracks cell count and slack per commit.

## Toolchain and hardware

- **macOS (Apple Silicon):**
  - OSS CAD Suite: Yosys, SymbiYosys, Verilator, Icarus, nextpnr-himbaechel/Apicula.
  - cocotb.
  - LibreLane via Nix/Docker. CI is authoritative for GDS.
- **Hardware:** Sipeed Tang Nano 20K, Raspberry Pi Pico (host and SWD target), 24 MHz FX2 logic analyzer with sigrok/PulseView, I2C EEPROM, SPI NOR flash, USB-UART adapter, USB-A breakout. All 3.3 V.

## Current status

- Planning done; ISA draft v0 written (`docs/isa-v0.md`).
- **Next: Phase 0.**
  1. Sign-up form.
  2. Repo from the TT IHP template (6x4) with a trivial UART TX reaching GDS in CI.
  3. Measure: DFF vs latch-RAM vs SRAM area (64×16, 128×16), minimal-lane area, fmax, TT IHP mux max toggle rate, I/O voltage.
  4. Blinky + UART TX on the Tang Nano 20K.
  5. Create `docs/log.md`.
