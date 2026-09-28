/*
 * Copyright 2024 JLCEDA <support[#]lceda.cn>
 * Copyright 2026 Eritque arcus
 *
 * Licensed under the Apache License, Version 2.0 (see ../LICENSE).
 *
 * NOTICE: This file has been modified from the upstream original at
 * https://github.com/easyeda/eext-run-api-gateway (commit 479d9b3, v1.0.5).
 * Changes: per-request execution timeout, chunked transfer of large results,
 * in-EDA stack traces on error, binary-result envelope, reconnect hardening,
 * serialization robustness. See ../CHANGES.md for the full list and rationale.
 */

/**
 * EasyEDA API Gateway 扩展
 *
 * 为 AI 编程工具（Claude Code、OpenCode、QwenCode 等）提供 WebSocket 桥接服务。
 * 扩展启动后自动扫描端口范围 49620-49629，发现 Bridge Server 并建立连接。
 *
 * 功能：
 * 1. 自动扫描端口范围发现 Bridge Server（握手验证 service: "easyeda-bridge"）
 * 2. 接收并执行来自 AI 的代码请求
 * 3. 将执行结果/错误返回给 Bridge Server
 * 4. 心跳检测 + 断线自动重连
 *
 * 架构：
 *   ┌─────────────┐  HTTP/WS    ┌────────────────┐  WebSocket   ┌──────────┐
 *   │  AI Agent    │ ◄────────► │  Bridge Server  │ ◄──────────► │ 本扩展    │
 *   │ (Skill Tool) │ Port Range │  (Node.js)      │  Port Range  │ (EasyEDA)│
 *   └─────────────┘ 49620-629  └────────────────┘  49620-629   └──────────┘
 */
import * as extensionConfig from '../extension.json';

// ─── 配置 ───────────────────────────────────────────────────────────
const WS_ID = 'ai-bridge';
const PORT_START = 49620;
const PORT_END = 49629;
const SERVICE_ID = 'easyeda-bridge';
const RETRY_DELAY_MS = 3000; // 重试退避基数（指数退避起点）
const RETRY_MAX_DELAY_MS = 30000; // 重试退避上限（超过噪声阈值后静默轮询）
const MAX_RETRIES = 5; // 弹提示的重试次数；超过后转为静默后台轮询（不再彻底放弃）
const HEARTBEAT_INTERVAL_MS = 15000;
const HEARTBEAT_TIMEOUT_MS = 5000;
const CONNECTION_TIMEOUT_MS = 1500; // 每个端口的连接+握手超时
const EXECUTE_TIMEOUT_MS = 25000; // 单次代码执行默认超时（< Bridge 端默认 30s，确保错误能先上报）
const EXECUTE_TIMEOUT_MAX_MS = 600000; // 请求可覆写的超时上限（10min）——批量导出/写回可能远超默认值
// 大结果分块传输：EDA 侧 sys_WebSocket.send 的单帧上限未文档化，超过阈值就切片，
// 由 Bridge 端按 id 重组。阈值取保守值——分块本身几乎无成本。
const RESULT_CHUNK_THRESHOLD = 512 * 1024;
const RESULT_CHUNK_SIZE = 256 * 1024;
const STORAGE_KEY_AUTO_CONNECT = 'autoConnectEnabled';
const STORAGE_KEY_LAST_PORT = 'lastGoodPort'; // 缓存上次成功端口，重连时优先尝试
const MBUS_TOPIC_STATUS = 'api-gateway-status';
const MBUS_TOPIC_CONTROL = 'api-gateway-control';

// ─── 状态 ───────────────────────────────────────────────────────────
let currentPort: number | null = null;
let handshakeVerified = false;
let retryTimer: ReturnType<typeof setTimeout> | null = null;
let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
let heartbeatPending = false;
let autoConnectEnabled = true;
let retryCount = 0;
let windowId: string | null = null; // 窗口唯一标识符
let isConnecting = false;
let connectionSessionId = 0;
let messageBusRegistered = false;

interface GatewayControlRequest {
	command: 'reconnect' | 'stop';
}

