<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

PE-16 is a reprogrammable, timing-exact coprocessor for pin-level protocols: UART, SPI and
I2C are loadable programs rather than fixed blocks, so the part stays reprogrammable after
fabrication.

**This build is the Phase 0 scaffold, not the core.** It is a minimal UART transmitter
occupying the full 6x4 target area, its job being to carry a real sequential design through
the IHP CMOS5L flow so that CI, area and timing numbers exist before the core does. It is
written under the RTL rules the core will follow: a single clock, a single synchronous
reset, all external inputs synchronised through two flip-flops, and no vendor primitives.

A rising edge on `START` latches the byte on `TXDATA` and shifts it out on `TX` as 8N1 at
`clk / 434` (115200 baud from a 50 MHz clock), LSB first. `BUSY` is high for the frame,
which is exactly 4340 clocks long, and start requests are ignored while it is high.

## How to test

Drive `clk` at 50 MHz, release `rst_n`, put a byte on `ui_in` and pulse `uio_in[0]` high for
at least four clocks. `uo_out[0]` carries the serial frame and `uo_out[1]` is busy. Any
115200 8N1 receiver, or a logic analyser with sigrok's UART decoder, will read the byte back.

`test/test.py` is the cocotb testbench: it decodes the line at bit centres like an external
receiver, checks framing for a set of byte patterns, asserts the frame is exactly 10 bit
times with no jitter, and checks that a start request mid-frame cannot corrupt the frame in
flight.

## External hardware

None required. A USB-UART adapter on `uo_out[0]` (3.3 V, 115200 8N1), or a logic analyser,
is enough to observe the output.
