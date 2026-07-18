#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    uint8_t type;
    uint8_t declared_length;
    char payload[32];
} tlv_frame;

int main(int argc, char **argv) {
    tlv_frame frame = {0x42, 0, {0}};
    if (argc < 2) {
        puts("usage: farm_gate_controller <payload>");
        return 1;
    }

    frame.declared_length = (uint8_t)strlen(argv[1]);
    strcpy(frame.payload, argv[1]);

    if (strstr(frame.payload, "ADMIN_A7") && strstr(frame.payload, "FIBONACCI_GATE")) {
        puts("CTF{LOCAL_GATE_PATTERN_ACCEPTED}");
    } else {
        printf("locked type=0x%02x len=%u\n", frame.type, frame.declared_length);
    }
    return 0;
}
