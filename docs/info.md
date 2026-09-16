<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

This is the unmodified Tiny Tapeout IHP CMOS5L template scaffold, kept as-is to get the
6x4 GDS/docs CI flow green before the real PE-16 RTL lands. `src/project.v` (`tt_um_example`)
is an 8-bit adder: `uo_out = ui_in + uio_in`, with `uio_out`/`uio_oe` tied low (all `uio`
pins are inputs only). The actual PE-16 reprogrammable protocol-emulator core will replace
this stub once the RTL (`rtl/core/`) and Tiny Tapeout top (`tt/tt_um_pe.v`) are in place.

## How to test

Drive `ui_in` and `uio_in` with two 8-bit operands and check that `uo_out` equals their sum
one clock cycle later. See `test/test.py` for the cocotb testbench (e.g. `ui_in=20`,
`uio_in=30` after reset should yield `uo_out=50`).

## External hardware

List external hardware used in your project (e.g. PMOD, LED display, etc), if any
