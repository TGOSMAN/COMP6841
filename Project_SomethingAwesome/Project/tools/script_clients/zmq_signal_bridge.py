from __future__ import annotations

import argparse
import json
import socket
import struct
import sys
import time


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


def send_meta(sock: socket.socket, args: argparse.Namespace) -> None:
    payload = {
        "type": "meta",
        "challenge_id": args.challenge_id,
        "center_hz": args.center_hz,
        "span_hz": args.span_hz,
        "sample_rate_hz": args.sample_rate_hz,
        "bins": args.bins,
        "scheme_id": args.scheme_id,
        "modulation": args.modulation,
        "source_label": args.source_label,
    }
    ack = send_json_line(sock, payload)
    if ack:
        print(ack)


def send_iq_frame(sock: socket.socket, args: argparse.Namespace, payload: bytes, frame: int) -> bool:
    complete = len(payload) - (len(payload) % 8)
    if complete < args.min_iq_samples * 8:
        return False
    samples = complete // 8
    header = (
        "SFORGE IQCF32 "
        f"challenge_id={args.challenge_id} center_hz={args.center_hz} "
        f"sample_rate_hz={args.sample_rate_hz} span_hz={args.span_hz} "
        f"bins={args.bins} scheme_id={args.scheme_id} modulation={args.modulation_token} "
        f"source_label={args.source_label_token} samples={samples}\n"
    )
    sock.sendall(header.encode("ascii"))
    sock.sendall(payload[:complete])
    ack = recv_ack(sock)
    if args.print_acks and ack:
        print(ack)
    return True


def normalize_fft_row(values: list[float], scale: str) -> list[float]:
    if not values:
        return []
    if scale == "clamp":
        return [round(max(0.0, min(1.0, value)), 4) for value in values]
    low = min(values)
    high = max(values)
    dynamic_range = max(1e-9, high - low)
    return [round(max(0.0, min(1.0, (value - low) / dynamic_range)), 4) for value in values]


def send_fft_rows(sock: socket.socket, args: argparse.Namespace, payload: bytes, frame: int) -> int:
    complete = len(payload) - (len(payload) % 4)
    if complete < args.bins * 4:
        return 0
    values = struct.unpack(f"<{complete // 4}f", payload[:complete])
    sent = 0
    for start in range(0, len(values) - args.bins + 1, args.bins):
        row = normalize_fft_row(list(values[start : start + args.bins]), args.fft_scale)
        message = {
            "type": "fft",
            "challenge_id": args.challenge_id,
            "center_hz": args.center_hz,
            "span_hz": args.span_hz,
            "sample_rate_hz": args.sample_rate_hz,
            "bins": args.bins,
            "row": row,
            "parser": {
                "stage": "gnu_radio_zmq_fft",
                "confidence": 0.8,
                "bit_buffer": f"zmq fft frame {frame + sent:06d}",
                "fields": {
                    "endpoint": args.endpoint,
                    "pattern": args.pattern,
                    "dtype": args.dtype,
                    "frame": frame + sent,
                },
                "note": "FFT row received from GNU Radio ZMQ and forwarded to Signal Forge.",
            },
        }
        ack = send_json_line(sock, message)
        if args.print_acks and ack:
            print(ack)
        sent += 1
        if args.max_frames and frame + sent >= args.max_frames:
            break
    return sent


