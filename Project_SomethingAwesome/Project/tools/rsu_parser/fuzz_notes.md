# Parser Hardening Notes

Useful hardening ideas for this training parser:

- reject fields longer than their destination buffers,
- parse into bounded temporary buffers,
- fuzz with randomly generated frames,
- compile production code with stack protection and address sanitizers,
- prefer memory-safe parser implementations where practical.
