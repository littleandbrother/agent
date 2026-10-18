# CI修复与反馈执行发布

上次提交 `dcd7c54` 的两次CI均在Repository作业失败。3项报告测试调用了写死的Codex Python路径，Ubuntu中不存在该路径。

本次修改：

- 统一PDF解释器：优先显式 `BF_REPORT_PYTHON`，其次使用具备依赖的当前解释器，兼容既有桌面运行环境。
- 固定数值/PDF依赖；CI实际生成PDF并检查同版交付包。
- Linux真实编译固定参考C，检查掉电复位和禁止上电程序冒用OFF；macOS沙箱集成在本机检查。
- CI通过 `BFWORLD_VERIFY_PROFILE=architecture-v2-ci ./init.sh` 执行回归和44件封存证据读回。
- BFA-035保留未关闭工程门，登记为blocked，解除其与当前活动功能的登记冲突。

本机与干净源树280项Repository测试通过。Pi干净安装、构建、类型和浏览器检查通过，源文件无生成修改。11项原生资格证据读回、项目登记检查通过。新增模型调用和原生求解均为0。

BFA-040反馈执行及两份PDF随本次发布。GitHub精确提交CI结果随后追加到verification.json。推进方案见 [NEXT.md](NEXT.md)。
