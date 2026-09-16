# Protocol Emulator ASIC — Development Plan (solo)

**Target:** IHP SG13 130 nm (CMOS5L) via Tiny Tapeout, 6x4 tiles (~24 K cells), possibly 8x4.
**Deadline:** Mon 18 Jan 2027. **Internal freeze:** Sun 10 Jan 2027.
**Duration:** 17 working weeks (W1 = Mon 21 Sep 2026) plus this week as W0.

---

## 1. Scope tiers

| Tier | Content |
|---|---|
| **Must** | Reprogrammable timed core; UART, SPI (modes 0–3), I2C (incl. clock stretching, NACK) running from firmware; program loading over SPI from the RP2040; GDS passing at 6x4; verification report |
| **Should** | Generic protocol primitives (CRC LFSR, bit-stuff counter, NRZI/Manchester pin modes, edge timestamp); SWD demo; lightweight protocol DSL (Python) → assembly with a static timing check |
| **Could** | USB low-speed bit/packet layer (only if M2 lands on time); full MLIR dialect stack; PS/2, CAN (CRC15 + stuffing, via external transceiver); multi-lane synchronized protocols; use of 8x4 if offered |
| **Won't (default)** | 10BASE-T in silicon. Revisit only if the week-2 I/O measurements say it is feasible. FPGA-only demo is acceptable. |

A feature moves up a tier only when the tier above is done and verified.

### Time budget (2 h/day)

About 14 h/week × 17 weeks ≈ 240 h. Planning assumes **~210 h** after holiday and illness losses.

| Work package | Est. hours |
|---|---|
| Setup & feasibility | 20 |
| ISA spec, ISS, assembler, UART/SPI/I2C firmware | 35 |
| RTL core + SPI host interface | 45 |
| Verification (differential, formal, BFMs, coverage) | 40 |
| FPGA bring-up + Pico loader | 20 |
| Hardening, GL sim, closure | 25 |
| Docs, writeup, demos | 15 |
| **Must subtotal** | **200** |
| Primitives (LFSR, stuffing, NRZI, capture) | 20 |
| SWD demo | 8 |
| Lightweight DSL + timing check | 20 |
| USB LS (Could) | 35 |
| Full MLIR stack (Could) | 50+ |

Must plus primitives already fills the budget. USB LS and MLIR only happen if Phase 2 finishes early.

**Working rules:**
- Plan each 2 h session the day before: one task with a testable exit condition.
- Let CI run GDS and long regressions between sessions, and review the results at the start of the next one.
- Keep a short engineering log per session; it becomes the writeup.
- Protect focus blocks for debugging and hardening; don't split them across unrelated tasks.

---

## 2. Baseline architecture (to validate, not frozen)

- **Lanes:** N identical timed state machines, with N set by area at gate G2 (expect 2–4). Lanes share program memory and each has its own PC.
- **Per-lane state:**
  - PC.
  - Two 16-bit scratch registers (X, Y).
  - In and out shift registers with configurable width, direction and autoshift.
  - A cycle timer with `WAIT_UNTIL` semantics, i.e. absolute deadlines rather than relative delays, so jitter doesn't accumulate. This is the Zqtime idea.
  - A pin base/count mapping.
- **Timebase:** a fractional clock divider per lane, giving a baud tick from the system clock.
- **Primitives per lane** (generic, not protocol blocks):
  - A programmable-polynomial LFSR, up to 16 bits in Must. Extend to 32 bits only if area allows.
  - A run-length counter for bit stuffing and destuffing.
  - Pin encode/decode modes: raw, NRZI, Manchester.
  - Edge capture with timer timestamp.
- **ISA:** 16-bit fixed-width instructions. The categories are pin I/O, shift, wait/timer, jump/branch on condition, register ops, primitive control, and FIFO push/pull.
- **Program memory:** 64–128 × 16 bit. The technology (latch RAM, DFF, or SRAM macro) is chosen at G1.
- **Host interface:** SPI slave with a register map for program load, lane control, FIFOs, status and IRQ.
  - Sample SCK/MOSI/CS with the system clock (oversampled), with no SCK-domain logic. This gives one clock domain and no CDC.
- **I/O:** 8 in, 8 out and 8 bidir. Reserve the host SPI plus an IRQ pin; the rest form the programmable pin pool.

---

## 3. Repository layout

```
rtl/        Verilog (TT template)
iss/        cycle-accurate golden model (Python)
asm/        assembler + macro library
dsl/        protocol DSL → assembly + timing check (Should tier)
programs/   protocol firmware (uart_tx.pe, i2c_master.pe, ...)
tb/         cocotb testbenches, protocol BFMs, random program generator
formal/     SymbiYosys configs + property files
fpga/       Tang Nano 20K top, constraints, build scripts
fw/         RP2040 loader/host firmware (Pico + TT demo board)
docs/       ISA spec, register map, datasheet, verification report
```

CI runs on GitHub Actions: TT GDS flow, cocotb regression, formal, and FPGA synthesis. Track cell count and slack per commit.

---

## 4. Verification strategy

1. **Golden model.** The Python ISS is cycle-accurate, because timing is part of the spec. Every RTL test compares against it.
2. **Differential random testing.** A constrained-random program generator runs each program on the RTL and the ISS, comparing architectural state and pins every cycle.
3. **Formal (SymbiYosys).**
   - Decode completeness and no illegal state.
   - The timer never misses a deadline.
   - FIFO invariants.
   - Correctness of the SPI host protocol.
   - Cover properties for every instruction and branch condition.
