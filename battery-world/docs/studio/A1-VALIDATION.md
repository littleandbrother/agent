# A1 World Studio validation

Implemented: five navigable views (Study Atlas, World Studio, Experiments,
Knowledge, Evidence), parameterized React Three Fiber assembly, orbit/zoom,
source sample playback, synchronized phase/trace selection, threshold overlays,
energy-based capacitor fill, first-violation navigation, source drawer,
artifact search/export, and responsive/presentation layouts.

The portable HTML embeds the renderer and all 2,803 original A samples.
No source sample is dropped. The independent projection validator compares
every original channel value and validates derived usable energy and fill.

Validation commands:

```sh
./init.sh
corepack pnpm run test:studio
```

Results: 32 Python tests passed, TypeScript SDK and Studio checks passed,
source projection verified, isolated copied HTML opened with all HTTP requests
blocked, 12 browser interaction checks passed, zero page errors, zero network
requests. Screenshots are under `docs/studio/screenshots/`.

The UI never calls a scientific solver or computes PMP/EA/VMS. Phase verdicts
are read from the sealed manifest. F0 golden cases are explicitly labeled
semantic fixtures. A's incomplete physical components, Agent, knowledge,
hardware, and hidden qualification remain absent in this reference.

A-001 bundle identity remains
`sha256:6fa761099b10c9b10060a3636380e5d83221cd95272ee6ac9efa96955ad97059`.

Component geometry is illustrative rather than CAD. Fine-step validation is a
resolution check of the same model, not an independent physical-fidelity claim.
The renderer follows [React Three Fiber](https://r3f.docs.pmnd.rs/) and
[Three.js](https://threejs.org/docs/) APIs, with all dependencies pinned locally.
