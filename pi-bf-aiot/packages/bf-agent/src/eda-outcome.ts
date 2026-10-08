/** A native check can validly report a bad design. This is different from a CLI
 * invocation that failed (which must not appear as a successful tool execution). */
export function assertEdaExecution(value: any) {
	if (!value || ["QUEUED", "RUNNING"].includes(value.status)) return value;
	const result = value.result;
	let native: any;
	if (typeof result?.stdout === "string") {
		try {
			native = JSON.parse(result.stdout);
		} catch {
			/* Text help/check output is also valid. */
		}
	}
	const failed =
		value.status === "FAILED" ||
		value.status === "CANCELLED" ||
		(typeof result?.exit_code === "number" && result.exit_code !== 0) ||
		native?.ok === false;
	if (failed) {
		throw new Error(
			JSON.stringify({
				error: "EDA_EXECUTION_FAILED",
				job_id: value.id,
				status: value.status,
				exit_code: result?.exit_code,
				receipt_path: result?.receipt_path,
				receipt_sha256: result?.receipt_sha256,
				detail: value.error ?? native?.error ?? result?.stderr?.slice(0, 3000) ?? null,
				stdout_excerpt: result?.stdout?.slice(0, 1500),
				partial_effects_possible: true,
			}),
		);
	}
	// In particular native.result.passed=false is evidence, not a transport error.
	return value;
}