interface GatewayControlResponse {
	handled: boolean;
	connected: boolean;
	windowId: string | null;
}

/**
 * 获取当前连接状态（供 messageBus RPC 调用）
 */
function getConnectionStatus(): {
	connected: boolean;
	connecting: boolean;
	port: number | null;
	windowId: string | null;
} {
	return {
		connected: handshakeVerified,
		connecting: isConnecting,
		port: currentPort,
		windowId,
	};
}

function ensureMessageBusServices(): void {
	if (messageBusRegistered)
		return;

	eda.sys_MessageBus.rpcService(MBUS_TOPIC_STATUS, () => getConnectionStatus());
	eda.sys_MessageBus.rpcService(MBUS_TOPIC_CONTROL, (request?: GatewayControlRequest): GatewayControlResponse => {
		if (request?.command === 'reconnect') {
			performReconnect();
		}
		else if (request?.command === 'stop') {
			performStopConnection(false);
		}

		return {
			handled: true,
			connected: handshakeVerified,
			windowId,
		};
	});

	messageBusRegistered = true;
}

function nextConnectionSessionId(): number {
	connectionSessionId += 1;
	return connectionSessionId;
}

function isConnectionSessionActive(sessionId: number): boolean {
	return sessionId === connectionSessionId;
}

function closeWebSocket(): void {
	try {
		eda.sys_WebSocket.close(WS_ID);
	}
	catch { /* ignore */ }
}

function cancelConnectionFlow(resetRetryCount = true): void {
	nextConnectionSessionId();
	isConnecting = false;
	clearRetryTimer();
	stopHeartbeat();
	handshakeVerified = false;
	currentPort = null;
	windowId = null;
	if (resetRetryCount) {
		retryCount = 0;
	}
	closeWebSocket();
}

function performReconnect(): void {
	eda.sys_Message.showToastMessage(eda.sys_I18n.text('Reconnecting...'));
	cancelConnectionFlow();
	void scanAndConnect();
}

function performStopConnection(showToast = true): void {
	cancelConnectionFlow();
	if (showToast) {
		eda.sys_Message.showToastMessage(eda.sys_I18n.text('Connection stopped'));
	}
}

async function dispatchControlCommand(command: GatewayControlRequest['command']): Promise<void> {
	try {
		const response = await eda.sys_MessageBus.rpcCall(MBUS_TOPIC_CONTROL, { command }, 500) as GatewayControlResponse;
		if (response?.handled) {
			if (command === 'stop') {
				eda.sys_Message.showToastMessage(eda.sys_I18n.text('Connection stopped'));
			}
			return;
		}
	}
	catch {}

	ensureMessageBusServices();
	if (command === 'reconnect') {
		performReconnect();
	}
	else {
		performStopConnection();
	}
}

// ─── 生命周期 ────────────────────────────────────────────────────────

/**
 * 扩展激活入口（支持 onStartupFinished 自动启动）
 */
// eslint-disable-next-line unused-imports/no-unused-vars
export function activate(status?: 'onStartupFinished', arg?: string): void {
	ensureMessageBusServices();
	const storedValue = eda.sys_Storage.getExtensionUserConfig(STORAGE_KEY_AUTO_CONNECT);
	autoConnectEnabled = storedValue !== false;

	if (autoConnectEnabled) {
		void scanAndConnect();
	}
}

/**
 * 扩展停用时清理资源
 */
export function deactivate(): void {
	cancelConnectionFlow(false);
}

// ─── 菜单操作 ────────────────────────────────────────────────────────

/**
 * 手动重新连接（菜单项）
 */
export function reconnect(): void {
	void dispatchControlCommand('reconnect');
}

/**
 * 关于对话框（菜单项）
 */
