# Signal Forge HDL Exercises

These files are synthetic training targets for the advanced CTF tasks. They are
not vendor HDL and do not target real radio or gate hardware.

- `../../radio/AntennaBinFormer.v` is the recovered twelve-element complex
  receive beam-gate. It performs a true complex multiply-accumulate on the I/Q
  ADC channels using four-state phase coefficients.
- `../../radio/AntennaBinFormer_tb.v` sweeps the recovered gate's 32 angular
  bins so a reviewer can map its main and unintended accepted lobes.
- `farm_gate_lock_controller.v` models a gate lock state machine with a
  deliberately unsafe maintenance override path.

Use them as review and testbench inputs for local coursework only.
