`timescale 1ns/1ps

// Twelve-element narrow-band receive beamformer.
//
// ADCInputI and ADCInputQ contain twelve packed signed complex samples:
// element zero occupies bits [15:0], element one [31:16], and so on.
// The coefficient ROM is a Q1.7 steering vector for the trusted look angle.
module AntennaBeamBlock #(
    parameter integer NUM_ELEMENTS       = 12,
    parameter integer SAMPLE_WIDTH       = 16,
    parameter integer COEFFICIENT_WIDTH  = 8,
    parameter integer ACCUMULATOR_WIDTH  = 32,
    parameter integer ACCEPT_THRESHOLD   = 2500000,
    parameter [7:0]   MIN_CORRELATION    = 8'd240
) (
    input  wire                                   reset,
    input  wire                                   clk,
    input  wire                                   sample_valid,
    input  wire                                   frame_valid,
    input  wire                                   auth_tag_ok,
    input  wire [7:0]                             correlation,
    input  wire [(NUM_ELEMENTS*SAMPLE_WIDTH)-1:0] ADCInputI,
    input  wire [(NUM_ELEMENTS*SAMPLE_WIDTH)-1:0] ADCInputQ,
    output reg  signed [ACCUMULATOR_WIDTH-1:0]    BeamI,
    output reg  signed [ACCUMULATOR_WIDTH-1:0]    BeamQ,
    output reg  [11:0]                            SignalFromBeam,
    output reg                                    DataAccepted
);
    localparam integer PRODUCT_WIDTH = SAMPLE_WIDTH + COEFFICIENT_WIDTH + 1;

    integer element;
    reg signed [SAMPLE_WIDTH-1:0] sample_i;
    reg signed [SAMPLE_WIDTH-1:0] sample_q;
    reg signed [ACCUMULATOR_WIDTH-1:0] next_beam_i;
    reg signed [ACCUMULATOR_WIDTH-1:0] next_beam_q;
    reg        [ACCUMULATOR_WIDTH-1:0] next_magnitude;

    // Quantised complex steering coefficients. Repetition is intentional: it
    // came from the original panel geometry and four-state phase shifters.
    function signed [COEFFICIENT_WIDTH-1:0] lobe_filter_i;
        input integer element_index;
        begin
            case (element_index % 4)
                0: lobe_filter_i =  8'sd127;
                1: lobe_filter_i =  8'sd0;
                2: lobe_filter_i = -8'sd127;
                default: lobe_filter_i = 8'sd0;
            endcase
        end
    endfunction

    function signed [COEFFICIENT_WIDTH-1:0] lobe_filter_q;
        input integer element_index;
        begin
            case (element_index % 4)
                0: lobe_filter_q =  8'sd0;
                1: lobe_filter_q = -8'sd127;
                2: lobe_filter_q =  8'sd0;
                default: lobe_filter_q = 8'sd127;
            endcase
        end
    endfunction

    // Real component of (sample_i + j*sample_q) * (weight_i + j*weight_q).
    function signed [PRODUCT_WIDTH-1:0] complex_multiply_i;
        input signed [SAMPLE_WIDTH-1:0] sample_i_value;
        input signed [SAMPLE_WIDTH-1:0] sample_q_value;
        input signed [COEFFICIENT_WIDTH-1:0] weight_i_value;
        input signed [COEFFICIENT_WIDTH-1:0] weight_q_value;
        begin
            complex_multiply_i =
                (sample_i_value * weight_i_value)
                - (sample_q_value * weight_q_value);
        end
    endfunction

    // Imaginary component of the same complex product.
    function signed [PRODUCT_WIDTH-1:0] complex_multiply_q;
        input signed [SAMPLE_WIDTH-1:0] sample_i_value;
        input signed [SAMPLE_WIDTH-1:0] sample_q_value;
        input signed [COEFFICIENT_WIDTH-1:0] weight_i_value;
        input signed [COEFFICIENT_WIDTH-1:0] weight_q_value;
        begin
            complex_multiply_q =
                (sample_i_value * weight_q_value)
                + (sample_q_value * weight_i_value);
        end
    endfunction

    function [ACCUMULATOR_WIDTH-1:0] absolute_value;
        input signed [ACCUMULATOR_WIDTH-1:0] value;
        begin
            absolute_value = value[ACCUMULATOR_WIDTH-1] ? -value : value;
        end
    endfunction

    // Complex multiply-accumulate across the full antenna aperture.
    always @* begin
        next_beam_i = {ACCUMULATOR_WIDTH{1'b0}};
        next_beam_q = {ACCUMULATOR_WIDTH{1'b0}};

        for (element = 0; element < NUM_ELEMENTS; element = element + 1) begin
            sample_i = $signed(
                ADCInputI[(element*SAMPLE_WIDTH) +: SAMPLE_WIDTH]
            );
            sample_q = $signed(
                ADCInputQ[(element*SAMPLE_WIDTH) +: SAMPLE_WIDTH]
            );
            next_beam_i = next_beam_i + complex_multiply_i(
                sample_i,
                sample_q,
                lobe_filter_i(element),
                lobe_filter_q(element)
            );
            next_beam_q = next_beam_q + complex_multiply_q(
                sample_i,
                sample_q,
                lobe_filter_i(element),
                lobe_filter_q(element)
            );
        end

        // An L1 magnitude is inexpensive and monotonic around the acceptance
        // threshold. The full signed I/Q sums remain available for analysis.
        next_magnitude = absolute_value(next_beam_i)
                       + absolute_value(next_beam_q);
    end

    always @(posedge clk or posedge reset) begin
        if (reset) begin
            BeamI          <= {ACCUMULATOR_WIDTH{1'b0}};
            BeamQ          <= {ACCUMULATOR_WIDTH{1'b0}};
            SignalFromBeam <= 12'd0;
            DataAccepted   <= 1'b0;
        end else if (sample_valid) begin
            BeamI <= next_beam_i;
            BeamQ <= next_beam_q;

            // Scale the accumulated magnitude into a compact monitor output.
            if (next_magnitude > 32'd4193280)
                SignalFromBeam <= 12'hfff;
            else
                SignalFromBeam <= next_magnitude[21:10];

            DataAccepted <= frame_valid
                         && auth_tag_ok
                         && (correlation >= MIN_CORRELATION)
                         && (next_magnitude >= ACCEPT_THRESHOLD);
        end else begin
            DataAccepted <= 1'b0;
        end
    end
endmodule
