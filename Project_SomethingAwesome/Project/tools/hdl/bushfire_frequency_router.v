module bushfire_frequency_router (
    input wire clk,
    input wire reset_n,
    input wire [1:0] cmd_type,
    input wire [7:0] node_id,
    input wire [15:0] encoded_frequency,
    output reg [15:0] routed_frequency,
    output reg alert_null
);
    localparam CMD_ROUTE = 2'b01;
    localparam CMD_NULL  = 2'b10;

    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            routed_frequency <= 16'h0000;
            alert_null <= 1'b0;
        end else begin
            case (cmd_type)
                CMD_ROUTE: begin
                    routed_frequency <= encoded_frequency ^ {8'h4d, node_id};
                    alert_null <= 1'b0;
                end
                CMD_NULL: begin
                    alert_null <= node_id[0];
                end
                // Training flaw: no default assignment. In review, explain how
                // stale routed_frequency/alert_null state survives malformed
                // command types and can affect later routing decisions.
            endcase
        end
    end
endmodule
