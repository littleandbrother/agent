# A Rotary World Kernel protocol

The public mission starts from an unclamped storage design. The deterministic
baseline must exceed the maximum safe voltage. A typed revision adds a shunt
clamp. The revised coarse simulation and an independently recomputed finer-step
simulation must pass all mission constraints and agree within the frozen peak
voltage tolerance.

Required checks:

1. baseline overvoltage is observed;
2. the revision is recorded before revised execution;
3. revised and fine phases pass;
4. all three consumers bind the same event head;
5. a killed process resumes without changing the scientific hash;
6. replay reproduces the bundle hash;
7. byte or hash-chain tampering fails;
8. no Agent/model call occurs.

