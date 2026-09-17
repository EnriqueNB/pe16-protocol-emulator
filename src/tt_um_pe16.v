/*
 * PE-16 Protocol Emulator ASIC -- Phase 0 scaffold.
 *
 * This is NOT the PE-16 core. It is a minimal UART transmitter whose only job
 * is to carry a real, non-trivial sequential design through the Tiny Tapeout
 * IHP flow at 6x4 so that CI, area and timing numbers mean something before
 * the core exists. It is written under the same RTL rules as the core will be:
 * one clock, one synchronous reset, all external inputs 2FF-synchronised, no
 * vendor primitives, no `initial` state, no `ifdef`.
 *
 * Copyright (c) 2025 Enrique NB
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_enb7395_pe16 #(
    // 50 MHz / 115200 baud. Not overridden by the testbench: the gate-level
    // netlist has no parameters, so RTL and GL sim must agree on the default.
    parameter integer CLKS_PER_BIT = 434
) (
    input  wire [7:0] ui_in,    // Dedicated inputs:  TX data byte
    output wire [7:0] uo_out,   // Dedicated outputs: [0] serial TX, [1] busy
    input  wire [7:0] uio_in,   // IOs: Input path:   [0] start
    output wire [7:0] uio_out,  // IOs: Output path (unused, driven low)
    output wire [7:0] uio_oe,   // IOs: Enable path (all inputs)
    input  wire       ena,      // always 1 when powered
    input  wire       clk,      // clock
    input  wire       rst_n     // synchronous reset, active low
);

  localparam integer DIV_W = $clog2(CLKS_PER_BIT);

  // -- Input synchronisers --------------------------------------------------
  // Every external input crosses into the clock domain through 2 flip-flops.
  reg [7:0] data_meta, data_sync;
  reg start_meta, start_sync, start_q;

  always @(posedge clk) begin
    if (!rst_n) begin
      data_meta  <= 8'h00;
      data_sync  <= 8'h00;
      start_meta <= 1'b0;
      start_sync <= 1'b0;
      start_q    <= 1'b0;
    end else begin
      data_meta  <= ui_in;
      data_sync  <= data_meta;
      start_meta <= uio_in[0];
      start_sync <= start_meta;
      start_q    <= start_sync;
    end
  end

  // Rising edge of the synchronised start request.
  wire start_pulse = start_sync & ~start_q;

  // -- Transmitter ----------------------------------------------------------
  // shreg holds {stop, data[7:0], start} and shifts LSB-first, filling with
  // idle 1s, so shreg[0] is the line level at all times -- including at reset
  // and after the stop bit -- and needs no output mux.
  reg [      9:0] shreg;
  reg [      3:0] bitcnt;
  reg [DIV_W-1:0] divcnt;
  reg             busy;

  always @(posedge clk) begin
    if (!rst_n) begin
      shreg  <= 10'h3FF;
      bitcnt <= 4'd0;
      divcnt <= {DIV_W{1'b0}};
      busy   <= 1'b0;
    end else if (!busy) begin
      if (start_pulse) begin
        shreg  <= {1'b1, data_sync, 1'b0};
        bitcnt <= 4'd10;
        divcnt <= CLKS_PER_BIT - 1;
        busy   <= 1'b1;
      end
    end else if (divcnt == {DIV_W{1'b0}}) begin
      shreg  <= {1'b1, shreg[9:1]};
      bitcnt <= bitcnt - 4'd1;
      divcnt <= CLKS_PER_BIT - 1;
      busy   <= (bitcnt != 4'd1);
    end else begin
      divcnt <= divcnt - 1'b1;
    end
  end

  assign uo_out  = {6'b0, busy, shreg[0]};
  assign uio_out = 8'h00;
  assign uio_oe  = 8'h00;

  // List all unused inputs to prevent warnings
  wire _unused = &{ena, uio_in[7:1], 1'b0};

endmodule
