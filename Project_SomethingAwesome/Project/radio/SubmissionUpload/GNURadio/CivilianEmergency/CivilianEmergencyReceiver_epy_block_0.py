"""Live civilian-emergency audio source with Barker-13 framing and CRC-16."""

from __future__ import annotations

import math
import os

import numpy as np
from gnuradio import gr


BARKER_13 = (1, 1, 1, 1, 1, -1, -1, 1, 1, -1, 1, -1, 1)
PAYLOADS = {
    "civilian-emergency-intercept": b"CIVIC-7|NORTH-SECTOR|WEEKLY-TEST",
    "civilian-emergency-obscured": b"CIVIC-7|NORTH-SECTOR|PRIORITY",
    "civilian-emergency-active-re": b"CIVIC-7|NORTH-SECTOR|EVACUATE|AUTH",
}


def crc16_ccitt(data: bytes, initial: int = 0xFFFF) -> int:
    """Return CRC-16/CCITT-FALSE for a payload."""
    crc = initial & 0xFFFF
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def framed_symbols(payload: bytes) -> tuple[tuple[int, ...], int]:
    """Build Barker-13 + payload + big-endian CRC trailer symbols."""
    crc = crc16_ccitt(payload)
    framed_bytes = payload + crc.to_bytes(2, "big")
    payload_symbols = tuple(
        1 if value & (1 << bit_index) else -1
        for value in framed_bytes
        for bit_index in range(7, -1, -1)
    )
    if crc16_ccitt(framed_bytes[:-2]) != int.from_bytes(framed_bytes[-2:], "big"):
        raise ValueError("Civilian emergency frame failed its CRC-16 self-check")
    return BARKER_13 + payload_symbols, crc


class blk(gr.sync_block):
    """Generate live alert audio plus Barker-coded, CRC-protected metadata."""

    def __init__(
        self,
        sample_rate=44100,
        symbol_samples=40,
        samples_per_hop=11025,
        challenge_id="",
    ):
        gr.sync_block.__init__(
            self,
            name="Live Emergency Audio + Barker-13 + CRC-16",
            in_sig=None,
            out_sig=[np.complex64],
        )
        self.sample_rate = max(8_000.0, float(sample_rate))
        self.symbol_samples = max(4, int(symbol_samples))
        self.samples_per_hop = max(self.symbol_samples, int(samples_per_hop))
        self.challenge_id = (
            str(challenge_id).strip()
            or os.environ.get("SIGNAL_FORGE_CHALLENGE_ID", "civilian-emergency-intercept")
        )
        self.payload = PAYLOADS.get(self.challenge_id, PAYLOADS["civilian-emergency-intercept"])
        self.symbols, self.frame_crc = framed_symbols(self.payload)
        self.crc_check = "valid"
        self.sample_index = 0
        self.metadata_phase = 0.0
        self.hop_phase = 0.0

    def set_sample_rate(self, sample_rate):
        self.sample_rate = max(8_000.0, float(sample_rate))

    def _hop_frequency(self, hop_index: int) -> float:
        clear_offsets = (-12_000.0, -4_000.0, 6_000.0, 14_000.0)
        if self.challenge_id == "civilian-emergency-obscured":
            state = 7
            for _ in range(hop_index + 1):
                state = (5 * state + 1) % 16
            return clear_offsets[state % len(clear_offsets)]
        if self.challenge_id == "civilian-emergency-active-re":
            return clear_offsets[(hop_index * 3 + 1) % len(clear_offsets)]
        return clear_offsets[hop_index % len(clear_offsets)]

    def work(self, input_items, output_items):
        output = output_items[0]
        metadata_step = 2.0 * math.pi * 3_200.0 / self.sample_rate

        for index in range(len(output)):
            absolute_sample = self.sample_index + index
            symbol = self.symbols[(absolute_sample // self.symbol_samples) % len(self.symbols)]
            cadence = 0.58 + 0.24 * math.sin(2.0 * math.pi * absolute_sample / self.sample_rate * 1.7)
            alert_audio = (
                0.44 * math.sin(2.0 * math.pi * 640.0 * absolute_sample / self.sample_rate)
                + 0.28 * math.sin(2.0 * math.pi * 960.0 * absolute_sample / self.sample_rate)
                + 0.12 * math.sin(2.0 * math.pi * 1_280.0 * absolute_sample / self.sample_rate)
            ) * cadence
            metadata = complex(math.cos(self.metadata_phase), math.sin(self.metadata_phase)) * symbol * 0.24

            hop_index = absolute_sample // self.samples_per_hop
            hop_frequency = self._hop_frequency(hop_index)
            hop_step = 2.0 * math.pi * hop_frequency / self.sample_rate
            carrier = complex(math.cos(self.hop_phase), math.sin(self.hop_phase))
            output[index] = np.complex64((complex(alert_audio, alert_audio * 0.18) + metadata) * carrier)

            self.metadata_phase = math.fmod(self.metadata_phase + metadata_step, 2.0 * math.pi)
            self.hop_phase = math.fmod(self.hop_phase + hop_step, 2.0 * math.pi)

        self.sample_index += len(output)
        return len(output)
