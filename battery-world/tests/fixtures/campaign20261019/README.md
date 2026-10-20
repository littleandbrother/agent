# Portable campaign test fixtures

`ar-reference.zip` contains the exact archived 17-case reference (81 sealed files plus its seal) and the original stale-failure receipt. It is a compressed read-only fixture, not a new simulation or live runtime. `ar-reference.json` records its checksum and scope. Tests extract it only into a temporary directory and run the unchanged independent readback.

The E4 tests copy only their small allowlisted frozen inputs into a temporary source fixture and register a separate unit-test profile with every model/native capability disabled. Production resource and identity gates remain unchanged.

The two historical Pi phase1 transport scripts are excluded from automatic Biome rewrites so their experimentally frozen bytes remain intact; they still participate in TypeScript and dependency checks.

`phase3-initial-cache.zip` preserves the original initial cache and its 40 allowlisted response artifacts (about 2 MB uncompressed). Tests verify their saved bytes and write a separate temporary path projection. Response values and input identities stay unchanged. This lets group-budget and reuse checks consume the existing exact-input results without reading private home directories or running those successful simulations again. A/R test output is likewise confined to temporary directories; the original runtime is never used by these unit tests.
