#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned int weak_checksum(const char *s) {
    unsigned int total = 0;
    for (const unsigned char *p = (const unsigned char *)s; *p; ++p) {
        total = (total + *p) & 0xff;
    }
    return total;
}

int main(int argc, char **argv) {
    char buf[512];
    FILE *fp;
    char *fields[9];
    char *cursor;
    int count = 0;
    char checksum_input[448] = {0};
    unsigned int expected;
    unsigned int provided;

    if (argc != 2) {
        puts("usage: telemetry_decoder <frame-file>");
        return 2;
    }

    fp = fopen(argv[1], "r");
    if (!fp) {
        puts("could not open frame file");
        return 1;
    }
    if (!fgets(buf, sizeof(buf), fp)) {
        puts("empty frame file");
        fclose(fp);
        return 1;
    }
    fclose(fp);
    buf[strcspn(buf, "\r\n")] = '\0';

    cursor = strtok(buf, "|");
    while (cursor && count < 9) {
        fields[count++] = cursor;
        cursor = strtok(NULL, "|");
    }

    if (count != 9 || strcmp(fields[0], "SFCTF1") != 0) {
        puts("not an SFCTF1 telemetry frame");
        return 1;
    }

    for (int i = 0; i < 8; ++i) {
        strcat(checksum_input, fields[i]);
        if (i != 7) strcat(checksum_input, "|");
    }

    expected = weak_checksum(checksum_input);
    provided = (unsigned int)strtoul(fields[8], NULL, 16);

    printf("vehicle_id: %s\n", fields[1]);
    printf("pseudonym_id: %s\n", fields[2]);
    printf("booth_id: %s\n", fields[3]);
    printf("route_code: %s\n", fields[4]);
    printf("schedule_code: %s\n", fields[5]);
    printf("timestamp: %s\n", fields[6]);
    printf("nonce: %s\n", fields[7]);
    printf("checksum_expected: %02x\n", expected);
    printf("checksum_valid: %s\n", expected == provided ? "true" : "false");
    if (expected == provided) {
        puts("flag: CTF{REVERSER_FOUND_THE_FRAME}");
    }
    return 0;
}
