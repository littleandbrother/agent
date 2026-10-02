/** U0 makes a source-changing request from public experience only. */
export function improvementPrompt(context: any): string {
	return `You are an independent Pi improver modifying a battery-free AIoT solver harness.
Read the source under harness/ and the public experience in experience.json.
Improve solver behavior by editing harness/solver.ts. You may also improve the improvement procedure in harness/improver.ts.
These are the only two allowed source changes. Do not change task/evaluator semantics, budgets, tools or controller files.
Do not insert task-specific answers or result labels. Propose a general improvement grounded in observable traces.
Use bash to run the existing local TypeScript build/check and repair failures within this same session.
Explain the change, falsifier, expected effect and limitations in candidate-note.md. A no-op is not an improvement.
An external controller will hash the diff, build it, start a fresh Pi process, and compare it with the parent on identical tasks and budgets. Passing build alone does not qualify promotion.
Use only the explicit execution packet limits: ${JSON.stringify(context.execution_contract)}. Finish with files on disk, not an answer-only patch.
Context: ${JSON.stringify(context)}`;
}
