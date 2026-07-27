/*
 * Recovered training fragment: civic PA receiver, normalization layer.
 * Transport framing and CRC verification occur before this function.
 */
#include <stdbool.h>
#include <stddef.h>
#include <string.h>

struct warning_fields {
    char callsign[20];
    char zone[12];
    char alert[48];
    char action[48];
    char auth[20];
};

static bool field_present(const char *message, const char *label,
                          const char *value)
{
    const char *cursor = strstr(message, label);
    return cursor != NULL && value[0] != '\0' && strstr(cursor, value) != NULL;
}

/*
 * The dispatcher rotates the AUTH value for every call. The caller has already
 * recovered that value from the final voice burst and supplies it here.
 */
bool warning_message_accept(const char *normalized_message,
                            const struct warning_fields *observed)
{
    if (normalized_message == NULL || observed == NULL)
        return false;

    return strstr(normalized_message, observed->callsign) != NULL
        && field_present(normalized_message, "ZONE ", observed->zone)
        && field_present(normalized_message, "ALERT ", observed->alert)
        && field_present(normalized_message, "ACTION ", observed->action)
        && field_present(normalized_message, "AUTH ", observed->auth);
}
