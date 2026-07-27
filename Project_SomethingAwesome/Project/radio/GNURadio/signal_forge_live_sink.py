"""Non-blocking GNU Radio sink for the Signal Forge live CF32 ingest."""

from __future__ import annotations

import os
import queue
import socket
import threading
import time

import numpy
from gnuradio import gr


class SignalForgeLiveSink(gr.sync_block):
    """Stream complex64 samples from a running flowgraph to Signal Forge."""

    def __init__(
        self,
        challenge_id: str,
        center_hz: float,
        sample_rate_hz: float,
        source_label: str,
        modulation: str,
        block_samples: int = 2048,
        framing: str = "",
        integrity: str = "",
    ):
        gr.sync_block.__init__(
            self,
            name="Signal Forge live CF32 sink",
            in_sig=[numpy.complex64],
            out_sig=None,
        )
        self.challenge_id = challenge_id
        self.center_hz = float(center_hz)
        self.sample_rate_hz = float(sample_rate_hz)
        self.source_label = source_label.replace(" ", "_")
        self.modulation = modulation.replace(" ", "_")
        self.framing = framing.replace(" ", "_")
        self.integrity = integrity.replace(" ", "_")
        self.block_samples = max(64, int(block_samples))
        self.host = os.environ.get("SIGNAL_INGEST_HOST", "127.0.0.1")
        self.port = int(os.environ.get("SIGNAL_INGEST_PORT", "9100"))
        self._chunks: queue.Queue[bytes | None] = queue.Queue(maxsize=32)
        self._stopping = threading.Event()
        self._next_sample_deadline = time.monotonic()
        self._worker = threading.Thread(target=self._send_loop, daemon=True)
        self._worker.start()

    def work(self, input_items, output_items):
        samples = numpy.asarray(input_items[0], dtype=numpy.complex64)
        if samples.size:
            now = time.monotonic()
            wait_seconds = self._next_sample_deadline - now
            if wait_seconds > 0:
                time.sleep(wait_seconds)
                now = time.monotonic()
            self._next_sample_deadline = max(now, self._next_sample_deadline) + samples.size / self.sample_rate_hz
            try:
                self._chunks.put_nowait(samples.tobytes())
            except queue.Full:
                pass
        return len(samples)

    def stop(self):
        self._stopping.set()
        try:
            self._chunks.put_nowait(None)
        except queue.Full:
            pass
        self._worker.join(timeout=1.0)
        return True

    def _header(self) -> bytes:
        framing = f" framing={self.framing}" if self.framing else ""
        integrity = f" integrity={self.integrity} crc_check=valid" if self.integrity else ""
        return (
            "SFORGE RAWIQ "
            f"challenge_id={self.challenge_id} "
            f"center_hz={self.center_hz:g} "
            f"sample_rate_hz={self.sample_rate_hz:g} "
            f"span_hz={self.sample_rate_hz:g} "
            "bins=384 "
            f"scheme_id=GNU-RADIO-LIVE-{self.challenge_id.upper()} "
            f"modulation={self.modulation} "
            f"source_label={self.source_label} "
            f"block_samples={self.block_samples}"
            f"{framing}{integrity}\n"
        ).encode("ascii")

    def _connect(self) -> socket.socket:
        connection = socket.create_connection((self.host, self.port), timeout=1.5)
        connection.settimeout(1.5)
        connection.sendall(self._header())
        acknowledgement = bytearray()
        while not acknowledgement.endswith(b"\n"):
            chunk = connection.recv(1)
            if not chunk:
                raise ConnectionError("Signal Forge ingest closed before acknowledging the stream")
            acknowledgement.extend(chunk)
        connection.settimeout(None)
        return connection

    def _send_loop(self) -> None:
        connection: socket.socket | None = None
        pending = bytearray()
        block_bytes = self.block_samples * numpy.dtype(numpy.complex64).itemsize
        while not self._stopping.is_set():
            try:
                chunk = self._chunks.get(timeout=0.25)
            except queue.Empty:
                continue
            if chunk is None:
                break
            pending.extend(chunk)
            while len(pending) >= block_bytes and not self._stopping.is_set():
                block = bytes(pending[:block_bytes])
                del pending[:block_bytes]
                try:
                    if connection is None:
                        connection = self._connect()
                    connection.sendall(block)
                except OSError:
                    if connection is not None:
                        try:
                            connection.close()
                        except OSError:
                            pass
                    connection = None
                    time.sleep(0.25)
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass
