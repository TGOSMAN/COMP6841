`timescale 1ns/1ps

module AntennaBeamBlock_tb;
    localparam integer ELEMENTS = 12;
    localparam integer WIDTH = 16;
    localparam integer ANGLE_BINS = 32;
    localparam integer SPATIAL_STRIDE = 4;
    localparam integer SAMPLE_AMPLITUDE = 2048;

    reg reset = 1'b1;
    reg clk = 1'b0;
    reg sample_valid = 1'b0;
    reg frame_valid = 1'b1;
    reg auth_tag_ok = 1'b1;
    reg [7:0] correlation = 8'hff;
    reg [(ELEMENTS*WIDTH)-1:0] adc_i = 0;
    reg [(ELEMENTS*WIDTH)-1:0] adc_q = 0;
    wire signed [31:0] beam_i;
    wire signed [31:0] beam_q;
    wire [11:0] signal_from_beam;
    wire data_accepted;

    integer angle_bin;
    integer element;
    integer integer_i;
    integer integer_q;
    real phase;

    AntennaBeamBlock dut (
        .reset(reset),
        .clk(clk),
        .sample_valid(sample_valid),
        .frame_valid(frame_valid),
        .auth_tag_ok(auth_tag_ok),
        .correlation(correlation),
        .ADCInputI(adc_i),
        .ADCInputQ(adc_q),
        .BeamI(beam_i),
        .BeamQ(beam_q),
        .SignalFromBeam(signal_from_beam),
        .DataAccepted(data_accepted)
    );

    always #5 clk = ~clk;

    task load_arrival_bin;
        input integer selected_bin;
        begin
            for (element = 0; element < ELEMENTS; element = element + 1) begin
                phase = 2.0 * 3.141592653589793
                      * SPATIAL_STRIDE * selected_bin * element
                      / ANGLE_BINS;
                integer_i = $rtoi(SAMPLE_AMPLITUDE * $cos(phase));
                integer_q = $rtoi(SAMPLE_AMPLITUDE * $sin(phase));
                adc_i[(element*WIDTH) +: WIDTH] = integer_i[WIDTH-1:0];
                adc_q[(element*WIDTH) +: WIDTH] = integer_q[WIDTH-1:0];
            end
        end
    endtask

    initial begin
        repeat (2) @(posedge clk);
        reset = 1'b0;
        sample_valid = 1'b1;

        for (angle_bin = 0; angle_bin < ANGLE_BINS; angle_bin = angle_bin + 1) begin
            load_arrival_bin(angle_bin);
            @(posedge clk);
            #1 $display(
                "bin=%0d beam_i=%0d beam_q=%0d magnitude=%0d accepted=%0d",
                angle_bin,
                beam_i,
                beam_q,
                signal_from_beam,
                data_accepted
            );
        end

        $finish;
    end
endmodule
