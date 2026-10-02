/* Shared host/ARM policy core. Timings/currents are model inputs, not cycle measurements.
 * PGOOD is status only. RESET and WAIT still draw current from the supply.
 * Radio adapter must call this with observed power and completion, not invent reception.
 */
#include <stdint.h>
#include "policy.h"
enum {RESET,BOOT,WAIT,INIT,TX,SLEEP};
static int state=RESET;
static double elapsed=0;
void bf_reset(void){state=RESET;elapsed=0;}
int bf_state(void){return state;}
double bf_current_mA(void){
    const double currents[]={RESET_MA,BOOT_MA,SLEEP_MA,INIT_MA,TX_MA,SLEEP_MA};
    return currents[state];
}
int bf_step(double dt_ms,double supply,double pgood){
    /* Brownout clears partial radio progress before considering completion. */
    if(supply<1.8){bf_reset();return 0;}
    if(state==RESET){state=BOOT;elapsed=0;return 0;}
    if((state==INIT || state==TX || state==SLEEP) && pgood<2.5){state=WAIT;elapsed=0;return 0;}
    elapsed+=dt_ms;
    switch(state){
    case BOOT:if(elapsed>=BOOT_MS){state=WAIT;elapsed=0;}break;
    case WAIT:if(pgood>=2.5){state=INIT;elapsed=0;}break;
    case INIT:if(elapsed>=INIT_MS){state=TX;elapsed=0;}break;
    case TX:if(elapsed>=TX_MS){state=SLEEP;elapsed=0;return 1;}break;
    case SLEEP:if(elapsed>=INTERVAL_MS-TX_MS){state=TX;elapsed=0;}break;
    }
    return 0;
}
void bf_payload(uint8_t *out){
    const uint8_t bytes[12]={'B','F','D','2',1,2,3,4,5,6,7,8};
    for(int i=0;i<12;i++)out[i]=bytes[i];
}
