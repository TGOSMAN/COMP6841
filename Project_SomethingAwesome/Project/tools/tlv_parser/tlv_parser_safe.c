#include <stdint.h>
#include <stdio.h>
#include <string.h>

int parse_note_tlv_safe(const uint8_t *frame, size_t frame_len) {
    char operator_note[32];
    if (frame_len < 2) {
        return -1;
    }

    uint8_t type = frame[0];
    size_t declared_len = frame[1];
    if (type != 0x42) {
        return -2;
    }
    if (declared_len > frame_len - 2) {
        puts("reject: declared length exceeds available frame bytes");
        return -3;
    }
    if (declared_len >= sizeof(operator_note)) {
        puts("reject: operator note exceeds destination buffer");
        return -4;
    }

    memcpy(operator_note, frame + 2, declared_len);
    operator_note[declared_len] = '\0';
    puts(operator_note);
    return 0;
}
