# Engineering log

## 2026-09-17 — Phase 0.2: scaffold to 6x4, real tests

**Done**

- Dev container up (amd64 pinned, 4 GB). Toolchain present: iverilog, verilator, cocotb
  2.0.1, klayout, yowasp-yosys 0.55, LibreLane 3.0.0.dev44 in `/ttsetup/venv`. PDK not
  downloaded locally; CI stays authoritative for GDS.
- Replaced the template example with `src/tt_um_pe16.v` (`tt_um_enb7395_pe16`): a minimal
  UART TX written under the core's RTL rules — one clock, one sync reset, 2FF input
  synchronisers, no vendor primitives, no `initial` state. `CLKS_PER_BIT = 434` is a
  default, never overridden by the testbench, so RTL and gate-level sim agree.
- `test/test.py`: four cocotb tests that decode the line at bit centres like an external
  receiver — reset/idle state, byte patterns incl. 0x00/0xFF, exact frame length
  (10 x 434 clocks, no jitter), and start-ignored-while-busy. 4/4 pass.
- Verified the tests are not vacuous by hand-mutating the RTL: reversing the shift
  direction kills `test_transmit_bytes` + `test_start_ignored_while_busy`; shortening the
  frame by one bit kills `test_frame_length_is_exact`. Both mutants caught, RTL restored.
- `info.yaml` at `tiles: "6x4"`, `clock_hz: 50000000`, real pinout. `docs/info.md`
  rewritten as a datasheet for the scaffold.
- `python tt/tt_tool.py --ihp --create-user-config` produces the right config:
  `DIE_AREA 0 0 1289.28 710.64`, `tt_block_6x4_pgvdd.def`, `RT_MAX_LAYER TopMetal1`.
- Gitignored `/tt` (it is a copy of tt-support-tools dropped in by the container's
  `postStartCommand`, not project source). Fixed the `tt/` collision in the layout section
  of `CLAUDE.md`: the TT top lives in `src/`.

**Numbers (first data point for the area model)**

- Generic yosys synth of the scaffold: 114 cells, 42 flops, 72 combinational.
- 6x4 die at IHP: 1289.28 x 710.64 um = 0.916 mm^2. The scaffold fills ~0.5% of it.

**Next**

- Push and confirm the four workflows are green, gds in particular. Record cell count and
  slack from the GDS run as the Phase 0 baseline.
- Then Phase 0.3: the real measurements — DFF vs latch-RAM vs SRAM area at 64x16 and
  128x16, minimal-lane area, fmax, TT IHP mux max toggle rate, I/O voltage.

**Open issues**

- Untested: whether LibreLane is happy placing 114 cells in a 6x4 die (~0.5% utilisation).
  If it trips on near-empty floorplans, either pad the scaffold or drop to a smaller tile
  count until the core has real logic.
- `tt_tool.py` defaults to sky130A when `--ihp` is omitted, silently emitting a wrong die
  area. Always pass `--ihp`.
- 4 GB container RAM rules out local LibreLane comfortably; the Phase 0 area/fmax sweeps
  may need CI or a bigger machine.
