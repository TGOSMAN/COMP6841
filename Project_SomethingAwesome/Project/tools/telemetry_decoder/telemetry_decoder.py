from __future__ import annotations

import sys
from pathlib import Path


FLAG = "CTF{REVERSER_FOUND_THE_FRAME}"


def weak_checksum(fields: list[str]) -> str:
    total = sum(bytearray("|".join(fields).encode("utf-8"))) & 0xFF
    return f"{total:02x}"


def decode(frame: str) -> dict[str, str | bool]:
    parts = frame.strip().split("|")
    if len(parts) != 9 or parts[0] != "SFCTF1":
        raise ValueError("not an SFCTF1 telemetry frame")

    names = [
        "magic",
        "vehicle_id",
        "pseudonym_id",
        "booth_id",
        "route_code",
        "schedule_code",
        "timestamp",
        "nonce",
        "checksum",
    ]
    decoded = dict(zip(names, parts))
    expected = weak_checksum(parts[:-1])
    decoded["expected_checksum"] = expected
    decoded["checksum_valid"] = expected == parts[-1].lower()
    if decoded["checksum_valid"]:
        decoded["flag"] = FLAG
    return decoded


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: telemetry_decoder.py <frame-file>")
        return 2

    try:
        frame = Path(sys.argv[1]).read_text(encoding="utf-8")
        decoded = decode(frame)
    except Exception as exc:
        print(f"decode failed: {exc}")
        return 1

    for key, value in decoded.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
