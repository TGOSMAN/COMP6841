"""Signal Forge live sink wrapper for the civilian emergency flowgraph."""

from __future__ import annotations

import os
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from signal_forge_live_sink import SignalForgeLiveSink


class blk(SignalForgeLiveSink):
    def __init__(self, center_hz=169650000, sample_rate_hz=44100):
        challenge_id = os.environ.get(
            "SIGNAL_FORGE_CHALLENGE_ID",
            "civilian-emergency-intercept",
        )
        super().__init__(
            challenge_id=challenge_id,
            center_hz=float(center_hz),
            sample_rate_hz=float(sample_rate_hz),
            source_label="CivilianEmergencyReceiver.py post-channel-model CF32",
            modulation="AM audio plus Barker-13 BPSK metadata",
            framing="BARKER13",
            integrity="CRC16_CCITT",
        )
