/** H0 policy for presenting verified experiment state to a Pi solver. */
export interface SolverState {
	current: unknown;
	bestVerified: any;
	pending: Record<string, any>;
	facts: any[];
	hypotheses: string[];
	plan: string[];
	remainingExperiments: number;
}

export function initialState(budget: {solver_calls: number}): SolverState {
	return {
		current: null,
		bestVerified: null,
		pending: {},
		facts: [],
		hypotheses: [],
		plan: [],
		remainingExperiments: budget.solver_calls,
	};
}

export function observeExperiment(state: SolverState, result: any): SolverState {
	const checks = Object.values(result.checks ?? {}).filter(Boolean).length;
	const bestChecks = Object.values(state.bestVerified?.checks ?? {}).filter(Boolean).length;
	return {
		...state,
		current: result,
		bestVerified: !state.bestVerified || checks > bestChecks ? result : state.bestVerified,
		facts: [
			...state.facts,
			{ run_id: result.run_id, snapshot_id: result.snapshot_id, checks: result.checks, summary: result.summary },
		],
	};
}

export function solverPrompt(task: any, state: SolverState): string {
	return `You solve one declared computational battery-free AIoT design task independently.
Read task.json and candidate.json. Use the registered magnetic candidate contract. Unsupported architecture or model regions are insufficient evidence, never silently restricted or scored as design failure.
First execute the provided baseline unchanged and inspect it. If it fails, choose and execute a source revision using the observed result. If it passes, unnecessary changes are not required.
Use bf_experiment to execute current files, bf_job to reconcile, bf_inspect_run to read verified facts, and bf_submit to seal current files against their exact completed run.
Execution success and design success differ. Do not claim hardware or a trained-model result.
Use observations to decide your next revision. Keep hypotheses separate from facts in notes.md.
Use only the explicit execution packet limits. No internet access. A blocked native request is not a completed experiment.
Execution contract: ${JSON.stringify(task.execution_contract)}
If no design passes, submit the best actually evaluated design and state the failure. Required but unavailable assets must be reported as NOT_EVALUATED; never replace them with synthetic defaults.
When work is interrupted, use persisted operation IDs and pending jobs; never invent or redispatch unknown work.
Task: ${JSON.stringify(task)}
Current structured state: ${JSON.stringify(state)}`;
}
