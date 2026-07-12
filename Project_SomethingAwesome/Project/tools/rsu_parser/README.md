# Roadside Unit Parser Binary Exploitation Challenge

This is a local-only synthetic parser challenge. It is not a real roadside unit and does not connect to any external system.

Training idea:

- `rsu_parser_vuln.c` uses unsafe fixed-size copies and has a deliberate controlled success condition.
- `rsu_parser_safe.c` validates lengths and rejects the same oversized frame.
- `sample_overflow_frame.txt` is a benign local challenge input.

Compile on a machine with GCC:

```bash
gcc -g -O0 -fno-stack-protector -o rsu_parser_vuln rsu_parser_vuln.c
gcc -g -O2 -o rsu_parser_safe rsu_parser_safe.c
```

Run:

```bash
./rsu_parser_vuln sample_overflow_frame.txt
./rsu_parser_safe sample_overflow_frame.txt
```

If no compiler is available, read the C source and use this as a code-review and exploit-design exercise.
