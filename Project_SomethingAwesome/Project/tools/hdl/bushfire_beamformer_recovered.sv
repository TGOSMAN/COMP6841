// Recovered from the synthetic BFR-8 receive-gate image.
// Signal names were reconstructed from fan-out and register use.
module bfr8_rx_gate (
    input  logic       clk,
    input  logic       reset_n,
    input  logic       frame_valid,
    input  logic       auth_tag_ok,
    input  logic [4:0] arrival_bin,
    input  logic [7:0] correlation,
    output logic [7:0] array_gain,
    output logic       data_accept
);
    localparam logic [7:0] MIN_CORRELATION = 8'd240;
    localparam logic [7:0] TRUST_VECTOR    = 8'b10_11_00_10;

    logic [7:0] phase_signature;

    // Two-bit phase shifters from an eight-element, half-wavelength ULA were
    // reduced to this 32-bin ROM by synthesis.
    always_comb begin
        unique case (arrival_bin)
            5'd0:  begin phase_signature = 8'b10_11_00_10; array_gain = 8'd255; end
            5'd1:  begin phase_signature = 8'b10_11_00_10; array_gain = 8'd243; end
            5'd2:  begin phase_signature = 8'b10_11_01_10; array_gain = 8'd211; end
            5'd3:  begin phase_signature = 8'b10_10_01_11; array_gain = 8'd168; end
            5'd4:  begin phase_signature = 8'b10_10_01_11; array_gain = 8'd119; end
            5'd5:  begin phase_signature = 8'b01_10_01_11; array_gain = 8'd74;  end
            5'd6:  begin phase_signature = 8'b01_10_01_00; array_gain = 8'd43;  end
            5'd7:  begin phase_signature = 8'b01_10_01_00; array_gain = 8'd32;  end
            5'd8:  begin phase_signature = 8'b01_01_10_00; array_gain = 8'd51;  end
            5'd9:  begin phase_signature = 8'b00_01_10_00; array_gain = 8'd104; end
            5'd10: begin phase_signature = 8'b10_11_00_10; array_gain = 8'd226; end
            5'd11: begin phase_signature = 8'b10_11_00_10; array_gain = 8'd247; end
            5'd12: begin phase_signature = 8'b10_11_01_10; array_gain = 8'd214; end
            5'd13: begin phase_signature = 8'b10_10_01_11; array_gain = 8'd151; end
            5'd14: begin phase_signature = 8'b01_10_01_11; array_gain = 8'd87;  end
            5'd15: begin phase_signature = 8'b01_10_01_00; array_gain = 8'd39;  end
            5'd16: begin phase_signature = 8'b01_01_10_00; array_gain = 8'd24;  end
            5'd17: begin phase_signature = 8'b01_10_01_00; array_gain = 8'd39;  end
            5'd18: begin phase_signature = 8'b01_10_01_11; array_gain = 8'd87;  end
            5'd19: begin phase_signature = 8'b10_10_01_11; array_gain = 8'd151; end
            5'd20: begin phase_signature = 8'b10_11_01_10; array_gain = 8'd214; end
            5'd21: begin phase_signature = 8'b10_11_00_10; array_gain = 8'd247; end
            5'd22: begin phase_signature = 8'b10_11_00_10; array_gain = 8'd226; end
            5'd23: begin phase_signature = 8'b00_01_10_00; array_gain = 8'd104; end
            5'd24: begin phase_signature = 8'b01_01_10_00; array_gain = 8'd51;  end
            5'd25: begin phase_signature = 8'b01_10_01_00; array_gain = 8'd32;  end
            5'd26: begin phase_signature = 8'b01_10_01_00; array_gain = 8'd43;  end
            5'd27: begin phase_signature = 8'b01_10_01_11; array_gain = 8'd74;  end
            5'd28: begin phase_signature = 8'b10_10_01_11; array_gain = 8'd119; end
            5'd29: begin phase_signature = 8'b10_10_01_11; array_gain = 8'd168; end
            5'd30: begin phase_signature = 8'b10_11_01_10; array_gain = 8'd211; end
            default: begin phase_signature = 8'b10_11_00_10; array_gain = 8'd243; end
        endcase
    end

    // Design note in the recovered image: "vector match identifies trusted
    // sector". No independent angle-of-arrival bound survives synthesis.
    always_ff @(posedge clk or negedge reset_n) begin
        if (!reset_n)
            data_accept <= 1'b0;
        else
            data_accept <= frame_valid
                        && auth_tag_ok
                        && (phase_signature == TRUST_VECTOR)
                        && (correlation >= MIN_CORRELATION)
                        && (array_gain >= MIN_CORRELATION);
    end
endmodule
