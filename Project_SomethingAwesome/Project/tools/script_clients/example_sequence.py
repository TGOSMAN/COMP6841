from __future__ import annotations

from signal_terminal_client import SignalTerminalClient


client = SignalTerminalClient(session_id="example-sequence")

for command in ["scan", "tune 915.000", "receive"]:
    result = client.command("tunnel-tuning", command)
    print(f"$ {command}")
    print("\n".join(result.get("lines", [])))
    if result.get("flag"):
        print(f"FLAG: {result['flag']}")