export async function about(): Promise<void> {
	let status: string;

	// 通过 messageBus 获取 WebSocket 连接状态
	let statusInfo: { connected: boolean; connecting: boolean; port: number | null; windowId: string | null } = {
		connected: false,
		connecting: false,
		port: null,
		windowId: null,
	};
	try {
		statusInfo = await eda.sys_MessageBus.rpcCall(MBUS_TOPIC_STATUS, undefined, 300);
	}
	// eslint-disable-next-line unused-imports/no-unused-vars
	catch (e) {}

	if (statusInfo?.connected) {
		const portInfo = `Connected (port ${statusInfo.port})`;
		const windowInfo = statusInfo.windowId ? `\nWindow ID: ${statusInfo.windowId}` : '\nWindow ID: (not registered)';
		status = `${portInfo}${windowInfo}`;
	}
	else if (statusInfo?.connecting) {
		status = 'Connecting...';
	}
	else {
		status = 'Disconnected';
	}

	// 列出扩展能力——装错版本时这里能立刻看出来（旧版没有这一段）。
	const caps = [
		`timeout override (max ${EXECUTE_TIMEOUT_MAX_MS / 1000}s)`,
		`chunked results (>${RESULT_CHUNK_THRESHOLD / 1024}KB)`,
		'error stack',
	].join(', ');

	eda.sys_Dialog.showInformationMessage(
		`API Gateway v${extensionConfig.version}\n${status}\nCapabilities: ${caps}`,
		'About',
	);
}

/**
 * 切换自动连接开关（菜单项）
 */
export async function toggleAutoConnect(): Promise<void> {
	const currentlyEnabled = eda.sys_Storage.getExtensionUserConfig(STORAGE_KEY_AUTO_CONNECT) !== false;
	const nextEnabled = !currentlyEnabled;
	await eda.sys_Storage.setExtensionUserConfig(STORAGE_KEY_AUTO_CONNECT, nextEnabled);
	autoConnectEnabled = nextEnabled;
	eda.sys_Message.showToastMessage(
		eda.sys_I18n.text(nextEnabled ? 'Auto-Connect enabled' : 'Auto-Connect disabled'),
	);
}

/**
 * 停止连接并取消重试（菜单项）
 */
export function stopConnection(): void {
	void dispatchControlCommand('stop');
}

// ─── 端口扫描与连接 ──────────────────────────────────────────────────

/**
 * 端口尝试顺序：上次成功的端口优先，加速重连；其余按范围顺序。
 */
function getScanPortOrder(): number[] {
	const ports: number[] = [];
	for (let port = PORT_START; port <= PORT_END; port++)
		ports.push(port);

	const last = eda.sys_Storage.getExtensionUserConfig(STORAGE_KEY_LAST_PORT);
	if (typeof last === 'number' && last >= PORT_START && last <= PORT_END)
		return [last, ...ports.filter(port => port !== last)];
	return ports;
}

/**
 * 指数退避延迟：3s, 6s, 12s, 24s, ... 封顶 RETRY_MAX_DELAY_MS。
 */
function nextRetryDelayMs(): number {
	return Math.min(RETRY_DELAY_MS * 2 ** Math.min(retryCount, 6), RETRY_MAX_DELAY_MS);
}

/**
 * 获取当前窗口的可读标签（工程名），供 Bridge 在多窗口列表中区分展示。
 * 尽力而为——握手时可能尚未打开工程，失败则返回 undefined。
 */
async function getWindowLabel(): Promise<string | undefined> {
	try {
		const project = await eda.dmt_Project.getCurrentProjectInfo();
		return project?.friendlyName || project?.name || undefined;
	}
	catch {
		return undefined;
	}
}

/**
 * 扫描端口范围，通过 WebSocket 连接 + 握手验证找到 Bridge Server。
 *
 * 不使用 HTTP fetch（EasyEDA 网页端为 HTTPS，fetch http://127.0.0.1 会被
 * 浏览器的 Mixed Content 策略拦截），改为直接用 eda.sys_WebSocket.register()
 * 逐端口尝试，等待服务端发送 handshake 消息来确认身份。
 */
