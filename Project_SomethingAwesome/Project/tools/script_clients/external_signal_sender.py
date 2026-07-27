from __future__ import annotations

import argparse
import json
import math
import random
import socket
import struct
import time


def gaussian_row(bins: int, frame: int, tone_offset_hz: float, span_hz: float) -> list[float]:
    row: list[float] = []
    drift_hz = math.sin(frame * 0.045) * span_hz * 0.04
    gate = 0.28 + 0.72 * (0.5 + 0.5 * math.sin(frame * 0.31))
    for index in range(bins):
        offset_hz = -span_hz / 2 + index / max(1, bins - 1) * span_hz
        noise = 0.025 + random.random() * 0.045
        distance = (offset_hz - tone_offset_hz - drift_hz) / max(1.0, span_hz * 0.025)
        signal = math.exp(-0.5 * distance * distance) * gate
        row.append(round(min(1.0, noise + signal), 4))
    return row


def complex_tone_block(samples: int, frame: int, tone_offset_hz: float, sample_rate_hz: float) -> bytes:
    output = bytearray()
    phase_base = frame * samples * 2.0 * math.pi * tone_offset_hz / sample_rate_hz
    for index in range(samples):
        phase = phase_base + index * 2.0 * math.pi * tone_offset_hz / sample_rate_hz
        envelope = 0.15 + 0.75 * (0.5 + 0.5 * math.sin((frame + index / samples) * 0.52))
        noise_i = (random.random() * 2 - 1) * 0.035
        noise_q = (random.random() * 2 - 1) * 0.035
        output += struct.pack("<ff", math.cos(phase) * envelope + noise_i, math.sin(phase) * envelope + noise_q)
    return bytes(output)


def recv_ack(sock: socket.socket) -> str:
    sock.settimeout(1.5)
    buffer = bytearray()
    try:
        while not buffer.endswith(b"\n"):
            chunk = sock.recv(1)
            if not chunk:
                break
            buffer += chunk
    except TimeoutError:
        return ""
    finally:
        sock.settimeout(None)
    return buffer.decode("utf-8", errors="replace").strip()


def send_json_line(sock: socket.socket, payload: dict) -> str:
    sock.sendall((json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))
    return recv_ack(sock)


def send_fft(args: argparse.Namespace) -> None:
    with socket.create_connection((args.host, args.port), timeout=5) as sock:
        meta = {
            "type": "meta",
            "challenge_id": args.challenge_id,
            "center_hz": args.center_hz,
            "span_hz": args.span_hz,
            "sample_rate_hz": args.sample_rate_hz,
            "bins": args.bins,
            "scheme_id": args.scheme_id,
            "modulation": "external FFT row",
            "source_label": "External FFT sender",
        }
        print(send_json_line(sock, meta))
        for frame in range(args.frames):
            payload = {
                "type": "fft",
                "challenge_id": args.challenge_id,
                "center_hz": args.center_hz,
                "span_hz": args.span_hz,
                "sample_rate_hz": args.sample_rate_hz,
                "bins": args.bins,
                "row": gaussian_row(args.bins, frame, args.tone_offset_hz, args.span_hz),
                "samples": [round(math.sin((index + frame) * 0.18), 4) for index in range(160)],
                "parser": {
                    "stage": "external_fft",
                    "confidence": 0.82,
                    "bit_buffer": f"external frame {frame:04d}",
                    "fields": {"frame": frame, "source": "tools/script_clients/external_signal_sender.py"},
                    "note": "Synthetic FFT row accepted from the external signal ingest client.",
                },
            }
            ack = send_json_line(sock, payload)
            if ack:
                print(ack)
            time.sleep(1 / args.rate)


def send_iq(args: argparse.Namespace) -> None:
    with socket.create_connection((args.host, args.port), timeout=5) as sock:
        for frame in range(args.frames):
            header = (
                "SFORGE IQCF32 "
                f"challenge_id={args.challenge_id} center_hz={args.center_hz} "
                f"sample_rate_hz={args.sample_rate_hz} span_hz={args.span_hz} "
                f"bins={args.bins} scheme_id={args.scheme_id} modulation=raw_cf32 "
                f"source_label=External_IQ_sender samples={args.block_samples}\n"
            )
            sock.sendall(header.encode("ascii"))
            sock.sendall(complex_tone_block(args.block_samples, frame, args.tone_offset_hz, args.sample_rate_hz))
            ack = recv_ack(sock)
            if ack:
                print(ack)
            time.sleep(1 / args.rate)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Push external RF frames into the Signal Forge CTF waterfall.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9100)
    parser.add_argument("--challenge-id", default="tunnel-basic-dos")
    parser.add_argument("--mode", choices=["fft", "iq"], default="fft")
    parser.add_argument("--frames", type=int, default=180)
    parser.add_argument("--rate", type=float, default=18.0, help="Frames or IQ blocks per second.")
    parser.add_argument("--bins", type=int, default=384)
    parser.add_argument("--block-samples", type=int, default=2048)
    parser.add_argument("--center-hz", type=float, default=915_000_000)
    parser.add_argument("--sample-rate-hz", type=float, default=44_200)
    parser.add_argument("--span-hz", type=float, default=44_200)
    parser.add_argument("--tone-offset-hz", type=float, default=10_000)
    parser.add_argument("--scheme-id", default="EXTERNAL-DEMO-CF32")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.rate = max(0.1, args.rate)
    if args.mode == "fft":
        send_fft(args)
    elif args.mode == "iq":
        send_iq(args)


if __name__ == "__main__":
    main()