def import_zmq():
    try:
        import zmq  # type: ignore
    except ImportError:
        print(
            "pyzmq is required for the GNU Radio ZMQ bridge.\n"
            "Install it in the GNU Radio environment with one of:\n"
            "  sudo apt install python3-zmq\n"
            "  python -m pip install pyzmq",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return zmq


def open_zmq_receiver(args: argparse.Namespace):
    zmq = import_zmq()
    context = zmq.Context.instance()
    socket_type = zmq.PULL if args.pattern == "pull" else zmq.SUB
    receiver = context.socket(socket_type)
    receiver.setsockopt(zmq.RCVTIMEO, int(args.timeout_ms))
    receiver.setsockopt(zmq.RCVHWM, int(args.high_water_mark))
    if args.pattern == "sub":
        receiver.setsockopt(zmq.SUBSCRIBE, args.topic.encode("utf-8"))
    if args.bind:
        receiver.bind(args.endpoint)
        direction = "bound"
    else:
        receiver.connect(args.endpoint)
        direction = "connected"
    print(f"ZMQ {args.pattern.upper()} {direction} to {args.endpoint}")
    return receiver


def recv_payload(receiver, args: argparse.Namespace) -> bytes | None:
    zmq = import_zmq()
    try:
        if args.pattern == "sub":
            parts = receiver.recv_multipart()
            if not parts:
                return None
            return parts[-1]
        return receiver.recv()
    except zmq.Again:
        return None


def bridge(args: argparse.Namespace) -> None:
    args.modulation_token = args.modulation.replace(" ", "_")
    args.source_label_token = args.source_label.replace(" ", "_")
    receiver = open_zmq_receiver(args)
    frame = 0
    last_status = time.time()
    with socket.create_connection((args.ingest_host, args.ingest_port), timeout=5) as ingest:
        send_meta(ingest, args)
        print(f"Forwarding to Signal Forge ingest {args.ingest_host}:{args.ingest_port}")
        while True:
            payload = recv_payload(receiver, args)
            if payload is None:
                if time.time() - last_status > args.status_interval:
                    print(f"waiting for ZMQ frames on {args.endpoint}")
                    last_status = time.time()
                continue
            if args.dtype == "cf32":
                if send_iq_frame(ingest, args, payload, frame):
                    frame += 1
            else:
                frame += send_fft_rows(ingest, args, payload, frame)
            if args.max_frames and frame >= args.max_frames:
                break
            if args.rate_limit > 0:
                time.sleep(1 / args.rate_limit)
    print(json.dumps({"ok": True, "frames_forwarded": frame, "endpoint": args.endpoint}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bridge GNU Radio ZMQ streams into the Signal Forge waterfall.")
    parser.add_argument("--endpoint", default="tcp://127.0.0.1:5555", help="GNU Radio ZMQ endpoint.")
    parser.add_argument("--pattern", choices=["pull", "sub"], default="pull", help="Use pull for ZMQ PUSH Sink, sub for ZMQ PUB Sink.")
    parser.add_argument("--bind", action="store_true", help="Bind the bridge socket. By default it connects to GNU Radio.")
    parser.add_argument("--topic", default="", help="SUB topic prefix for GNU Radio PUB Sink.")
    parser.add_argument("--dtype", choices=["cf32", "f32fft"], default="cf32", help="GNU Radio payload format.")
    parser.add_argument("--challenge-id", default="tunnel-packet-injection")
    parser.add_argument("--ingest-host", default="127.0.0.1")
    parser.add_argument("--ingest-port", type=int, default=9100)
    parser.add_argument("--center-hz", type=float, default=915_000_000)
    parser.add_argument("--sample-rate-hz", type=float, default=44_200)
    parser.add_argument("--span-hz", type=float, default=44_200)
    parser.add_argument("--bins", type=int, default=384)
    parser.add_argument("--scheme-id", default="GNU-RADIO-ZMQ-BRIDGE")
    parser.add_argument("--modulation", default="GNU Radio ZMQ cf32")
    parser.add_argument("--source-label", default="GNU Radio ZMQ")
    parser.add_argument("--fft-scale", choices=["minmax", "clamp"], default="minmax")
    parser.add_argument("--min-iq-samples", type=int, default=64)
    parser.add_argument("--timeout-ms", type=int, default=1000)
    parser.add_argument("--high-water-mark", type=int, default=8)
    parser.add_argument("--status-interval", type=float, default=3.0)
    parser.add_argument("--rate-limit", type=float, default=0.0, help="Optional maximum forwarded frames per second.")
    parser.add_argument("--max-frames", type=int, default=0, help="0 means run until interrupted.")
    parser.add_argument("--print-acks", action="store_true")
    return parser


def main() -> None:
    bridge(build_parser().parse_args())


if __name__ == "__main__":
    main()
