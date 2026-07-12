# Telemetry Decoder Reverse Engineering Challenge

This tool is intentionally small and local. It teaches packet reversing without touching real systems.

Training frame:

```text
SFCTF1|VH-7A29|PX-41F0|EAST-17|BIRCH|STANDARD|2026-07-12T06:41:03Z|N-6841-0001|6d
```

The challenge is to identify:

- magic/version field,
- vehicle ID,
- pseudonym ID,
- booth ID,
- route code,
- schedule code,
- timestamp,
- nonce,
- weak checksum.

Run:

```powershell
python tools/telemetry_decoder/telemetry_decoder.py artifacts/telemetry-frame.txt
```

The C source mirrors the Python tool for learners who want to inspect or compile a binary.
