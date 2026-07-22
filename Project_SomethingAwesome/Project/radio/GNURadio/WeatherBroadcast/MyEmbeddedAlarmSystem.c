//
// Created by User on 22/07/2026.
//

#include "MyEmbeddedAlarmSystem.h"
#include <stdlib.h>
#include <stddef.h>
#include <stdint.h>
#include <tmmintrin.h>   // SSSE3
#include <smmintrin.h>   // SSE4.1
#include <nmmintrin.h>   // SSE4.2
#include <stdio.h>


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


int main(int argc, char *argv[]) {
    // uint8_t emergency
    uint8_t emergency;
    //THESE SHOULD ALL BE WITH EMERGENCY == 0xF
    uint32_t test1 = 0x0000F000;
    uint32_t test2 = 0x0001F000;
    uint32_t test3 = 0xFFFFF000;
    uint32_t test4 = 0xB5AD6000;
    uint32_t test5 = 0x0003F000;
    uint32_t test6 = 0x131D3000;

    // THESE SHOULD ALL RETURN EMERGENCY == 0xA
    uint32_t test7 = 0x00005000; // No 1-pairs; all alarm bits collected afterward
    uint32_t test8 = 0x00035000; // One 1-pair; one alarm bit interleaved
    uint32_t test9 = 0xAB65D000; // Many 1-pairs; all alarm bits interleaved
    emergency = AlarmSent(test1);
    printf("TEST 1: %x, EMERGENCY: %x\n", test1, emergency);
    emergency = AlarmSent(test2);
    printf("TEST 2: %x, EMERGENCY: %x\n", test2, emergency);
    emergency = AlarmSent(test3);
    printf("TEST 3: %x, EMERGENCY: %x\n", test3, emergency);
    emergency = AlarmSent(test4);
    printf("TEST 4: %x, EMERGENCY: %x\n", test4, emergency);
    emergency = AlarmSent(test5);
    printf("TEST 5: %x, EMERGENCY: %x\n", test5, emergency);
    emergency = AlarmSent(test6);
    printf("TEST 6: %x, EMERGENCY: %x\n", test6, emergency);
    emergency = AlarmSent(test7);
    printf("TEST 7: %x, EMERGENCY: %x\n", test7, emergency);
    emergency = AlarmSent(test8);
    printf("TEST 8: %x, EMERGENCY: %x\n", test8, emergency);
    emergency = AlarmSent(test9);
    printf("TEST 9: %x, EMERGENCY: %x\n", test9, emergency);

    return 0;
}
