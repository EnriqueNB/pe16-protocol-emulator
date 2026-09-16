# PE-16 Instruction Set Architecture — Draft v0

Status: **draft for discussion**. Every parameter marked ⚙ is to be fixed at gate G2, after the G1 area measurements.

---

## 1. Design principles

1. **Timing is semantics.** Every instruction has a fixed, known cycle cost, so a program's timing can be checked statically.
2. **Absolute deadlines, full-speed execution.** Lanes run one instruction per system clock cycle. Bit timing comes from a free-running per-lane *tick grid*, not from slowing execution down (unlike RP2040 PIO's clock divider). Instructions between two waits never accumulate drift.
3. **Primitives expose events; programs make decisions.** CRC, bit stuffing and line coding are generic hardware helpers. Anything that changes the waveform (e.g. inserting a stuff bit) is an explicit program action, so it stays visible to the timing checker.
4. **No protocol knowledge in silicon.** Nothing in the ISA names UART, SPI or I2C.
5. **Everything large lives in host-written config tables** (baud increments, CRC polynomials), selected by small indices from instructions.

---

## 2. Lane model

A chip has **N lanes** (⚙ 2–4) sharing one program memory (⚙ 128 × 16 bit; 7-bit addresses).

### 2.1 Architectural state per lane

| Name | Width | Description |
|---|---|---|
| `PC` | 7 | Program counter |
| `RA` | 7 | Return address (single level) |
| `X`, `Y` | 16 ⚙ | Scratch registers |
| `OSR` + `ocnt` | 16 + 5 | Output shift register and remaining bit count |
| `ISR` + `icnt` | 16 + 5 | Input shift register and received bit count |
| `LEN` | 5 | ISR full threshold, and bit count for `MOV → OSR` (1–16) |
| `T` | 16 | Down-counting timer, decrements every cycle while nonzero |
| `CAP` | 16 | Free-running cycle counter value latched on a watched edge |
| `LFSR` | 16 ⚙ | CRC register; polynomial and seed come from a host profile |
| `F` | 1 | Flag: last bit shifted or sampled |
| `ACC` | 24 | Tick-grid phase accumulator |
| Line config | ~20 | Coding mode, open-drain mask, stuff config, edge watch, baud and CRC profile selects |
| Sticky flags | 4 | `EDGE`, `STUFF`, `OVF`, `SIG` |

### 2.2 Pins

Each lane sees an **8-pin window** starting at a host-configured base in the chip's pin pool. Pins are addressed as `p0`–`p7` relative to that window.

A pin in the lane's **open-drain mask** never drives high: writing 1 releases it (hi-Z), and the external pull-up does the rest. Reading a pin always returns the actual pad level, including while driving.

### 2.3 Host FIFOs

Each lane has a TX FIFO (host → lane) and an RX FIFO (lane → host).
- Each entry is **16 data bits plus a 4-bit tag** (⚙ depth 4).
- Tags carry status to the host, e.g. `NACK` or `FRAMING`.

---

## 3. Time model

- **R1.** Every instruction except `WAIT`, and blocking FIFO operations, takes **exactly 1 cycle**.
- **R2.** The tick grid: each cycle, `ACC += INC[baud]` (mod 2²⁴).
  - A **TICK** event fires when `ACC` wraps.
  - A **HALF** event fires when `ACC[23]` rises.
  - So the period is P = 2²⁴ / INC cycles, and HALF events sit exactly P/2 after each TICK.
- **R3.** A `WAIT` finishes on the cycle its event occurs; the next instruction runs on the following cycle. Therefore **an instruction placed k instructions after a wait executes at event + k cycles**, with no jitter.
- **R4.** **Sync** (the `WAIT` sync flag or `CTRL SYNC`) sets `ACC ← 0` when the event happens. The next TICK is then at +P and the next HALF at +P/2. This anchors the grid to an external edge, e.g. a UART start bit or I2C clock stretching.

**Static timing obligation** (what the DSL checker proves): for every path between two consecutive tick/half waits, the instruction count must be less than the event spacing, and every pin write must land at a constant offset from its event.

**Throughput bound:** a bit loop of c instructions needs P ≥ c. At f_sys = 24 MHz, USB low speed (1.5 Mbit/s) gives P = 16 cycles, far more than any loop needs. The practical limit is the pad and I/O path, measured at G1.

---

## 4. Encoding

Instructions are 16 bits, with the opcode in `[15:12]`.

| Op | Mnemonic | Layout (`[11:0]`) |
|---|---|---|
| 0 | `JMP` | `inv[11] cond[10:7] addr[6:0]` |
| 1 | `WAIT` | `kind[11:9] sync[8] arg[7:0]` |
| 2 | `PIN` | `mode[11:9] – mask[7:0]` |
| 3 | `OUT` | `dst[11:9] n-1[8:5] pin[4:2] crc[1] stuff[0]` |
| 4 | `IN` | `src[11:9] n-1[8:5] pin[4:2] crc[1] stuff[0]` |
| 5 | `FIFO` | `kind[11:10] nb[9] n-1[8:5] clr[4] tag[3:0]` |
| 6 | `SET` | `reg[11:8] imm[7:0]` |
| 7 | `MOV` | `dst[11:8] src[7:4] op[3:0]` |
| 8 | `CALL`/`RET` | `ret[11] – addr[6:0]` |
| 9 | `CTRL` | `kind[11:8] arg[7:0]` |
| A–F | reserved | Kept for Should/Could extensions |

### 4.1 `JMP` conditions

If `inv` is set, the condition is negated. `JMP !ALWAYS` is the canonical NOP.

| # | Cond | True when |
|---|---|---|
| 0 | `ALWAYS` | always |
| 1 | `F` | F = 1 |
| 2 | `XZ` | X = 0 |
| 3 | `YZ` | Y = 0 |
| 4 | `XEQY` | X = Y |
| 5 | `OSRE` | `ocnt` = 0 |
| 6 | `ISRF` | `icnt` = `LEN` |
| 7 | `TXE` | TX FIFO empty |
| 8 | `RXF` | RX FIFO full |
| 9 | `TDONE` | T = 0 |
| 10 | `EDGE` | sticky edge flag set |
| 11 | `STUFF` | TX: stuff bit due / RX: stuff error |
| 12 | `XDEC` | X ≠ 0 (then X ← X − 1) |
| 13 | `YDEC` | Y ≠ 0 (then Y ← Y − 1) |
| 14 | `USER` | host control bit set |
| 15 | `SIG` | signal from another lane pending |

### 4.2 `WAIT` kinds

| # | Kind | Completes when |
|---|---|---|
| 0 | `TICK` | next TICK event |
| 1 | `HALF` | next HALF event |
| 2 | `TIMER` | T = 0 |
| 3 | `EDGE` | watched edge: `arg[2:0]` pin, `arg[4:3]` = rise / fall / any |
| 4 | `LEVEL` | pin `arg[2:0]` reads `arg[3]` |
| 5 | `CYCLES` | `arg + 1` cycles elapsed (static cost) |
| 6 | `TXNE` | TX FIFO not empty |
| 7 | `SIG` | lane signal `arg[1:0]` received |

The `sync` flag applies R4 at completion. `EDGE` also latches `CAP`.

### 4.3 `PIN` modes (applied to all pins in `mask` simultaneously)

| # | Mode | Effect |
|---|---|---|
| 0 | `LOW` | drive 0 |
| 1 | `HIGH` | drive 1 (release, if open-drain) |
| 2 | `HIZ` | release |
| 3 | `TOGGLE` | invert the driven value |
| 4 | `EQF` | drive F |
| 5 | `NEQF` | drive ¬F |
| 6 | `SAMPLE` | F ← OR of the masked input levels |
| 7 | — | reserved |

`SAMPLE` with a two-pin mask gives SE0 detection (both lines low ⇒ F = 0) in one instruction.

### 4.4 `OUT` / `IN`

`OUT` shifts n bits from `OSR` to the destination and sets F to the last *data* bit (before line coding). `IN` shifts n bits from the source into `ISR` and sets F to the last *decoded* bit. The shift order is set by `LINE[3]`.

| # | `OUT` dst | `IN` src |
|---|---|---|
| 0 | `PIN`: pins `pin`..`pin+n−1` in parallel; line coding applies when n = 1 | `PIN` |
| 1 | `F` | `F` |
| 2 | `X` | `X` |
| 3 | `Y` | `Y` |
| 4 | `NULL` (discard) | `ZERO` |
| 5 | `DIFF`: 1 bit to `pin` / `pin+1` as a complementary pair, coded (USB J/K) | `DIFF`: decoded from the pair |
| 6 | `STUFFBIT`: emit the stuff bit through the coder, without consuming OSR | — |
| 7 | reserved | reserved |

- **`crc` flag:** each bit also clocks the LFSR.
- **`stuff` flag, `OUT`:** each bit updates the run counter. When the run reaches the threshold, `STUFF` is set; the program then waits a tick and emits `OUT STUFFBIT`.
- **`stuff` flag, `IN`:** a bit that follows a completed run is *discarded* (not shifted, `icnt` unchanged). If it has the wrong value, `STUFF` is set as an error.

### 4.5 `FIFO`

| kind | Operation |
|---|---|
| 0 | `PULL` → `OSR`, with `ocnt` ← n |
| 1 | `PUSH` ← `ISR`, with `tag`; `icnt` ← 0 |
| 2 | `PULL` → `X` |
| 3 | `PUSH` ← `X`, with `tag` |

- **Blocking by default.** With `nb` set: a PULL on an empty FIFO sets F ← 0 and changes nothing (F ← 1 on success); a PUSH on a full FIFO drops the entry and sets `OVF`.
- **`clr`:** zero the source register after a push.

### 4.6 `SET` registers (8-bit immediate)

| # | Reg | Effect |
|---|---|---|
| 0 / 1 | `XL` / `XH` | X ← imm / X[15:8] ← imm |
| 2 / 3 | `YL` / `YH` | same for Y |
| 4 / 5 | `TL` / `TH` | T ← imm / T[15:8] ← imm |
| 6 | `LEN` | 1–16 |
| 7 | `BAUD` | select INC profile 0–3 |
| 8 | `CRC` | select profile 0–1 and load its seed |
| 9 | `LINE` | [1:0] raw / NRZI / Manchester, [2] invert, [3] MSB-first |
| 10 | `OD` | open-drain mask |
| 11 | `STUFFCFG` | [2:0] threshold, [3] mode (0 = ones only, 1 = any identical run) |
| 12 | `IRQ` | raise a host interrupt with code imm |
| 13 | `SIG` | signal lane(s) imm[3:0] |
| 14 | `EDGEW` | edge watch: [2:0] pin, [4:3] polarity |
| 15 | reserved | |

### 4.7 `MOV`

Performs `dst ← dst op src`, or `dst ← op(src)` for unary ops.

- **Operands:**
  - 0 `X`, 1 `Y`, 2 `OSR` (as destination, also sets `ocnt ← LEN`), 3 `ISR`
  - 4 `LFSR`, 5 `T`, 6 `CAP`, 7 `F` (zero-extended)
  - 8 `ZERO`, 9 `ONES`
- **Ops:**
  - Unary: 0 copy, 1 not, 2 bit-reverse (over `LEN` bits), 8 shl1, 9 shr1.
  - Binary: 3 add, 4 sub, 5 xor, 6 and, 7 or.

### 4.8 `CTRL`

| # | Kind | Effect |
|---|---|---|
| 0 | `NOP` | none |
| 1 | `HALT` | stop the lane and notify the host |
| 2 | `CRCCHK` | F ← (LFSR = profile residue) |
| 3 | `SYNC` | apply R4 now |
| 4 | `CLR` | clear sticky flags in `arg` |
| 5 | `CAPT` | latch the free-running counter into `CAP` |

---

## 5. Host-side configuration

These registers are written over SPI and are not part of the instruction stream.

- **Per lane:** enable, start PC, pin-window base, and the `USER` bit.
- **Shared tables:**
  - `INC[0..3]` (24 bit each).
  - CRC profiles `[0..1]`, each with width, polynomial, seed, residue and reflect flag.
- **Program memory:** load, then verify by reading it back.
- **Status and IRQ:** halted lanes, `OVF`, IRQ codes.

---

## 6. Example programs

All pin writes land at event + 1 (see R3).

### 6.1 UART TX (`p0` = TX)

```
        set   baud, 0
idle:   pin   high, p0
        pull  osr, 8            ; blocks until the host sends a byte
        wait  tick
        pin   low, p0           ; start bit       @tick+1
bit:    wait  tick
        out   pin p0, 1         ; data bit        @tick+1
        jmp   !osre, bit
        wait  tick
        pin   high, p0          ; stop bit        @tick+1
        wait  tick
        jmp   idle
```

### 6.2 UART RX (`p1` = RX)

```
        set   len, 8
rx:     wait  edge p1 fall, sync   ; anchor the grid to the start edge
        wait  half                 ; middle of the start bit
        pin   sample, p1
        jmp   f, rx                ; line is high again: glitch, restart
bit:    wait  half                 ; middle of the next data bit
        in    pin p1, 1
        jmp   !isrf, bit
        wait  half                 ; middle of the stop bit
        pin   sample, p1
        jmp   !f, ferr
        push  isr
        jmp   rx
ferr:   push  isr, tag=FRAMING
        jmp   rx
```

### 6.3 I2C write, one byte with ACK (`p0` = SCL, `p1` = SDA)

```
        set   od, 0b11             ; both lines open-drain
        pull  osr, 8
wbit:   out   pin p1, 1            ; SDA changes while SCL is low
        wait  tick
        pin   high, p0             ; release SCL
        wait  level p0 high, sync  ; clock stretching; re-anchor the grid
        wait  tick
        pin   low, p0
        jmp   !osre, wbit
        pin   high, p1             ; release SDA for the ACK bit
        wait  tick
        pin   high, p0
        wait  level p0 high, sync
        pin   sample, p1           ; ACK = low
        wait  tick
        pin   low, p0
        jmp   f, nack
```

### 6.4 USB low-speed TX inner loop (`p0`/`p1` = D−/D+ pair)

```
        set   line, NRZI
        set   stuffcfg, 6          ; stuff after six ones
bit:    wait  tick
        out   diff p0, 1, crc, stuff
        jmp   !stuff, next
        wait  tick
        out   stuffbit p0          ; inserted bit, explicit and timed
next:   jmp   !osre, bit
```

---

## 7. Comparison with RP2040 PIO

| | PIO | PE-16 v0 |
|---|---|---|
| Timing | Clock divider slows execution; delays per instruction | Full-speed execution against an absolute tick grid; statically checkable |
| Program memory | 32 instructions | 128 ⚙ |
| Arithmetic | Decrement and compare only | Add, sub, logic, compare |
| CRC / stuffing / line coding | None (done in software or impossible) | Generic hardware primitives |
| Differential and open-drain | Awkward | `DIFF`, open-drain mask, multi-pin simultaneous writes |
| Subroutines | None | One-level `CALL`/`RET` |
| Edge timestamps | None | `CAP` latched on edge |

---

## 8. Rough area (to calibrate at G1)

- **Per lane:** ~250 flip-flops plus datapath and decode, roughly **1.5–2.5 K cells**.
- **Program memory:** 128×16 latch RAM with read mux, roughly **3–4 K cells**. Halves at 64 words.
- **Shared tables, FIFOs, SPI host interface and control:** roughly **2–3 K cells**.
- **Three lanes: ~12–14 K cells**, about 55% of the nominal 24 K. This leaves headroom for routing and clock tree.

---

## 9. Open decisions for G2

1. Number of lanes (2 / 3 / 4).
2. Program memory depth (64 vs 128); 256 words would need a wider JMP address field.
3. X/Y and shift-register width (16 vs 8 bits). This trades area against SWD/JTAG, which use 32-bit words and would need chaining.
4. LFSR width: 16 bits covers CRC5, CRC15 and CRC16; CRC32 for Ethernet needs 32.
5. Whether Manchester coding earns its area if 10BASE-T is dropped.
6. Multi-level call stack vs a single return address.
