"""
Embedded Python Blocks:

Each time this file is saved, GRC will instantiate the first class it finds
to get ports and parameters of your block. The arguments to __init__  will
be the parameters. All of them are required to have default values!
"""

import numpy as np
from gnuradio import gr


class blk(gr.sync_block):
    """
    Encode 16-bit data into a 32-bit alarm packet.

    Data bits:
        Read MSB-first.

    Emergency bits:
        Inserted LSB-first after every second data bit equal to 1.
        Any emergency bits not inserted are appended after the data.

    The result is left-aligned so the C decoder starts at packet bit 31.
    """

    def __init__(self, emergency=0xB):
        gr.sync_block.__init__(
            self,
            name="Alarm Packet Encoder",
            in_sig=[np.uint16],
            out_sig=[np.uint32],
        )

        self.emergency = int(emergency) & 0x0F

    @staticmethod
    def encode(data, emergency):
        packet = 0
        packet_length = 0
        pair_count = 0
        emergency_index = 0

        # Process the 16 data bits MSB-first.
        for bit_index in range(15, -1, -1):
            data_bit = (data >> bit_index) & 1

            packet = (packet << 1) | data_bit
            packet_length += 1

            if data_bit:
                pair_count += 1

            # Insert an emergency bit after every second data 1.
            if pair_count == 2 and emergency_index < 4:
                emergency_bit = (
                    emergency >> emergency_index
                ) & 1

                packet = (packet << 1) | emergency_bit
                packet_length += 1

                emergency_index += 1
                pair_count = 0

        # Append emergency bits that were not interleaved.
        while emergency_index < 4:
            emergency_bit = (
                emergency >> emergency_index
            ) & 1

            packet = (packet << 1) | emergency_bit
            packet_length += 1
            emergency_index += 1

        # The C decoder begins reading at bit 31.
        packet <<= 32 - packet_length

        return packet & 0xFFFFFFFF

    def work(self, input_items, output_items):
        input_data = input_items[0]
        output_packets = output_items[0]

        for i in range(len(input_data)):
            output_packets[i] = self.encode(
                int(input_data[i]),
                self.emergency,
            )

        return len(output_packets)