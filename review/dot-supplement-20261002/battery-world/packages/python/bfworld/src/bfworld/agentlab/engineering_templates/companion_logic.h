#ifndef COMPANION_LOGIC_H
#define COMPANION_LOGIC_H
#include <stdint.h>
#ifndef COMPANION_PULSE_MS
#define COMPANION_PULSE_MS 100
#endif
enum phase { READY, DEBOUNCE, PULSE, WAIT_RELEASE, RELEASE_DEBOUNCE };
typedef struct { enum phase phase; uint32_t since; uint8_t led; } companion;
/* One response per stable press; time subtraction is safe across uint32 wrap. */
static inline void step(companion *s, uint32_t now, int pressed, int power_ok) {
    if (!power_ok) { s->phase=WAIT_RELEASE; s->led=0; return; }
    switch(s->phase) {
    case READY: if(pressed){s->phase=DEBOUNCE;s->since=now;} break;
    case DEBOUNCE:
        if(!pressed)s->phase=READY;
        else if((uint32_t)(now-s->since)>=30){s->phase=PULSE;s->since=now;s->led=1;}
        break;
    case PULSE:
        if((uint32_t)(now-s->since)>=COMPANION_PULSE_MS){s->led=0;s->phase=WAIT_RELEASE;}
        break;
    case WAIT_RELEASE: if(!pressed){s->phase=RELEASE_DEBOUNCE;s->since=now;} break;
    case RELEASE_DEBOUNCE:
        if(pressed)s->phase=WAIT_RELEASE;
        else if((uint32_t)(now-s->since)>=30)s->phase=READY;
        break;
    }
}
#endif
