#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void win(void) {
    puts("CTF{TLV_LENGTH_FIELDS_BITE_BACK}");
}

int parse_note_tlv(const uint8_t *frame, size_t frame_len) {
    char operator_note[32];
    if (frame_len < 2) {
        return -1;
    }

    uint8_t type = frame[0];
    uint8_t declared_len = frame[1];
    if (type != 0x42) {
        return -2;
    }

    /*
     * Vulnerability: declared_len is trusted for the copy, while the only
     * bounds check was that the frame contains at least a TLV header.
     */
    memcpy(operator_note, frame + 2, declared_len);
    operator_note[sizeof(operator_note) - 1] = '\0';

    if (strstr(operator_note, "MAINT_DIAG_UNLOCK") != NULL) {
        win();
    }
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 2) {
        puts("usage: tlv_parser_vuln <ascii-note>");
        return 1;
    }
    size_t note_len = strlen(argv[1]);
    uint8_t *frame = calloc(note_len + 2, 1);
    frame[0] = 0x42;
    frame[1] = (uint8_t)(note_len + 64);
    memcpy(frame + 2, argv[1], note_len);
    int result = parse_note_tlv(frame, note_len + 2);
    free(frame);
    return result;
}