async function scanAndConnect(): Promise<void> {
	if (isConnecting) {
		return;
	}

	const sessionId = nextConnectionSessionId();
	isConnecting = true;
	clearRetryTimer();

	try {
		for (const port of getScanPortOrder()) {
			if (!isConnectionSessionActive(sessionId)) {
				return;
			}

			const found = await tryConnectToPort(port, sessionId);
			if (!isConnectionSessionActive(sessionId)) {
				return;
			}

			if (found) {
				currentPort = port;
				retryCount = 0;
				void eda.sys_Storage.setExtensionUserConfig(STORAGE_KEY_LAST_PORT, port);
				startHeartbeat(sessionId);
				return;
			}
		}

		// 未找到：指数退避后持续重试，不再彻底放弃（常见于 EDA 先开、Bridge 后启动）。
		// 超过 MAX_RETRIES 后停止弹提示，转为静默后台轮询。
		const delay = nextRetryDelayMs();
		retryCount++;
		console.warn(`[API-Gateway] No bridge server found on ports ${PORT_START}-${PORT_END}, retrying in ${delay}ms (attempt ${retryCount})...`);
		if (retryCount <= MAX_RETRIES) {
			eda.sys_Message.showToastMessage(
				`${eda.sys_I18n.text('Bridge not found, retrying in ', undefined, undefined, String(Math.round(delay / 1000)))} (${retryCount}/${MAX_RETRIES})`,
			);
		}
		scheduleRetry(sessionId, delay);
	}
	finally {
		if (isConnectionSessionActive(sessionId)) {
			isConnecting = false;
		}
	}
}

/**
 * 尝试通过 WebSocket 连接到指定端口，等待握手验证。
 *
 * 流程：
 * 1. 关闭已有 WS → register 新连接
 * 2. 如果 connectedCallFn 被调用 → 等待 handshake 消息
 * 3. 如果 handshake.service === SERVICE_ID → 成功（resolve true）
 * 4. 超时 CONNECTION_TIMEOUT_MS 仍未成功 → 关闭并返回 false
 *
 * @returns true = 握手成功且连接保持；false = 超时或验证失败
 */
function tryConnectToPort(port: number, sessionId: number): Promise<boolean> {
	return new Promise((resolve) => {
		let settled = false;

		let timer: ReturnType<typeof setTimeout>;

		const settle = (success: boolean, _reason: string) => {
			if (settled)
				return;
			settled = true;
			clearTimeout(timer);
			if (!success && isConnectionSessionActive(sessionId)) {
				closeWebSocket();
			}
			resolve(success);
		};

		if (!isConnectionSessionActive(sessionId)) {
			resolve(false);
			return;
		}

		// 先关闭旧连接（register 对同 ID 活跃连接不会更新参数）
		closeWebSocket();

		timer = setTimeout(settle, CONNECTION_TIMEOUT_MS, false, 'timeout');

		handshakeVerified = false;

		try {
			eda.sys_WebSocket.register(
				WS_ID,
				`ws://127.0.0.1:${port}/eda`,
				// 收到消息的回调（在扫描阶段处理握手，后续处理业务消息）
				async (event: MessageEvent) => {
					if (!isConnectionSessionActive(sessionId)) {
						settle(false, 'session cancelled');
						return;
					}

					try {
						const msg = JSON.parse(event.data);

						// 握手验证
						if (msg.type === 'handshake') {
							if (msg.service === SERVICE_ID) {
								handshakeVerified = true;
								// 生成窗口ID并注册到bridge（附带可读标签，便于多窗口区分）
								windowId = crypto.randomUUID();
								const label = await getWindowLabel();
								eda.sys_WebSocket.send(WS_ID, JSON.stringify({
									type: 'register',
									windowId,
									label,
									timestamp: Date.now(),
								}));
								eda.sys_Message.showToastMessage(
									`${eda.sys_I18n.text('Bridge connected (port ', undefined, undefined, String(port))})`,
								);
								settle(true, 'handshake OK');
							}
							else {
								console.warn(`[API-Gateway] Handshake failed: unexpected service "${msg.service}"`);
								settle(false, `wrong service: ${msg.service}`);
							}
							return;
						}

						// 非握手消息：扫描阶段忽略，已连接后正常处理
						if (!handshakeVerified)
							return;

						await handleMessage(msg);
					}
					catch (err) {
						console.error('[API-Gateway] Failed to handle message:', err);
					}
				},
				// 连接建立回调（此时等待服务端主动发送 handshake）
				() => {},
			);
		}
		catch (e) {
			// register 本身抛异常（如权限未开启）
			console.error('[API-Gateway] Failed to register WebSocket:', e);
			settle(false, `register threw: ${e}`);
		}
	});
}

