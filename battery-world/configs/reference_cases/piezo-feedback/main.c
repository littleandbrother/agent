#include "feedback.h"
/* Reference host controller: schedule relative to actual admitted boot.
 * Volatile state is reset by the apparatus on loss of supply. */
static int phase;
static unsigned sequence;
static double deadline;
void bf_reset(void) { phase=0; sequence=1; deadline=0; }
int bf_step(double t, double dt, double v, int pgood) {
    (void)dt; (void)v; (void)pgood;
    if (phase==0) { deadline=t+0.25; phase=1; }
    if (t+1e-10 >= deadline) {
        if (phase==1) { phase=2; deadline=t+0.010; }
        else if (phase==2) { phase=3; deadline=t+0.004; }
        else { phase=1; ++sequence; deadline=t+4.0; }
    }
    return phase==2 ? BF_SAMPLE : phase==3 ? BF_TX : BF_IDLE;
}
unsigned bf_sequence(void) { return sequence; }
unsigned bf_value(void) { return 2500; }
unsigned bf_checksum(void) { return (sequence ^ bf_value() ^ 0xA5) & 255; }
