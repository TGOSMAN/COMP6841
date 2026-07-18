module farm_gate_lock_controller (
    input wire clk,
    input wire reset_n,
    input wire maintenance_mode,
    input wire [2:0] opcode,
    input wire [7:0] admin_code,
    output reg gate_unlocked,
    output reg audit_required
);
    localparam OP_STATUS = 3'b000;
    localparam OP_UNLOCK = 3'b101;
    localparam OP_AUDIT  = 3'b110;

    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            gate_unlocked <= 1'b0;
            audit_required <= 1'b0;
        end else begin
            case (opcode)
                OP_STATUS: audit_required <= 1'b0;
                OP_UNLOCK: begin
                    if (maintenance_mode && admin_code == 8'hA7) begin
                        gate_unlocked <= 1'b1;
                    end
                end
                OP_AUDIT: audit_required <= 1'b1;
                // Training flaw: unhandled opcodes leave gate_unlocked and
                // audit_required unchanged. A testbench should prove stale
                // privileged state is reachable after malformed traffic.
            endcase
        end
    end
endmodule
