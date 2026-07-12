#include <stdbool.h>
#include <stdio.h>
#include <string.h>

typedef bool (*command_handler)(const char *argument);

typedef struct {
    const char *name;
    command_handler handler;
    bool release_allowed;
} command_entry;

static bool status_handler(const char *argument) {
    (void)argument;
    puts("RSU status nominal");
    return true;
}

static bool radio_diag_handler(const char *argument) {
    (void)argument;
    puts("FHSS profile TOLL-LPI-TRAINING-03, preamble 0xA7D5, sync 0xC35A");
    return true;
}

static bool maint_unlock_handler(const char *argument) {
    if (strcmp(argument, "TRAINING_ONLY_HMAC_KEY_CHANGE_ME") == 0) {
        puts("CTF{FIRMWARE_REVEALS_THE_TRUST_BOUNDARY}");
        return true;
    }
    puts("denied");
    return false;
}

static const command_entry COMMANDS[] = {
    {"status", status_handler, true},
    {"radio_diag", radio_diag_handler, true},
    {"unlock_maint_diag", maint_unlock_handler, false},
};

int main(int argc, char **argv) {
    if (argc != 3) {
        puts("usage: rsu_firmware_stub <command> <argument>");
        return 1;
    }
    for (unsigned i = 0; i < sizeof(COMMANDS) / sizeof(COMMANDS[0]); i++) {
        if (strcmp(argv[1], COMMANDS[i].name) == 0) {
            return COMMANDS[i].handler(argv[2]) ? 0 : 2;
        }
    }
    puts("unknown command");
    return 3;
}
