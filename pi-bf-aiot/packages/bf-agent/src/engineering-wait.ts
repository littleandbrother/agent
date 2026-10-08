import { setTimeout as delay } from "node:timers/promises";

/** Native jobs outlive an LLM response. Waiting is executor work, not another prompt. */
export async function waitForEngineeringJob(
	read: () => Promise<any>,
	options: {
		wait: boolean;
		signal?: AbortSignal;
		progress?: (job: any) => void;
		sleep?: (signal?: AbortSignal) => Promise<unknown>;
	},
) {
	let job = await read();
	let nextNotice = 0;
	while (options.wait && ["QUEUED", "RUNNING"].includes(job.status)) {
		options.signal?.throwIfAborted();
		if (Date.now() >= nextNotice) {
			options.progress?.(job);
			nextNotice = Date.now() + 30000;
		}
		await (options.sleep ?? ((signal) => delay(5000, undefined, { signal })))(options.signal);
		options.signal?.throwIfAborted();
		job = await read();
	}
	return job;
}
