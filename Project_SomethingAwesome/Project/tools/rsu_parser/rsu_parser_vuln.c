#include <stdio.h>
#include <string.h>

typedef struct {
    char vehicle_id[12];
    char callsign[16];
    int maintenance_override;
} telemetry_record;

static void parse_field(char *dst, const char *src) {
    /* Deliberately unsafe for local CTF training. */
    strcpy(dst, src);
}

int main(int argc, char **argv) {
    char line[512];
    char *vehicle;
    char *callsign;
    FILE *fp;
    telemetry_record rec;

    memset(&rec, 0, sizeof(rec));

    if (argc != 2) {
        puts("usage: rsu_parser_vuln <frame-file>");
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

    parse_field(rec.vehicle_id, vehicle);
    parse_field(rec.callsign, callsign);

    printf("vehicle=%s callsign=%s override=%d\n", rec.vehicle_id, rec.callsign, rec.maintenance_override);
    if (rec.maintenance_override == 0x6841) {
        puts("diagnostic path reached (retired research module)");
    }
    return 0;
}
