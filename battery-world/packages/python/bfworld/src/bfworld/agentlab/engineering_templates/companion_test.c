#include <assert.h>
#include <stdio.h>
#include "companion_logic.h"
int main(void){
 companion s={READY,0,0};
 step(&s,0,1,1);step(&s,10,0,1);assert(!s.led&&s.phase==READY);
 step(&s,20,1,1);step(&s,49,1,1);assert(!s.led);
 step(&s,50,1,1);assert(s.led);
 step(&s,50+COMPANION_PULSE_MS-1,1,1);assert(s.led);step(&s,50+COMPANION_PULSE_MS,1,1);assert(!s.led);
 step(&s,10000,1,1);assert(!s.led&&s.phase==WAIT_RELEASE);
 step(&s,10001,0,1);step(&s,10031,0,1);assert(s.phase==READY);
 step(&s,10040,1,1);step(&s,10070,1,1);assert(s.led);
 step(&s,10071,1,0);assert(!s.led&&s.phase==WAIT_RELEASE);
 s=(companion){DEBOUNCE,UINT32_MAX-10,0};step(&s,20,1,1);assert(s.led);
 puts("PASS: debounce, pulse duration, held press, release, power loss, timer wrap");
}
