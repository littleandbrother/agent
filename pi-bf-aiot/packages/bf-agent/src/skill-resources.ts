import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import type { Skill } from "@earendil-works/pi-coding-agent";

interface Entry {
	id: string;
	description: string;
	path: string;
	sha256: string;
	version: string;
	plugin_id: string;
}
interface Manifest {
	schema_version: string;
	sha256: string;
	files: Record<string, string>;
	skills: Entry[];
}

function canonical(value: unknown): string {
	if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
	if (value !== null && typeof value === "object") {
		const object = value as Record<string, unknown>;
		return `{${Object.keys(object)
			.sort()
			.map((key) => `${JSON.stringify(key)}:${canonical(object[key])}`)
			.join(",")}}`;
	}
	return JSON.stringify(value);
}

export function startupSkillIds(
	skills: readonly Pick<Skill, "name">[],
	tools: readonly string[],
	restored: readonly string[] = [],
): string[] {
	if (!tools.includes("bf_skill")) return [];
	const ids = new Set(skills.map((skill) => skill.name));
	const required = [...new Set(["bf-task-recovery", ...restored])];
	if (required.some((id) => !ids.has(id))) throw Error("REQUIRED_TOOL_SKILL_MISSING");
	return required;
}

export function loadFrozenSkills(root: string, expected: string): Skill[] {
	const manifest = JSON.parse(fs.readFileSync(path.join(root, "manifest.json"), "utf8")) as Manifest;
	const { sha256, ...body } = manifest;
	const hash = (text: crypto.BinaryLike) => crypto.createHash("sha256").update(text).digest("hex");
	if (manifest.schema_version !== "bf-resource-manifest-v1" || sha256 !== expected || hash(canonical(body)) !== sha256)
		throw Error("RESOURCE_MANIFEST_TAMPER");
	const base = fs.realpathSync(root);
	for (const [name, digest] of Object.entries(manifest.files)) {
		const file = path.resolve(base, name);
		if (!file.startsWith(base + path.sep) || fs.lstatSync(file).isSymbolicLink() || fs.realpathSync(file) !== file)
			throw Error("RESOURCE_PATH_INVALID");
		if (hash(fs.readFileSync(file)) !== digest) throw Error(`RESOURCE_CONTENT_TAMPER: ${name}`);
	}
	const ids = new Set<string>();
	return manifest.skills.map((entry) => {
		if (ids.has(entry.id) || manifest.files[entry.path] !== entry.sha256) throw Error("RESOURCE_ENTRY_INVALID");
		ids.add(entry.id);
		const filePath = path.join(base, entry.path);
		const baseDir = path.dirname(filePath);
		return {
			name: entry.id,
			description: `${entry.description} [${entry.plugin_id}@${entry.version}; 用 bf_skill activate 加载]`,
			filePath,
			baseDir,
			disableModelInvocation: false,
			sourceInfo: { path: filePath, source: `bf-frozen:${sha256}`, scope: "project", origin: "package", baseDir },
		};
	});
}