4. **Protocol level.** cocotb bus-functional models (cocotbext-uart/spi, own I2C and USB-LS models) run against the firmware, covering error injection: NACK, clock stretching, framing and CRC errors.
5. **Functional coverage** with cocotb-coverage, covering instruction × lane × pin-mode crosses.
6. **Gate-level simulation** of the post-PnR netlist, running a smoke subset.
7. **Hardware-in-the-loop** on the FPGA with the Pico host, a real EEPROM, SPI flash and a USB device, decoded with sigrok.
8. **DSL (Should tier):** translation validation. The DSL semantics interpreter and the ISS execution of the compiled program must produce identical pin traces.

---

## 5. Schedule

### Phase 0 — Setup & feasibility (W0–W2, 16 Sep – 4 Oct)
- Fill in the sign-up form and order the hardware.
- Install the OSS CAD Suite and Nix/Docker LibreLane on the Mac. Fork the CMOS5L template and set the tiles to 6x4.
- Take a trivial UART TX all the way to GDS in CI.
- **Measure:**
  - DFF vs latch-RAM vs SRAM area for 64×16 and 128×16.
  - Area of a minimal lane.
  - Achievable fmax.
  - Max I/O toggle rate through the TT IHP mux.
  - I/O voltage levels.
- Blinky and UART TX on the Tang Nano 20K.
- **Gate G1:** decide the memory technology, the system clock target, the HDL (Verilog by default), and 10BASE-T go/no-go.

### Phase 1 — Architecture & golden model (W3–W5, 5 – 25 Oct)
- ISA spec v0 and register map in `docs/`.
- Python ISS and assembler.
- Firmware for UART TX/RX, SPI master (4 modes) and I2C master, verified in the ISS against the Python BFMs.
- Area model: a spreadsheet of per-block cell estimates, calibrated with the G1 data.
- **Gate G2:** freeze ISA v0, lane count and memory size.

### Phase 2 — RTL core & FPGA bring-up (W6–W9, 26 Oct – 22 Nov)
- **W6:** decode, PC, registers, branches.
- **W7:** timer, divider, shift registers, FIFOs.
- **W8:** SPI host interface, program load, pin mux; Pico loader firmware.
- **W9:** differential random testing, formal harness, coverage.
- **Continuous:** weekly GDS run with area and slack trend.
- **Milestone M2 (22 Nov):** UART, SPI and I2C running on the FPGA against real parts, loaded at runtime from the Pico, with GDS passing at 6x4.

### Phase 3 — Primitives & stretch (W10–W12, 23 Nov – 13 Dec)
- Add the LFSR, stuff counter, NRZI/Manchester and edge capture, all in the ISS first, then RTL.
- **SWD demo:** read the IDCODE of a second Pico.
- **DSL (Should tier):** a Python protocol description that emits assembly, with a static check that every bit period meets its timing constraint.
- **USB low-speed (Could, only if M2 was on time):** the chip does the bit and packet layer (sync, NRZI, stuffing, CRC5/16, EOP); higher layers run on the Pico.
- **Gate G3 (13 Dec):** RTL feature freeze. Anything not verified is cut or disabled.

### Phase 4 — Hardening & signoff (W13–W15, 14 Dec – 3 Jan; reduced holiday capacity)
- Area and timing closure; gate-level simulation; clean DRC/LVS through the TT flow.
- Final lane count and memory size; tie-offs for unused features.
- DSL: translation validation on the protocol programs (DSL interpreter vs ISS pin traces).

### Phase 5 — Docs & submission (W16–W17, 4 – 17 Jan)
- Datasheet: pinout, register map, ISA reference, example programs.
- Verification report: methodology, coverage numbers, formal results, known limitations.
- Demo videos from the FPGA with logic-analyzer captures.
- Final regression. **Freeze 10 Jan, submit by 13 Jan**, keeping 5 days of buffer.

---

## 6. Risk register

| Risk | Signal | Mitigation |
|---|---|---|
| Area overrun | Cell count > 85% at any weekly GDS | Reduce lanes or memory; move LFSR to 16 bit; use 8x4 if offered |
| I/O rate ceiling | G1 measurement | Drop 10BASE-T; confirm USB LS (1.5 Mbit) margin early |
| Routing congestion / timing | Negative slack after PnR while synthesis looks fine | Lower the clock target; pipeline decode; latch-RAM placement |
| Level compatibility (USB, 3.3 V parts) | G1 voltage check | External level shifting on the dev board side |
| Solo bandwidth (2 h/day) | A milestone slips by more than a week | Hard gates; Could items dropped first, then Should; the DSL falls back to assembler + macros |
| macOS tool friction | Local flow breaks | CI is authoritative for GDS; local runs are for iteration only |

---

## 7. Submission deliverables

- Open-source repo with a passing TT GDS action (6x4, or 8x4 if available).
- ISA spec, register map, datasheet.
- Firmware for UART/SPI/I2C (+ SWD, USB LS if done).
- Host loader firmware for the RP2040.
- Verification report and CI badges.
- DSL toolchain with a timing-check demo (if done).
- Writeup: design rationale, a comparison with PIO/PRU, lessons learned.