// ─── 心跳检测 ────────────────────────────────────────────────────────

function startHeartbeat(sessionId: number): void {
	stopHeartbeat();
	heartbeatTimer = setInterval(() => {
		if (!isConnectionSessionActive(sessionId)) {
			stopHeartbeat();
			return;
		}

		if (!handshakeVerified)
			return;
		try {
			heartbeatPending = true;
			eda.sys_WebSocket.send(WS_ID, JSON.stringify({
				type: 'ping',
				id: `hb-${Date.now()}`,
				timestamp: Date.now(),
			}));
			// 如果超时内没收到 pong，重新扫描
			setTimeout(() => {
				if (!isConnectionSessionActive(sessionId)) {
					return;
				}

				if (heartbeatPending) {
					console.warn('[API-Gateway] Heartbeat timeout, reconnecting...');
					cancelConnectionFlow();
					void scanAndConnect();
				}
			}, HEARTBEAT_TIMEOUT_MS);
		}
		catch {
			// send 失败说明已断开
			cancelConnectionFlow();
			void scanAndConnect();
		}
	}, HEARTBEAT_INTERVAL_MS);
}

function stopHeartbeat(): void {
	if (heartbeatTimer) {
		clearInterval(heartbeatTimer);
		heartbeatTimer = null;
	}
	heartbeatPending = false;
}

// ─── 重试 ────────────────────────────────────────────────────────────

function scheduleRetry(sessionId: number, delayMs: number = RETRY_DELAY_MS): void {
	clearRetryTimer();
	retryTimer = setTimeout(() => {
		if (!isConnectionSessionActive(sessionId) || isConnecting) {
			return;
		}
		void scanAndConnect();
	}, delayMs);
}

function clearRetryTimer(): void {
	if (retryTimer) {
		clearTimeout(retryTimer);
		retryTimer = null;
	}
}

// ─── 结果序列化 ──────────────────────────────────────────────────────

/**
 * 给一个 Promise 加超时。超时后 reject（注意：无法真正取消底层 EDA 操作，
 * 但能确保调用方收到明确错误，而不是永远挂起）。
 */
function withTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
	let timer: ReturnType<typeof setTimeout>;
	const timeout = new Promise<never>((_resolve, reject) => {
		timer = setTimeout(() => reject(new Error(`Execution exceeded ${timeoutMs}ms`)), timeoutMs);
	});
	return Promise.race([promise, timeout]).finally(() => clearTimeout(timer)) as Promise<T>;
}

interface EdaBinaryEnvelope {
	__edaBinary: 'blob';
	mime: string;
	size: number;
	base64: string;
}

async function blobToEnvelope(blob: Blob): Promise<EdaBinaryEnvelope> {
	const bytes = new Uint8Array(await blob.arrayBuffer());
	let binary = '';
	const CHUNK = 0x8000;
	for (let i = 0; i < bytes.length; i += CHUNK)
		binary += String.fromCharCode(...Array.from(bytes.subarray(i, i + CHUNK)));
	return { __edaBinary: 'blob', mime: blob.type, size: bytes.length, base64: btoa(binary) };
}

/**
 * 二进制返回值（Blob/File/ArrayBuffer/TypedArray）无法过 JSON——统一编码为
 * base64 信封，客户端识别 __edaBinary 后解码。仅处理顶层返回值。
 */
async function serializeResult(result: unknown): Promise<unknown> {
	if (result instanceof Blob)
		return blobToEnvelope(result);
	if (result instanceof ArrayBuffer)
		return blobToEnvelope(new Blob([result]));
	if (ArrayBuffer.isView(result))
		return blobToEnvelope(new Blob([result as unknown as BlobPart]));
	return result;
}

