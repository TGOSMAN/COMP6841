`timescale 1ns/1ps

module bushfire_beamformer_tb;
    logic clk = 0;
    logic reset_n = 0;
    logic frame_valid = 0;
    logic auth_tag_ok = 1;
    logic [4:0] arrival_bin = 0;
    logic [7:0] correlation = 8'hff;
    logic [7:0] array_gain;
    logic data_accept;
    integer bin;

    bfr8_rx_gate dut (
        .clk, .reset_n, .frame_valid, .auth_tag_ok, .arrival_bin,
        .correlation, .array_gain, .data_accept
    );

    always #5 clk = ~clk;

    initial begin
        #12 reset_n = 1;
        for (bin = 0; bin < 32; bin = bin + 1) begin
            arrival_bin = bin[4:0];
            frame_valid = 1;
            @(posedge clk);
            #1 $display("bin=%0d gain=%0d accepted=%0d",
                        arrival_bin, array_gain, data_accept);
        end
        $finish;
    end
endmodule
