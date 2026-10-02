/** Frozen prompt-first method manipulation. No model, solver or dispatch code. */
import crypto from "node:crypto";

export const METHOD_VERSION = "bf-method-policy-v2-mainline";
export const PROFILES = Object.freeze({
	strong_generic: Object.freeze({ R: false, Q: false }),
	bf_design: Object.freeze({ R: true, Q: true }),
	representation_only: Object.freeze({ R: true, Q: false }),
	revision_only: Object.freeze({ R: false, Q: true }),
});
export type MethodId = keyof typeof PROFILES;
export interface MethodProfile {
	schema: typeof METHOD_VERSION;
	method_id: MethodId;
	R: boolean;
	Q: boolean;
	candidate_opportunities: 3;
}
export const ordered = (value: any): any =>
	Array.isArray(value)
		? value.map(ordered)
		: value && typeof value === "object"
			? Object.fromEntries(
					Object.keys(value)
						.sort()
						.map((key) => [key, ordered(value[key])]),
				)
			: value;
export const digest = (value: unknown): string =>
	crypto
		.createHash("sha256")
		.update(JSON.stringify(ordered(value)))
		.digest("hex");
const hash = (value: unknown): value is string => typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
const fail = (code: string): never => {
	throw new Error(code);
};

export function profile(id: string): MethodProfile {
	if (!Object.hasOwn(PROFILES, id)) fail("UNKNOWN_METHOD_PROFILE");
	return {
		schema: METHOD_VERSION,
		method_id: id as MethodId,
		...PROFILES[id as MethodId],
		candidate_opportunities: 3,
	};
}
export function validateProfile(value: MethodProfile): MethodProfile {
	if (!value || digest(value) !== digest(profile(value.method_id))) fail("METHOD_PROFILE_DRIFT");
	return profile(value.method_id);
}
export function methodInstructions(value: MethodProfile): string {
	const p = validateProfile(value);
	const common = `All conditions receive the same public requirements, facts, history, tools, baseline, feedback and validity checks. You may propose architecture and cross-domain changes. Never treat unsupported execution as a failed design, or a proposed change as implemented. Preserve requirements; do not lower modeled currents or change physical assumptions without artifact-bound evidence. This bounded method version has bounded revision rounds and at most three candidate opportunities in the entire episode within the same total budget; unused opportunities are reported, not synthetically spent. Publicly select the final design using only available feedback. Record revisions with bf_engineering action=record_revision, citing observed run IDs and actual changed artifacts. No representation format is part of scientific acceptance.`;
	const representation = p.R
		? `R=1: Maintain method-state.json with functions, their implementing artifact IDs, resource supplies/demands, and conditional relations. Each relation names its condition, dependent artifact IDs and observed run IDs. Distinguish supported, stale, contradicted and unknown support. When artifacts change, recheck the affected relations; keep old evidence immutable. Use these relations to identify which requirements/resources conflict before choosing the next action. Relations do not add physical facts or confer validity.`
		: `R=0: Use ordinary notes or tables for exactly the same facts and history. No special functional/resource representation procedure is imposed; the common validity checks still apply.`;
	const revision = p.Q
		? `Q=1: Attribute the observed conflict to explicit requirement/condition and implementation choices. Consider parameter refinement and architecture recomposition. Refinement keeps roles/connections/implementation topology; recomposition changes functional allocation, connections or implementation. State why the chosen change addresses the conflict and what observation would falsify it. If recomposition lacks provider support, retain that proposal as insufficient_evidence/model_extension_required, never substitute a parameter edit while claiming architecture success. An unsupported proposal never adds a candidate budget.`
		: `Q=0: Use normal feedback-driven search across at most three candidate opportunities. No special conflict-attribution or refinement/recomposition procedure is imposed. Architecture and cross-domain proposals remain allowed; choose them spontaneously when useful.`;
	return [common, representation, revision].join("\n");
}

export const CURRENT_PROVIDER = Object.freeze({
	id: "mainline-numeric-candidate-only-v2",
	numeric_parameters: true,
	architecture: false,
	candidate_artifact_sources: false,
});
export function capabilityAdmission(required: { architecture: boolean; candidate_artifact_sources: boolean }) {
	if (
		!required ||
		Object.keys(required).sort().join() !== "architecture,candidate_artifact_sources" ||
		typeof required.architecture !== "boolean" ||
		typeof required.candidate_artifact_sources !== "boolean"
	)
		fail("CAPABILITY_REQUIREMENTS_REQUIRED");
	const blockers: string[] = [];
	if (required.architecture) blockers.push("PROVIDER_ARCHITECTURE_NOT_IMPLEMENTED");
	if (required.candidate_artifact_sources) blockers.push("PROVIDER_CANDIDATE_SOURCES_NOT_IMPLEMENTED");
	return {
		provider: CURRENT_PROVIDER,
		required: { ...required },
		capability_compatible: blockers.length === 0,
		blockers,
		execution_authorized: false,
		scientific_qualified: false,
	};
}

