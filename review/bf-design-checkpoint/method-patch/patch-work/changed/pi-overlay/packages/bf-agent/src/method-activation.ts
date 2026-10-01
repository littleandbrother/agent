/** Pure post-import method evidence; no SDK/session/provider creation. */
import crypto from "node:crypto";
const ordered = (value: any): any => Array.isArray(value) ? value.map(ordered)
    : value && typeof value === "object" ? Object.fromEntries(Object.keys(value).sort().map(k => [k, ordered(value[k])])) : value;
export const activationDigest = (value: unknown): string => crypto.createHash("sha256").update(JSON.stringify(ordered(value))).digest("hex");
const isHash = (v: unknown): v is string => typeof v === "string" && /^[a-f0-9]{64}$/.test(v);
export function verifyMethodBinding(binding: any, actual: Record<string, string>, manifest: any) {
    if (!binding || binding.schema !== "bf-method-binding-v1") throw new Error("METHOD_BINDING_REQUIRED");
    const body = { ...binding }; delete body.binding_id;
    if (activationDigest(body) !== binding.binding_id) throw new Error("METHOD_BINDING_TAMPER");
    for (const k of ["method_source_sha256", "method_build_sha256", "solver_source_sha256", "solver_build_sha256"])
        if (!isHash(binding[k]) || actual[k] !== binding[k]) throw new Error("METHOD_SOURCE_OR_BUILD_DRIFT:" + k);
    if (manifest.source_files?.["src/method.ts"] !== actual.method_source_sha256
        || manifest.source_files?.["src/solver.ts"] !== actual.solver_source_sha256
        || manifest.loaded_files?.["method.js"] !== actual.method_build_sha256
        || manifest.loaded_modules?.solver !== actual.solver_build_sha256) throw new Error("METHOD_MANIFEST_DRIFT");
    return JSON.parse(JSON.stringify(binding.profile));
}
export function methodEvent(phase: "post_import" | "invoked", entrypoint: string, binding: any, meta: any, output?: unknown) {
    if (!isHash(binding?.binding_id) || !Number.isInteger(meta?.pid) || meta.pid <= 0 || !meta.nonce || !isHash(meta.packet_id)) throw new Error("METHOD_ACTIVATION_CONTEXT");
    if (phase === "invoked" && output === undefined) throw new Error("METHOD_INVOCATION_OUTPUT_REQUIRED");
    return JSON.parse(JSON.stringify({ type: "method_activation", phase, entrypoint, method_binding_id: binding.binding_id,
        profile: binding.profile, pid: meta.pid, nonce: meta.nonce, packet_id: meta.packet_id,
        output: phase === "invoked" ? output : null,
        output_hash: phase === "invoked" ? activationDigest(output) : null }));
}
export function verifyMethodActivation(events: any[], binding: any, expected: any) {
    if (!expected || !Number.isInteger(expected.pid) || expected.pid <= 0 || !Number.isInteger(expected.author_pid) || expected.author_pid <= 0 || typeof expected.nonce !== "string" || !expected.nonce.trim() || !isHash(expected.packet_id) || expected.exit_code !== 0 || expected.pid === expected.author_pid || expected.fresh_process !== true || expected.clean_context !== true) throw new Error("METHOD_PROCESS_NOT_QUALIFIED");
    const rows = events.filter(e => e.type === "method_activation");
    if (rows.length !== 2 || rows[0].phase !== "post_import" || rows[0].entrypoint !== "solver.method"
        || rows[1].phase !== "invoked" || rows[1].entrypoint !== "solver.solverPrompt") throw new Error("METHOD_POST_IMPORT_INVOCATION_REQUIRED");
    for (const row of rows) {
        if (row.pid !== expected.pid || row.nonce !== expected.nonce || row.packet_id !== expected.packet_id
            || row.method_binding_id !== binding.binding_id || activationDigest(row.profile) !== activationDigest(binding.profile)) throw new Error("METHOD_ACTIVATION_BINDING_MISMATCH");
    }
    if (typeof rows[1].output !== "string" || !rows[1].output || rows[1].output_hash !== activationDigest(rows[1].output)) throw new Error("METHOD_ACTIVATION_OUTPUT_TAMPER");
    return { method_binding_id: binding.binding_id, prompt_hash: rows[1].output_hash,
        profile: JSON.parse(JSON.stringify(binding.profile)), post_import: true, invoked: true,
        execution_authorized: false, scientific_success: false };
}
