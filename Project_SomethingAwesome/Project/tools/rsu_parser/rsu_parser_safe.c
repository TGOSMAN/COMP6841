#include <stdio.h>
#include <string.h>

typedef struct {
    char vehicle_id[12];
    char callsign[16];
    int maintenance_override;
} telemetry_record;

static int copy_field(char *dst, size_t dst_size, const char *src) {
    if (strlen(src) >= dst_size) {
        return 0;
    }
    memcpy(dst, src, strlen(src) + 1);
    return 1;
}

int main(int argc, char **argv) {
    char line[512];
    char *vehicle;
    char *callsign;
    FILE *fp;
    telemetry_record rec;

    memset(&rec, 0, sizeof(rec));

    if (argc != 2) {
        puts("usage: rsu_parser_safe <frame-file>");
        return 2;
    }

    fp = fopen(argv[1], "r");
    if (!fp || !fgets(line, sizeof(line), fp)) {
        puts("could not read frame");
        return 1;
    }
    if (fp) fclose(fp);
    line[strcspn(line, "\r\n")] = '\0';

    vehicle = strtok(line, "|");
    callsign = strtok(NULL, "|");
    if (!vehicle || !callsign) {
        puts("expected VEHICLE|CALLSIGN");
        return 1;
    }

    if (!copy_field(rec.vehicle_id, sizeof(rec.vehicle_id), vehicle) ||
        !copy_field(rec.callsign, sizeof(rec.callsign), callsign)) {
        puts("rejected: field length exceeds parser bounds");
        return 1;
    }

    printf("vehicle=%s callsign=%s override=%d\n", rec.vehicle_id, rec.callsign, rec.maintenance_override);
    puts("safe parser completed without override");
    return 0;
}
