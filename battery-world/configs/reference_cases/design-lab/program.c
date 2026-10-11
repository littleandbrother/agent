/* D5 application core, compiled unchanged for host and Cortex-M4.
 * PGOOD qualifies entry from WAIT; it is not the SoC brownout detector.
 * Source: LTC3588-1 Table1/PGOOD; nRF52832 operating VDD1.7..3.6V.
 * The conservative 1.8V reset and complete BOOT/INIT/TX stage workloads
 * are preserved. Currents/timings are envelope assumptions, not a measured SoC.
 */
#include <stdint.h>
#include "policy.h"
enum {RESET,BOOT,WAIT,INIT,TX,SLEEP};
static int state=RESET;
/* The SIL clock is a frozen 100us tick. Accumulating binary floating-point
 * milliseconds can add a spurious tick to a complete workload. The host and
 * target application core use the same integer microsecond stage clock. */
static uint32_t elapsed_us=0;
static int submitted=0;
void bf_reset(void){state=RESET;elapsed_us=0;submitted=0;}
int bf_state(void){return state;}
double bf_current_mA(void){
    const double currents[]={RESET_MA,BOOT_MA,SLEEP_MA,INIT_MA,TX_MA,SLEEP_MA};
    return currents[state];
}
int bf_step(double dt_ms,double supply,double pgood){
    if(supply<1.8){bf_reset();return 0;}
    if(state==RESET){state=BOOT;elapsed_us=0;return 0;}
    elapsed_us+=(uint32_t)(dt_ms*1000.0+0.5);
    switch(state){
    case BOOT:if(elapsed_us>=(uint32_t)(BOOT_MS*1000.0+0.5)){state=WAIT;elapsed_us=0;}break;
    case WAIT:if(pgood>=2.5){state=INIT;elapsed_us=0;}break;
    case INIT:if(elapsed_us>=(uint32_t)(INIT_MS*1000.0+0.5)){state=TX;elapsed_us=0;}break;
    case TX:if(elapsed_us>=(uint32_t)(TX_MS*1000.0+0.5)){state=SLEEP;elapsed_us=0;submitted=1;return 1;}break;
    case SLEEP:if(BEACON_MODE && submitted && elapsed_us>=(uint32_t)((INTERVAL_MS-TX_MS)*1000.0+0.5)){state=TX;elapsed_us=0;}break;
    }
    return 0;
}
void bf_payload(uint8_t *out){
    const uint8_t bytes[12]={'B','F','D','2',1,2,3,4,5,6,7,8};
    for(int i=0;i<12;i++)out[i]=bytes[i];
}

void bf_event(uint32_t id,uint8_t kind){(void)id;(void)kind;}
