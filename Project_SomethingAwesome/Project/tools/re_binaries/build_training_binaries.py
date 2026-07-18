from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent

IMAGES = {
    "bushfire_node.bin": (
        b"SFCBIN\x01BUSHFIRE_NODE\x00"
        b"STATE=WHITENER;CHECK=ANOMALY_CLEAR;TARGET_SCORE=0x42\x00"
        b"\x13\x37\x42\x4d"
    ),
    "farm_gate_controller.bin": (
        b"SFCBIN\x01FARM_GATE_CONTROLLER\x00"
        b"TLV=0x42;ADMIN=ADMIN_A7;ACTION=FIBONACCI_GATE\x00"
        b"\xa7\x42\x10\x05"
    ),
}


def main() -> None:
    for name, data in IMAGES.items():
        (ROOT / name).write_bytes(data)
        print(f"wrote {name}: {len(data)} bytes")


if __name__ == "__main__":
    main()