export interface RevisionContext {
	profile: MethodProfile;
	previous_artifacts: Record<string, string>;
	current_artifacts: Record<string, string>;
	observation_ids: string[];
	round: number;
	used_opportunities: number[];
}
/** Input is untrusted participant metadata; all identities/effects come from context. */
export function revisionRecord(input: any, context: RevisionContext) {
	const p = validateProfile(context.profile);
	const keys = ["opportunity", "requested_kind", "observation_ids", "rationale", "falsifier", "relations"];
	if (!input || typeof input !== "object" || Array.isArray(input) || Object.keys(input).some((k) => !keys.includes(k)))
		fail("REVISION_FIELDS");
	if (![1, 2, 3].includes(input.opportunity) || context.used_opportunities.includes(input.opportunity))
		fail("REVISION_OPPORTUNITY_USED_OR_OUTSIDE_BUDGET");
	if (!Number.isInteger(context.round) || context.round < 1) fail("REVISION_ROUND");
	if (!["parameter_refinement", "architecture_recomposition"].includes(input.requested_kind)) fail("REVISION_KIND");
	if (
		!Array.isArray(input.observation_ids) ||
		!input.observation_ids.length ||
		new Set(input.observation_ids).size !== input.observation_ids.length ||
		input.observation_ids.some((id: unknown) => typeof id !== "string" || !context.observation_ids.includes(id))
	)
		fail("REVISION_UNKNOWN_OBSERVATION");
	if (
		typeof input.rationale !== "string" ||
		!input.rationale.trim() ||
		typeof input.falsifier !== "string" ||
		!input.falsifier.trim()
	)
		fail("REVISION_REASON_REQUIRED");
	for (const manifest of [context.previous_artifacts, context.current_artifacts]) {
		if (!manifest || !Object.keys(manifest).length || Object.values(manifest).some((value) => !hash(value)))
			fail("ARTIFACT_HASH_REQUIRED");
	}
	const artifacts = [
		...new Set([...Object.keys(context.previous_artifacts), ...Object.keys(context.current_artifacts)]),
	].sort();
	const changed = artifacts.filter((name) => context.previous_artifacts[name] !== context.current_artifacts[name]);
	const relations = input.relations ?? [];
	if (!Array.isArray(relations) || (p.R && !relations.length)) fail("METHOD_RELATIONS_REQUIRED");
	const relationIds = new Set<string>();
	for (const relation of relations) {
		if (
			!relation ||
			Object.keys(relation).sort().join() !==
				["id", "function", "implementation", "resource", "condition", "artifact_ids", "observation_ids"]
					.sort()
					.join() ||
			["id", "function", "implementation", "resource", "condition"].some(
				(k) => typeof relation[k] !== "string" || !relation[k].trim(),
			)
		)
			fail("METHOD_RELATION_FIELDS");
		if (relationIds.has(relation.id)) fail("METHOD_RELATION_DUPLICATE");
		relationIds.add(relation.id);
		if (
			!Array.isArray(relation.artifact_ids) ||
			!relation.artifact_ids.length ||
			relation.artifact_ids.some((name: string) => !artifacts.includes(name))
		)
			fail("METHOD_RELATION_UNKNOWN_ARTIFACT");
		if (
			!Array.isArray(relation.observation_ids) ||
			!relation.observation_ids.length ||
			relation.observation_ids.some((id: string) => !input.observation_ids.includes(id))
		)
			fail("METHOD_RELATION_UNKNOWN_OBSERVATION");
	}
	// A requested architecture change is never certified by changing numeric JSON.
	const unsupported = input.requested_kind === "architecture_recomposition";
	const record = {
		schema: "bf-method-revision-v1",
		method_profile: p,
		round: context.round,
		opportunity: input.opportunity,
		requested_kind: input.requested_kind,
		observation_ids: input.observation_ids,
		rationale: input.rationale,
		falsifier: input.falsifier,
		before_artifacts: context.previous_artifacts,
		after_artifacts: context.current_artifacts,
		changed_artifacts: changed,
		relations: relations.map((r: any) => ({
			...r,
			support_status: r.artifact_ids.some((a: string) => changed.includes(a))
				? "stale_after_revision"
				: "unknown_not_independently_validated",
		})),
		implementation_status: unsupported
			? "proposed_unsupported"
			: changed.length
				? "artifact_change_unverified"
				: "no_op",
		evaluation_status: "not_evaluated",
		acceptance_status: "not_accepted",
		blocker: unsupported ? "PROVIDER_ARCHITECTURE_NOT_IMPLEMENTED" : null,
		execution_authorized: false,
		scientific_success: false,
	};
	return JSON.parse(JSON.stringify({ ...record, record_id: digest(record) }));
}
