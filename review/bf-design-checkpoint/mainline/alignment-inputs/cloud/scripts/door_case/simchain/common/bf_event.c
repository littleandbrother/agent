#include "bf_event.h"
#ifndef BF_CONFIG_ID
#define BF_CONFIG_ID "unconfigured"
#endif
const char bf_program_config_id[] = BF_CONFIG_ID;
#ifndef BF_ADV_INTERVAL_US
#define BF_ADV_INTERVAL_US 100000u
#endif
void bf_encode_event(uint32_t id0, uint32_t id1, uint8_t out[12]) {
    unsigned i;
    out[0]='B'; out[1]='F'; out[2]='D'; out[3]='2';
    for(i=0;i<4;i++) {out[4+i]=(uint8_t)(id0>>(8*i));out[8+i]=(uint8_t)(id1>>(8*i));}
}
int bf_should_start(int pgood) {return pgood != 0;}
uint32_t bf_advertising_interval_us(void) {return BF_ADV_INTERVAL_US;}
