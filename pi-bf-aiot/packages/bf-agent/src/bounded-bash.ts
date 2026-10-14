import {
	type BashOperations,
	createBashToolDefinition,
	createLocalBashOperations,
	defineTool,
} from "@earendil-works/pi-coding-agent";

export const DEFAULT_BASH_TIMEOUT_SECONDS = 60;
export const MAX_BASH_TIMEOUT_SECONDS = 300;

/** BF operation containment is independent of the user's cumulative budget. */
export function boundedBashOperations(
	backend: BashOperations,
	defaultTimeout = DEFAULT_BASH_TIMEOUT_SECONDS,
	maximumTimeout = MAX_BASH_TIMEOUT_SECONDS,
): BashOperations {
	return {
		async exec(command, cwd, options) {
			const timeout = options.timeout ?? defaultTimeout;
			if (!Number.isFinite(timeout) || timeout <= 0 || timeout > maximumTimeout) {
				throw new Error(`BF_BASH_TIMEOUT_REQUIRED: use a positive timeout of at most ${maximumTimeout} seconds`);
			}
			const result = await backend.exec(command, cwd, { ...options, timeout });
			// The SDK shell result uses null for a signal exit. It must never be
			// mistaken for a successful command with empty output.
			if (result.exitCode === null) {
				throw new Error(
					"BF_BASH_SIGNAL_EXIT: command terminated by a signal; execution did not complete. Inspect the saved input and failure before retrying.",
				);
			}
			return result;
		},
	};
}

export function createBoundedBashTool(cwd: string) {
	const definition = createBashToolDefinition(cwd, { operations: boundedBashOperations(createLocalBashOperations()) });
	return defineTool({
		...definition,
		executionMode: "sequential",
		description: `${definition.description} BF default ${DEFAULT_BASH_TIMEOUT_SECONDS}s, maximum ${MAX_BASH_TIMEOUT_SECONDS}s. Work inside cwd; scratch/ is writable. Prefer bf_workspace for batched hashes, JSON fields and source-line search. Use Python hashlib rather than platform-specific sha256sum.`,
	});
}
