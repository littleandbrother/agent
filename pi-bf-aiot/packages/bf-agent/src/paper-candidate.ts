import { defineTool } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

type Api = (route: string, body?: unknown, bounded?: boolean) => Promise<any>;

/** Bind the real native consumer to the current working candidate. No executor,
 * device choice, evaluation, retry policy or second task planner lives here. */
export async function bindPaperAction(api: Api, route: string, body: any) {
	const native =
		(route === "/api/eda-cli" && body?.action === "command") ||
		(route === "/api/engineering" && body?.action === "run") ||
		(route === "/api/assembly" && ["write", "register"].includes(body?.action));
	if (!native) return body;
	const view = await api("/api/design-lab", { action: "inspect" });
	if (view.control_route !== "candidate-lifecycle") throw Error("PAPER_CANDIDATE_ROUTE_REQUIRED");
	return { ...body, candidate_id: view.working_design, candidate_revision: view.revision };
}

export function paperCandidateTool(api: Api, reply: (value: any) => any) {
	return defineTool({
		name: "bf_design",
		label: "Current design candidate",
		description:
			"inspect returns current P01 candidate/jobs/checks/pending operations; fields=[candidate_selector,input_manifest] adds the selection and files. freeze takes parent and sources={candidate.json: JSON text}; inside that JSON put schema_version=bf-paper-candidate-v1, files/projects/eda_receipts/selected_jobs and decision. Native EDA/engineering actions take decision_use. check takes operation_id and returns check_id; submit takes job_id=check_id and rationale. intent takes kind CONTINUE/BLOCKED/REJECT, rationale and plan. prepare_delivery takes operation_id, design_id and unresolved_gates; omitted engineering_jobs/files/eda_receipts reuse your frozen candidate selection, report_path defaults to native-report.json. Explicit arrays override those defaults. It writes metadata; freeze outputs before check/submit. interfaces returns current source-bound parameter facts.",
		executionMode: "sequential",
		parameters: Type.Object(
			{
				action: Type.Union(
					[
						"inspect",
						"environment",
						"source",
						"freeze",
						"job",
						"check",
						"submit",
						"adopt",
						"intent",
						"events",
						"ack",
						"prepare_delivery",
						"interfaces",
					].map((v) => Type.Literal(v)),
				),
				design_id: Type.Optional(Type.String()),
				view: Type.Optional(Type.Union([Type.Literal("current"), Type.Literal("full")])),
				fields: Type.Optional(Type.Array(Type.String())),
				engineering_jobs: Type.Optional(Type.Array(Type.String())),
				files: Type.Optional(Type.Array(Type.String())),
				eda_receipts: Type.Optional(Type.Array(Type.String())),
				report_path: Type.Optional(Type.String()),
				unresolved_gates: Type.Optional(Type.Array(Type.String())),
				parent: Type.Optional(Type.String()),
				sources: Type.Optional(Type.Record(Type.String(), Type.String())),
				operation_id: Type.Optional(Type.String()),
				job_id: Type.Optional(Type.String()),
				expected_revision: Type.Optional(Type.Integer()),
				rationale: Type.Optional(Type.String()),
				kind: Type.Optional(Type.Union(["CONTINUE", "BLOCKED", "REJECT"].map((v) => Type.Literal(v)))),
				plan: Type.Optional(Type.Array(Type.String())),
				after: Type.Optional(Type.Integer()),
				cursor: Type.Optional(Type.Integer()),
			},
			{ additionalProperties: false },
		),
		async execute(_id, args) {
			return reply(await api("/api/design-lab", args));
		},
	});
}

/** End at a real BF decision, rather than repeatedly issuing a new delivery
 * mandate. BLOCKED/REJECT terminate a round without claiming product success. */
export async function finishPaperRound(api: Api, before: any) {
	const view = await api("/api/design-lab", { action: "inspect" });
	let after = before.event_cursor;
	let decision: any;
	for (;;) {
		const page = await api("/api/design-lab", { action: "events", after });
		for (const e of page.events) if (e.kind === "candidate_decision") decision = e;
		if (page.events.length < 100) break;
		if (page.next_cursor <= after) throw Error("PAPER_EVENT_CURSOR_NOT_ADVANCING");
		after = page.next_cursor;
	}
	if (!decision || decision.data.working_design !== view.working_design || decision.data.kind !== view.intent.kind)
		throw Error("PAPER_CANDIDATE_DECISION_REQUIRED");
	return { view, decision, full_product_passed: false, physical: "NOT_TESTED" };
}
