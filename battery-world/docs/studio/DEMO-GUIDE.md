# Battery World Studio — demonstration route

Start from the repository root:

```sh
./init.sh
corepack pnpm run studio
```

Open `http://127.0.0.1:8766`. The standalone `apps/world-studio/dist/index.html`
can also be copied alone and opened offline. It embeds source data, React,
Three.js and styles; no CDN or service is required for replay. Live experiments
are disabled offline.

## Five-minute demonstration

1. **Study atlas**: see the frozen reference, actual roadmap and coverage. The
   green banner opens the new coupled mission and knowledge story.
2. **Coupled mission → TX brownout → Jump to event**: inspect capacitor energy,
   terminal voltage, PMIC/MCU states, prediction disagreement and interrupted TX.
   Switch to Wrong diagnosis and Receiver loss to distinguish information from
   energy and communication outcomes. Drag the cursor and orbit the 3D assembly.
3. **Experiments**: record a prediction, run the small-capacitor design, increase
   storage, and execute again. These call the actual local solver. Each operation
   has a durable identity and cost receipt; it is marked human intervention.
4. **Knowledge → Failure & interventions**: compare removing ESR, lowering TX
   demand and increasing storage. Inspect the program and its declared scope.
5. **Qualification**: the explanation test passes but the whole-use test fails.
   Then open Reuse & removal; removing the capsule changes the first task from one
   to five reference experiments. Keep the unsolved fourth task visible.

Do not describe this as an autonomous scientific Agent or RSI demonstration.
It is a reproducible computational apparatus and a guided reference study.
The 3D geometry is schematic, not CAD, and all present observations are simulated.

## Verification

```sh
corepack pnpm run test:studio
node apps/world-studio/live-test.mjs
```

Offline browser checks block all HTTP requests. Live checks use a fresh temporary
broker, run a failing and then passing design, check recorded costs, deny
cross-origin mutations and hidden profiles, and verify the repository is not
served. Screenshots and machine reports are in `docs/studio/`.
