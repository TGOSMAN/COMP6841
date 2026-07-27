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
    RANDU-based spreading block for continuous complex audio/QAM.

    Input:
        complex64 baseband signal, I + jQ

    Output:
        complex64 spread signal

    The RANDU state is converted into a binary chip:
        +1 or -1

    One chip is held for samples_per_chip input samples.
    """

    def __init__(self, samples_per_chip=10, seed=1):
        gr.sync_block.__init__(
            self,
            name="RANDU Phase Shifter",
            in_sig=[np.complex64],
            out_sig=[np.complex64]
        )

        self.samples_per_chip = max(1, int(samples_per_chip))

        # RANDU should not be started from zero.
        self.state = int(seed) & 0x7FFFFFFF

        if self.state == 0:
            self.state = 1

        # Using an odd seed is more representative of RANDU.
        if self.state % 2 == 0:
            self.state += 1

        self.current_chip = np.complex64(1.0 + 0.0j)
        self.chip_sample_counter = 0

    def next_randu(self):
        """
        RANDU recurrence:

            x[n+1] = 65539*x[n] mod 2^31
        """

        self.state = (65539 * self.state) & 0x7FFFFFFF
        return self.state

    def generate_chip(self):
    	state = self.next_randu()

    	# Select two relatively high state bits.
    	phase_index = (state >> 28) & 0x03

    	phase_table = (
        	np.complex64(1.0 + 0.0j),
        	np.complex64(0.0 + 1.0j),
        	np.complex64(-1.0 + 0.0j),
        	np.complex64(0.0 - 1.0j)
    	)

    	return phase_table[phase_index]

    def work(self, input_items, output_items):
        x = input_items[0]
        y = output_items[0]

        for i in range(len(x)):

            # Generate a new chip at the chip-rate boundary.
            if self.chip_sample_counter == 0:
                self.current_chip = self.generate_chip()

            # Apply the same sign change to I and Q.
            y[i] = x[i] * self.current_chip

            self.chip_sample_counter += 1

            if self.chip_sample_counter >= self.samples_per_chip:
                self.chip_sample_counter = 0

        return len(y)