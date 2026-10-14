import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

/** One bounded view and an exact, field-readable original. */
export function boundedToolReply(root: string, value: unknown) {
	const text = JSON.stringify(value);
	if (Buffer.byteLength(text) <= 8000) return { content: [{ type: "text" as const, text }], details: {} };
	const digest = crypto.createHash("sha256").update(text).digest("hex");
	const base = fs.realpathSync(root);
	const folder = path.join(base, "tool-records");
	if (fs.existsSync(folder) && (fs.lstatSync(folder).isSymbolicLink() || fs.realpathSync(folder) !== folder))
		throw Error("TOOL_RECORD_PATH_DENIED");
	fs.mkdirSync(folder, { recursive: true });
	const target = path.join(folder, `${digest}.json`);
	if (
		fs.existsSync(target) &&
		(fs.lstatSync(target).isSymbolicLink() ||
			crypto.createHash("sha256").update(fs.readFileSync(target)).digest("hex") !== digest)
	)
		throw Error("TOOL_RECORD_CONFLICT");
	if (!fs.existsSync(target)) fs.writeFileSync(target, text, { flag: "wx" });
	const object = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
	const summary: Record<string, unknown> = {
		record_file: path.relative(base, target),
		sha256: digest,
		bytes: Buffer.byteLength(text),
		available_fields: Object.keys(object).slice(0, 40),
		instruction: "Use bf_workspace json path=record_file fields=[...] for exact fields; search for source lines.",
	};
	for (const name of [
		"schema_version",
		"id",
		"status",
		"revision",
		"task_id",
		"design_id",
		"parent",
		"check_id",
		"submission_id",
		"hashes",
		"working_design",
		"current_design",
		"selected_jobs",
		"open_gates",
		"error",
	])
		if (
			name in object &&
			Buffer.byteLength(JSON.stringify(object[name])) < 2400 &&
			Buffer.byteLength(JSON.stringify({ ...summary, [name]: object[name] })) < 7000
		)
			summary[name] = object[name];
	if (object.acceptance && typeof object.acceptance === "object") {
		const acceptance = object.acceptance as Record<string, unknown>;
		const gates = Array.isArray(acceptance.functional_gates) ? acceptance.functional_gates : [];
		summary.acceptance = {
			digital_engineering_status: acceptance.digital_engineering_status,
			file_integrity: acceptance.file_integrity,
			full_product_passed: acceptance.full_product_passed,
			physical_validation: acceptance.physical_validation,
			functional_gates: gates.map((g: Record<string, unknown>) => ({ id: g.id, status: g.status })),
		};
		if (Buffer.byteLength(JSON.stringify(summary)) > 7600) delete summary.acceptance;
	}
	for (const name of ["messages", "checks", "jobs", "files", "artifacts"])
		if (Array.isArray(object[name])) summary[`${name}_count`] = object[name].length;
	return { content: [{ type: "text" as const, text: JSON.stringify(summary) }], details: {} };
}
