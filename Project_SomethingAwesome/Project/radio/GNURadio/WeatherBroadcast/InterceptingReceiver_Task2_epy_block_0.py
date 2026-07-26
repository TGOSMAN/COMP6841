"""Random frequency hopper with separate RANDU phase symbols for task 3.01."""

import hashlib
import math

import numpy as np
from gnuradio import gr


class blk(gr.sync_block):
    """
    Preserve complex baseband audio while moving it between random RF channels.

    The hop selector is deliberately separate from RANDU. RANDU rotates only
    the QPSK phase symbols so learners can recover and remove that weak layer.
    """

    def __init__(
        self,
        sample_rate=44200,
        samples_per_hop=4410,
        samples_per_phase_symbol=10,
        phase_seed=1,
        hop_key="weather-task-3.01-hop-v1",
    ):
        gr.sync_block.__init__(
            self,
            name="Random Hopper + RANDU Phase Symbols",
            in_sig=[np.complex64],
            out_sig=[np.complex64],
        )
        self.sample_rate = max(1.0, float(sample_rate))
        self.samples_per_hop = max(1, int(samples_per_hop))
        self.samples_per_phase_symbol = max(1, int(samples_per_phase_symbol))
        self.hop_frequencies = (-16000.0, -10000.0, -4000.0, 3000.0, 9000.0, 15000.0)
        self.hop_key = str(hop_key)
        self.phase_state = (int(phase_seed) & 0x7FFFFFFF) or 1
        if self.phase_state % 2 == 0:
            self.phase_state += 1
        self.carrier_phase = 0.0
        self.hop_index = 0
        self.samples_in_hop = 0
        self.samples_in_phase_symbol = 0
        self.current_frequency = self._hop_frequency(self.hop_index)
        self.current_phase_symbol = self._next_phase_symbol()

    def _hop_frequency(self, hop_index):
        digest = hashlib.sha256(
            f"{self.hop_key}:{hop_index}".encode("utf-8")
        ).digest()
        slot = int.from_bytes(digest[:4], "big") % len(self.hop_frequencies)
        return self.hop_frequencies[slot]

    def _next_phase_symbol(self):
        self.phase_state = (65539 * self.phase_state) & 0x7FFFFFFF
        return (1.0, 1.0j, -1.0, -1.0j)[(self.phase_state >> 28) & 0x03]

    def set_sample_rate(self, sample_rate):
        self.sample_rate = max(1.0, float(sample_rate))

    def work(self, input_items, output_items):
        source = input_items[0]
        output = output_items[0]

        for index, sample in enumerate(source):
            if self.samples_in_hop >= self.samples_per_hop:
                self.hop_index += 1
                self.current_frequency = self._hop_frequency(self.hop_index)
                self.samples_in_hop = 0

            if self.samples_in_phase_symbol >= self.samples_per_phase_symbol:
                self.current_phase_symbol = self._next_phase_symbol()
                self.samples_in_phase_symbol = 0

            carrier = np.complex64(
                complex(math.cos(self.carrier_phase), math.sin(self.carrier_phase))
            )
            output[index] = sample * self.current_phase_symbol * carrier
            self.carrier_phase += 2.0 * math.pi * self.current_frequency / self.sample_rate
            if abs(self.carrier_phase) > math.pi * 4096:
                self.carrier_phase = math.fmod(self.carrier_phase, 2.0 * math.pi)
            self.samples_in_hop += 1
            self.samples_in_phase_symbol += 1

        return len(output)
