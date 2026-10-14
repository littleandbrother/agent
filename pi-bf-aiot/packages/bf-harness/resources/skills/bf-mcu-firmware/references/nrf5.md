# P01 nRF5 固定版本
nRF5 SDK 17.1.0 / S132 7.2.0 / nRF52832。
当前工程 main.c、sdk_config.h、板级配置、app_policy.*；bf_workspace search 给出来源行。
核对顺序：引脚/LFCLK → SDK 初始化 → app_timer/IRQ → BLE 实际调度 → 通知队列/回调身份 → 失败/低功耗 → 目标构建 → 负载对应。
本地章节：components/softdevice/s132/headers/ble_gap.h；components/libraries/util/app_util.h；components/libraries/timer；components/ble/ble_advertising；integration/nrfx；examples/peripheral/twi_sensor。
固定章节与 SHA 见 [sdk-index.json](sdk-index.json)。当前任务 context 的 apparatus_reference 中，nrf5-sdk-index.json 给出可直接读取的 workspace_path；用 bf_workspace search 在精确章节定位行号。
Context7 当前查询返回 nRF Connect SDK、Rust HAL 等库；P01 采用本地 nRF5 17.1.0/S132 7.2.0 章节。
方法参考：https://github.com/Jeffallan/claude-skills/tree/main/skills/embedded-systems
