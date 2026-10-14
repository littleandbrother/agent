import { createLocalBashOperations } from "@earendil-works/pi-coding-agent";
import { describe, expect, it } from "vitest";
import { boundedBashOperations } from "../src/bounded-bash.ts";

describe("BF bounded shell", () => {
	it("passes default and explicit timeouts to the backend and rejects excess before execution", async () => {
		const received: number[] = [];
		const ops = boundedBashOperations({
			exec: async (_command, _cwd, options) => {
				received.push(options.timeout!);
				return { exitCode: 0 };
			},
		});
		await ops.exec("fixture", "/tmp", { onData: () => {} });
		await ops.exec("fixture", "/tmp", { onData: () => {}, timeout: 120 });
		await expect(ops.exec("fixture", "/tmp", { onData: () => {}, timeout: 301 })).rejects.toThrow(
			"BF_BASH_TIMEOUT_REQUIRED",
		);
		expect(received).toEqual([60, 120]);
	});

	it("reports an actual SIGTERM without stdout as failure", async () => {
		const ops = boundedBashOperations(createLocalBashOperations());
		await expect(ops.exec("kill -TERM $$", "/tmp", { onData: () => {} })).rejects.toThrow("BF_BASH_SIGNAL_EXIT");
	});

	it("terminates an actual non-terminating child by its operation deadline", async () => {
		const ops = boundedBashOperations(createLocalBashOperations(), 0.1, 1);
		const started = Date.now();
		await expect(ops.exec("sleep 30", "/tmp", { onData: () => {} })).rejects.toThrow("timeout:0.1");
		expect(Date.now() - started).toBeLessThan(3000);
	});

	it("preserves ordinary exit codes and outputs", async () => {
		let output = "";
		const ops = boundedBashOperations(createLocalBashOperations());
		const result = await ops.exec("printf verified; exit 7", "/tmp", {
			onData: (data) => {
				output += data;
			},
		});
		expect(result.exitCode).toBe(7);
		expect(output).toBe("verified");
	});
});
