# Modifications to Run API Gateway

This directory contains a **modified version** of

> **Run API Gateway** — https://github.com/easyeda/eext-run-api-gateway
>
> - Copyright 2024 JLCEDA `<support[#]lceda.cn>`
> - Licensed under the Apache License, Version 2.0 (see [LICENSE](LICENSE))

Notice of changes required by **Apache License 2.0, section 4(b)**. The upstream `LICENSE` and all copyright notices are retained unmodified.

- **Base:** upstream `1.0.5`, commit [`479d9b3`](https://github.com/easyeda/eext-run-api-gateway/commit/479d9b3e58d105229dc00f914c0871700a9f04df)
- **This version:** `1.2.0-eritque-arcus.1`
- **Extension uuid:** unchanged (`bded3619ce6a4e60...`), so installing this build replaces an installed upstream Run API Gateway rather than coexisting with it

Modified: `src/index.ts` (520 -> 692 lines, +206 / -34), `extension.json`, `CHANGELOG.md`, `package.json`, `tsconfig.json`, `.edaignore`. Added: `CHANGES.md`, `pnpm-lock.yaml`, `pnpm-workspace.yaml`. Removed: `package-lock.json`. Everything else is upstream's, byte for byte. To reproduce the comparison from the repo root:

```bash
curl -sL https://github.com/easyeda/eext-run-api-gateway/archive/479d9b3e58d105229dc00f914c0871700a9f04df.tar.gz | tar xz -C /tmp
diff -ru --exclude=node_modules --exclude=dist /tmp/eext-run-api-gateway-479d9b3*/ eext/
```

## `src/index.ts`

- `execute` accepts `timeoutMs`; `resolveExecuteTimeout()` clamps it to 600 s and the applied value is echoed back.
- Envelopes over `RESULT_CHUNK_THRESHOLD` (512 KB) are split by `sendEnvelope()` into `RESULT_CHUNK_SIZE` (256 KB) frames, reassembled by `(id, seq)`:
  ```jsonc
  { "type": "result_chunk", "id": "...", "seq": 0, "total": 7, "data": "..." }
  ```
- The `error` envelope carries `stack`.
- Results that are not JSON-representable (`ArrayBuffer`, `Blob`) are base64-encoded into an `__edaBinary` envelope.
- `RETRY_MAX_DELAY_MS` (30 s) caps a backoff that continues past `MAX_RETRIES` instead of stopping; the last working port is cached under `lastGoodPort` and tried first.
- Circular references and `BigInt` are handled during result serialization.
- File header carries the section 4(b) modification notice.

## `extension.json`

- `version`: `1.0.5` -> `1.2.0-eritque-arcus.1`
- `description`: notes the fork
- `publisher`: `EasyEDA` -> `Eritque arcus`; `repository` and `homepage` still point at upstream

## `CHANGELOG.md`

- Upstream entries removed; carries this fork's entries only.

## `package.json` / `tsconfig.json` / `.edaignore` / lockfile

Toolchain only — no change to what gets bundled or how esbuild is configured.

- Package manager: npm -> pnpm. `package-lock.json` removed, `pnpm-lock.yaml` + `pnpm-workspace.yaml` added, `build` script calls `pnpm run compile` instead of `npm run compile`.
- devDependencies bumped (`@antfu/eslint-config` 5 -> 9, `eslint` 9 -> 10, `esbuild` 0.24 -> 0.28, `lint-staged` 16 -> 17, `@jlceda/pro-api-types` 0.2 -> 0.4, patch bumps elsewhere).
- `@types/node` added: previously hoisted into a flat `node_modules` by npm, pnpm's strict layout does not expose it, so `import process from 'node:process'` in `config/esbuild.prod.ts` no longer type-resolved.
- New `typecheck` script (`tsc --noEmit`) — upstream had none.

### TypeScript 7 + 6 side by side

`typescript` `^5.7.3` -> two entries, following [Microsoft's documented layout](https://devblogs.microsoft.com/typescript/announcing-typescript-7-0/#running-side-by-side-with-typescript-6.0):

```jsonc
{
	"@typescript/native": "npm:typescript@^7.0.2", // bin: tsc  — the type checker
	"typescript": "npm:@typescript/typescript6@~6.0.2" // bin: tsc6 — the JS compiler API
}
```

TS 7.0 is the native (Go) compiler and ships **no programmatic API** — `require('typescript')` exposes 2 keys and `ts.sys` is `undefined`; a new API is expected in 7.1. Everything that embeds the compiler therefore has to load TS 6:

- `ts-node` (runs `config/esbuild.prod.ts` and `build/packaged.ts`) dies with `TypeError: Cannot read properties of undefined (reading 'fileExists')`.
- `typescript-eslint` refuses to load at all (`does not support TS 7.0`); its peer range is `>=4.8.4 <6.1.0`, tracked in typescript-eslint#10940. Hence the tilde on the 6.x entry.

Installing TS 6 under the name `typescript` is what makes both work — they resolve it by name — while `tsc` on `PATH` stays TS 7. (`@typescript/typescript6@6.0.2` is the alias package's own version counter; the compiler inside reports `6.0.3`.) Type checking itself runs on 7.0: `pnpm run typecheck` is ~0.5 s and clean. Collapse this back to a single `typescript` entry once typescript-eslint supports >=7.1.

### `tsconfig.json`

- `module` `CommonJS` -> `Node18`, `moduleResolution` `Node10` -> `Node16`: TS 7.0 **removed** node10 (`error TS5108`, deprecated in 6.0). Emit is unchanged in practice — no `"type": "module"` in `package.json`, so these files still emit CJS and `ts-node` still requires them.
- `"types": ["node"]`: TS 6.0 stopped auto-including every `node_modules/@types/*` package — `getAutomaticTypeDirectiveNames` now requires `types` to be set (`["*"]` restores the old wildcard).
- `"skipLibCheck": true`: `@jlceda/pro-api-types` is pulled in whole by `include` and reports 23 errors on its own `.d.ts` (needs `@types/react`, and its `Text` / `Image` collide with `lib.dom`). Pre-existing and never surfaced, since upstream has no typecheck script.

### `.edaignore`

- `/pnpm-lock.yaml` + `/pnpm-workspace.yaml` added next to upstream's `/package-lock.json` rule — after the npm -> pnpm switch the lockfile was being shipped inside the `.eext` (566 KB -> 521 KB).

`pnpm run lint` also required `shellEmulator: true` + `trustPolicy: no-downgrade` in `pnpm-workspace.yaml` and one `setTimeout(fn, ms, ...args)` rewrite in `src/index.ts` (`e18e/prefer-timer-args`), both from the newer `@antfu/eslint-config`.

## Not changed

Port scanning (49620-49629), handshake, heartbeat, menu/UI, i18n, storage keys, esbuild config.

## Building

```bash
cd eext && pnpm install && pnpm run build   # -> build/dist/*.eext
```

`npm` also works for installing, but the `build` script shells out to `pnpm`.

Then in EasyEDA Pro: 扩展 -> 导入 -> pick the `.eext`, then click `API Gateway -> Reconnect` once.
