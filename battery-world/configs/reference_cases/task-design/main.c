#include <stdio.h>
/* Deterministic reference controller. Times and current envelopes are in the task. */
int main(void) {
    puts("t_s,duration_s,state,seq,value,crc");
    for (unsigned seq = 1; seq <= 4; ++seq) {
        double start = 4.0 + 5.0 * (seq - 1);
        unsigned value = 2500;
        unsigned crc = (seq ^ value ^ 0xA5) & 255;
        printf("%.6f,0.010000,sample,%u,%u,%u\n", start, seq, value, crc);
        printf("%.6f,0.004000,tx,%u,%u,%u\n", start + 0.011, seq, value, crc);
    }
    return 0;
}
