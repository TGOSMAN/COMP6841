//
// Created by User on 22/07/2026.
//

#include "MyEmbeddedAlarmSystem.h"
#include <stdlib.h>
#include <stdint.h>


#define CODE_WORD 0x55
#define EMERGENCY_SIGNAL 0xB
#define EMERGENCY_BITS 4U



/*Recover The Alarm Message From The Interleaving Process*/
uint8_t AlarmDecoder(uint32_t packet)
{
    uint32_t inputMask = UINT32_C(1) << 31;
    uint8_t outputMask = 1U;
    uint8_t emergency = 0U;
    uint8_t pairCount = 0U;
    uint8_t recovered = 0U;

    for (uint8_t dataCount = 0U; dataCount < 16U; ++dataCount) {
        if ((packet & inputMask) != 0U) {
            ++pairCount;
        }

        inputMask >>= 1;

        if ((pairCount == 2U) && (recovered < 4U)) {
            if ((packet & inputMask) != 0U) {
                emergency |= outputMask;
            }

            outputMask <<= 1;
            ++recovered;
            pairCount = 0U;

            inputMask >>= 1;
        }
    }

    while (recovered < 4U) {
        if ((packet & inputMask) != 0U) {
            emergency |= outputMask;
        }

        inputMask >>= 1;
        outputMask <<= 1;
        ++recovered;
    }

    return emergency;
}

uint8_t AlarmCheck(uint32_t packet) {
    uint8_t message = AlarmDecoder(packet);
    uint8_t emergency = 0;
    if (message == EMERGENCY_SIGNAL) {
        emergency = 1U;
    }
    return emergency;
}
