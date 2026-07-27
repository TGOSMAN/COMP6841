#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""GNU Radio generated Python flowgraph for the civilian emergency receiver."""

from __future__ import annotations

import signal
import threading

from gnuradio import channels
from gnuradio import gr

import CivilianEmergencyReceiver_epy_block_0 as epy_block_0
import CivilianEmergencyReceiver_epy_block_1 as epy_block_1


class CivilianEmergencyReceiver(gr.top_block):
    def __init__(self):
        gr.top_block.__init__(
            self,
            "Civilian Emergency Receiver / Barker-13 + CRC-16",
            catch_exceptions=True,
        )
        self.samp_rate = samp_rate = 44_100

        self.live_emergency_source = epy_block_0.blk(
            sample_rate=samp_rate,
            symbol_samples=40,
            samples_per_hop=11_025,
        )
        self.channel_model = channels.channel_model(
            noise_voltage=0.08,
            frequency_offset=0.0,
            epsilon=1.0,
            taps=[1.0, 0.12 + 0.04j],
            noise_seed=6841,
            block_tags=False,
        )
        self.signal_forge_live_sink = epy_block_1.blk(
            center_hz=169_650_000,
            sample_rate_hz=samp_rate,
        )

        self.connect((self.live_emergency_source, 0), (self.channel_model, 0))
        self.connect((self.channel_model, 0), (self.signal_forge_live_sink, 0))

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.live_emergency_source.set_sample_rate(self.samp_rate)


def main(top_block_cls=CivilianEmergencyReceiver):
    top_block = top_block_cls()
    stopped = threading.Event()

    def stop_flowgraph(sig=None, frame=None):
        if stopped.is_set():
            return
        stopped.set()
        top_block.stop()
        top_block.wait()

    signal.signal(signal.SIGINT, stop_flowgraph)
    signal.signal(signal.SIGTERM, stop_flowgraph)
    top_block.start()
    try:
        while not stopped.wait(0.5):
            pass
    finally:
        stop_flowgraph()


if __name__ == "__main__":
    main()
