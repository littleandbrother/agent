/** Read current owner-bound facts. No caching, native operation or fallback. */
export async function inspectCurrentContext(args: unknown, api: (route: string) => Promise<unknown>): Promise<unknown> {
	if (
		!args ||
		typeof args !== "object" ||
		Array.isArray(args) ||
		(args as Record<string, unknown>).action !== "context_inspect" ||
		Object.keys(args).some((key) => key !== "action")
	) {
		throw new Error("PRODUCT_CONTEXT_INSPECT_ARGUMENTS: use only action=context_inspect");
	}
	return await api("/api/product-context");
}
