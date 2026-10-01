#ifndef BF_EVENT_H
#define BF_EVENT_H
#include <stdint.h>
void bf_encode_event(uint32_t id0, uint32_t id1, uint8_t out[12]);
int bf_should_start(int pgood);
uint32_t bf_advertising_interval_us(void);
#endif
