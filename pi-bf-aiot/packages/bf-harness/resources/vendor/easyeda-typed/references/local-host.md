# Desktop-local typed EDA

Transport: easyeda-typed-v1. Policy: desktop-local-v1. Compatible local connector: 1.9.0-bf-desktop.1 (`environment.v1`).

BF injects the exact bound project and selected window; Pi must omit route flags. `bf_eda inspect` reports binding and runtime readiness separately. Desktop/local readiness requires a single matching project window and official SDK host=desktop, mode=half-offline or offline. Unknown/missing facts and multiple matches refuse mutation. Window ID churn after reconnect is resolved using the original project UUID; no Web fallback.

The daemon is one loopback-only persistent service. Client startup is bounded-waited; NO_CONNECTED_WINDOW is not an account/login result. A project on the start page is not open engineering. No passwords, cookies, browser profiles or provider keys are stored by this adapter. Local editing/save/readback does not require cloud login; cloud library/project access and purchasing remain separate authenticated services.

Use stable operation_id, inspect or job before retry, and read back partial/unknown writes. Preserve originals. Change parameter data through typed sch/pcb/apply commands, explicitly save, bounded doc reload, then read the actual project/doc/objects. Report only the properties independently observed. Screenshots and exports do not prove connectivity/DRC.

## ARM 桌面内置 CLI 路由

操作员可将实际传输固定为 `native-cli-v1`。这仍使用同一 `bf_eda`、Cobra 命令及固定 typed action；不要调用 raw invoke/任意 JS。系统根据官方 `session list` 的真实编辑器会话建立唯一窗口，能力为 `native-cli.v1`。`inspect` 中 host policy 的 transport 与就绪窗口须对应。未找到 native 会话时不会自动回退 Connect 或 Web。

现有 Connect / Run API Gateway 可作为独立连接诊断；它们的多个 WS 注册不等于多个实际编辑器窗口。每次执行仍核对本地 host/mode 和精确项目 UUID。原生失败/超时必须先回读，不能重复写；未知写入阻止后续写入。每个修改检查点显式保存，真实重载后新鲜读取，不以自动保存代替同版本验证。