/**
 * 安全序列化：处理循环引用与 BigInt，避免 JSON.stringify 抛出晦涩错误。
 */
function safeStringify(value: unknown): string {
	const seen = new WeakSet<object>();
	return JSON.stringify(value, (_key, val) => {
		if (typeof val === 'bigint')
			return val.toString();
		if (typeof val === 'object' && val !== null) {
			if (seen.has(val))
				return '[Circular]';
			seen.add(val);
		}
		return val;
	});
}

/**
 * 把请求携带的 timeoutMs 夹到合法区间；缺省/非法则用默认值。
 */
function resolveExecuteTimeout(requested?: unknown): number {
	if (typeof requested !== 'number' || !Number.isFinite(requested) || requested <= 0)
		return EXECUTE_TIMEOUT_MS;
	return Math.min(Math.round(requested), EXECUTE_TIMEOUT_MAX_MS);
}

/**
 * 发送一个响应信封。超过阈值时切成 result_chunk 帧，Bridge 端按 (id, seq) 重组。
 *
 * 切片切的是信封的 JSON 字符串。即便切点落在代理对中间也是安全的：
 * JSON.stringify 会把孤立代理转义成 \udXXX，parse 后原样还原，拼接后代理对复原。
 */
function sendEnvelope(id: string | undefined, envelope: Record<string, unknown>): void {
	const json = safeStringify(envelope);

	if (json.length <= RESULT_CHUNK_THRESHOLD) {
		eda.sys_WebSocket.send(WS_ID, json);
		return;
	}

	const total = Math.ceil(json.length / RESULT_CHUNK_SIZE);
	for (let seq = 0; seq < total; seq++) {
		eda.sys_WebSocket.send(WS_ID, JSON.stringify({
			type: 'result_chunk',
			id,
			seq,
			total,
			data: json.slice(seq * RESULT_CHUNK_SIZE, (seq + 1) * RESULT_CHUNK_SIZE),
			timestamp: Date.now(),
		}));
	}
}

// ─── 消息处理 ────────────────────────────────────────────────────────

interface BridgeMessage {
	type: 'execute' | 'ping' | 'pong' | 'handshake' | 'result' | 'error';
	id?: string;
	code?: string;
	service?: string;
	result?: unknown;
	error?: string;
	/** 本次执行的超时覆写（ms）。缺省 EXECUTE_TIMEOUT_MS，上限 EXECUTE_TIMEOUT_MAX_MS。 */
	timeoutMs?: number;
	timestamp?: number;
}

async function handleMessage(msg: BridgeMessage): Promise<void> {
	if (msg.type === 'ping') {
		eda.sys_WebSocket.send(WS_ID, JSON.stringify({
			type: 'pong',
			id: msg.id,
			timestamp: Date.now(),
		}));
		return;
	}

	if (msg.type === 'pong') {
		heartbeatPending = false;
		return;
	}

	if (msg.type === 'execute' && msg.code) {
		const timeoutMs = resolveExecuteTimeout(msg.timeoutMs);
		try {
			// 使用 AsyncFunction 执行代码，允许 await；加超时确保卡死也能上报错误
			const AsyncFunction = Object.getPrototypeOf(async () => {}).constructor;
			const fn = new AsyncFunction('eda', msg.code);
			const raw = await withTimeout(fn(eda), timeoutMs);
			const result = await serializeResult(raw);

			sendEnvelope(msg.id, {
				type: 'result',
				id: msg.id,
				result: result !== undefined ? result : null,
				timestamp: Date.now(),
			});
		}
		catch (err: unknown) {
			// 带上 stack——几百行的批量导出脚本出错时，只有 message 基本没法定位。
			sendEnvelope(msg.id, {
				type: 'error',
				id: msg.id,
				error: err instanceof Error ? err.message : String(err),
				stack: err instanceof Error ? err.stack : undefined,
				timestamp: Date.now(),
			});
		}
	}
}
