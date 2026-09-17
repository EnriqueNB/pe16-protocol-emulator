# Phase 0 scaffold tests: decode the UART TX scaffold at pin level.
#
# These are deliberately not smoke tests. They decode the serial line the way
# an external receiver would and check the bit grid exactly, because the whole
# point of PE-16 is timing exactness -- the test methodology starts here.
#
# SPDX-FileCopyrightText: © 2025 Enrique NB
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, Timer

CLK_NS = 20  # 50 MHz
CLKS_PER_BIT = 434  # must match the RTL default (50 MHz / 115200 baud)
BIT_NS = CLK_NS * CLKS_PER_BIT

TX_BIT = 0
BUSY_BIT = 1

START_PIN = 0


def tx(dut):
    return (int(dut.uo_out.value) >> TX_BIT) & 1


def busy(dut):
    return (int(dut.uo_out.value) >> BUSY_BIT) & 1


async def reset(dut):
    clock = Clock(dut.clk, CLK_NS, unit="ns")
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)


async def send(dut, byte):
    """Present a byte and pulse start. Returns once the frame has begun."""
    dut.ui_in.value = byte
    dut.uio_in.value = 1 << START_PIN
    # 2FF synchroniser + edge detect, then the load cycle.
    await ClockCycles(dut.clk, 4)
    dut.uio_in.value = 0
    while busy(dut) == 0:
        await FallingEdge(dut.clk)


async def receive(dut):
    """Decode one frame from the TX line, sampling at bit centres.

    Must be called while the start bit is on the line. Returns the byte.
    """
    assert tx(dut) == 0, "receive() called outside a start bit"

    # We are somewhere inside the start bit. Realign to its falling edge by
    # measuring from the cycle busy went high, which is the same cycle: the
    # caller guarantees we are at most a few clocks in, so step to the next
    # bit centre conservatively.
    await Timer(BIT_NS + BIT_NS // 2, unit="ns")

    byte = 0
    for i in range(8):
        byte |= tx(dut) << i
        await Timer(BIT_NS, unit="ns")

    assert tx(dut) == 1, f"framing error: stop bit low for byte 0x{byte:02X}"
    return byte


@cocotb.test()
async def test_reset_state(dut):
    """After reset the line idles high, nothing is driven on the uio bus."""
    await reset(dut)

    assert tx(dut) == 1, "TX must idle high out of reset"
    assert busy(dut) == 0, "busy must be low out of reset"
    assert int(dut.uio_oe.value) == 0, "uio pins must all be inputs"
    assert int(dut.uio_out.value) == 0

    # Still idle after a while with no start request.
    await ClockCycles(dut.clk, 1000)
    assert tx(dut) == 1
    assert busy(dut) == 0


@cocotb.test()
async def test_transmit_bytes(dut):
    """Bytes come out LSB-first with correct start and stop bits."""
    await reset(dut)

    for value in (0x00, 0xFF, 0x55, 0xA3, 0x01, 0x80):
        await send(dut, value)
        got = await receive(dut)
        assert got == value, f"sent 0x{value:02X}, received 0x{got:02X}"

        # Line returns to idle and the transmitter reports done.
        while busy(dut) == 1:
            await FallingEdge(dut.clk)
        assert tx(dut) == 1
        await ClockCycles(dut.clk, 20)


@cocotb.test()
async def test_frame_length_is_exact(dut):
    """A frame is exactly 10 bit times of CLKS_PER_BIT clocks. No jitter."""
    await reset(dut)

    for value in (0x00, 0xFF, 0x96):
        dut.ui_in.value = value
        dut.uio_in.value = 1 << START_PIN

        cycles = 0
        while busy(dut) == 0:
            await FallingEdge(dut.clk)
        dut.uio_in.value = 0

        while busy(dut) == 1:
            await FallingEdge(dut.clk)
            cycles += 1

        expected = 10 * CLKS_PER_BIT
        assert cycles == expected, (
            f"byte 0x{value:02X}: frame took {cycles} clocks, expected {expected}"
        )
        await ClockCycles(dut.clk, 20)


@cocotb.test()
async def test_start_ignored_while_busy(dut):
    """A start request mid-frame must not corrupt the frame in flight."""
    await reset(dut)

    await send(dut, 0x3C)

    # Hammer start with a different byte while the frame is on the wire.
    async def interfere():
        for _ in range(6):
            dut.ui_in.value = 0xF0
            dut.uio_in.value = 1 << START_PIN
            await ClockCycles(dut.clk, 100)
            dut.uio_in.value = 0
            await ClockCycles(dut.clk, 100)

    cocotb.start_soon(interfere())

    got = await receive(dut)
    assert got == 0x3C, f"frame corrupted by mid-frame start: got 0x{got:02X}"
