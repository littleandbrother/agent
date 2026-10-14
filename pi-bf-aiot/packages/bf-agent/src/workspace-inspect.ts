import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { defineTool } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

export function workspaceInspect(
	root: string,
	args: {
		action: string;
		path?: string;
		paths?: string[];
		fields?: string[];
		decode_field?: string;
		query?: string;
		limit?: number;
	},
) {
	const base = fs.realpathSync(root);
	if (args.action === "inspect") fs.mkdirSync(path.join(base, "scratch"), { recursive: true });
	const file = (name: string) => {
		const relative = name.split(/[\\/]/);
		const target = path.resolve(base, name);
		if (
			relative.some((s) => ["..", ".pi"].includes(s)) ||
			!target.startsWith(base + path.sep) ||
			!fs.statSync(target).isFile() ||
			fs.realpathSync(target) !== target
		)
			throw Error("WORKSPACE_FILE_REQUIRED");
		if (fs.statSync(target).size > 128 * 1024 * 1024) throw Error("WORKSPACE_FILE_TOO_LARGE");
		return target;
	};
	if (args.action === "inspect")
		return {
			workspace: base,
			scratch: "scratch",
			hash: "bf_workspace action=hash paths=[...]",
			json: "bf_workspace action=json path=... fields=[dot.paths]",
			search: "bf_workspace action=search paths=[...] query=literal",
			shell: "Use workspace-relative paths; Python hashlib is portable.",
		};
	const names = args.paths ?? (args.path ? [args.path] : []);
	if (!names.length || names.length > 24) throw Error("WORKSPACE_EXPLICIT_PATHS_REQUIRED");
	const inputs = names.map((name) => {
		const bytes = fs.readFileSync(file(name));
		return {
			path: name,
			sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
			bytes: bytes.length,
			raw: bytes,
		};
	});
	if (args.action === "hash") return { files: inputs.map(({ raw: _raw, ...reference }) => reference) };
	const select = (value: unknown, fields: string[]) =>
		Object.fromEntries(
			fields.map((field) => {
				if (!/^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$/.test(field)) throw Error("WORKSPACE_FIELD_INVALID");
				let node: unknown = value;
				for (const part of field.split(".")) {
					if (node === null || typeof node !== "object" || !(part in node)) {
						const keys = node && typeof node === "object" ? Object.keys(node).slice(0, 40) : [];
						throw Error(`WORKSPACE_FIELD_NOT_FOUND:${field}; available=${JSON.stringify(keys)}`);
					}
					node = (node as Record<string, unknown>)[part];
				}
				return [field, node];
			}),
		);
	if (args.action === "json") {
		if (inputs.length !== 1 || !args.fields?.length || args.fields.length > 24 || inputs[0].bytes > 8 * 1024 * 1024)
			throw Error("WORKSPACE_JSON_FIELDS_REQUIRED");
		let value: unknown = JSON.parse(inputs[0].raw.toString("utf8"));
		if (args.decode_field) {
			const encoded = select(value, [args.decode_field])[args.decode_field];
			if (typeof encoded !== "string") throw Error("WORKSPACE_DECODE_STRING_REQUIRED");
			value = JSON.parse(encoded);
		}
		const { raw: _raw, ...reference } = inputs[0];
		const result = { reference, fields: select(value, args.fields) };
		if (Buffer.byteLength(JSON.stringify(result)) > 8000)
			throw Error("WORKSPACE_FIELDS_TOO_LARGE: select narrower fields");
		return result;
	}
	if (args.action !== "search" || !args.query || args.query.length > 256)
		throw Error("WORKSPACE_SEARCH_LITERAL_REQUIRED");
	if (inputs.some((entry) => entry.bytes > 8 * 1024 * 1024)) throw Error("WORKSPACE_SEARCH_TOO_LARGE");
	const limit = args.limit ?? 12;
	if (!Number.isInteger(limit) || limit < 1 || limit > 40) throw Error("WORKSPACE_SEARCH_LIMIT_INVALID");
	return {
		files: inputs.map(({ raw, ...reference }) => {
			const matches = raw
				.toString("utf8")
				.split(/\r?\n/)
				.flatMap((line, i) => (line.includes(args.query!) ? [{ line: i + 1, text: line.slice(0, 600) }] : []));
			return {
				...reference,
				total_matches: matches.length,
				matches: matches.slice(0, limit),
				more: matches.length > limit,
			};
		}),
	};
}

export function workspaceTool(root: string, reply: (value: unknown) => unknown) {
	return defineTool({
		name: "bf_workspace",
		label: "Workspace fields",
		executionMode: "sequential",
		description:
			"Inspect writable workspace/scratch, batch SHA256 files, select JSON dot fields or search literal text with source lines. decode_field parses a nested JSON string once. Returns exact input hash and bounded results; no shell commands.",
		parameters: Type.Object(
			{
				action: Type.Union(["inspect", "hash", "json", "search"].map((x) => Type.Literal(x))),
				path: Type.Optional(Type.String()),
				paths: Type.Optional(Type.Array(Type.String())),
				fields: Type.Optional(Type.Array(Type.String())),
				decode_field: Type.Optional(Type.String()),
				query: Type.Optional(Type.String()),
				limit: Type.Optional(Type.Integer()),
			},
			{ additionalProperties: false },
		),
		async execute(_id, args) {
			return reply(workspaceInspect(root, args)) as {
				content: { type: "text"; text: string }[];
				details: Record<string, unknown>;
			};
		},
	});
}
