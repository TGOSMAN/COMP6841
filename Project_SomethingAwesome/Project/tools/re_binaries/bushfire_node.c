#include <stdint.h>
#include <stdio.h>
#include <string.h>

static uint8_t score_packet(const uint8_t *packet, size_t length) {
    uint8_t score = 0;
    for (size_t index = 0; index < length; index++) {
        score ^= (uint8_t)((packet[index] << (index % 3)) | (packet[index] >> 5));
    }
    return score;
}

int main(int argc, char **argv) {
    uint8_t buffer[64] = {0};
    if (argc < 2) {
        puts("usage: bushfire_node <packet>");
        return 1;
    }

    size_t declared = strlen(argv[1]);
    memcpy(buffer, argv[1], declared);
    uint8_t score = score_packet(buffer, declared);

    if (strstr((char *)buffer, "ANOMALY_CLEAR") && score == 0x42) {
        puts("CTF{LOCAL_BUSHFIRE_NODE_ACCEPTED}");
    } else {
        printf("reject score=0x%02x\n", score);
    }
    return 0;
}
