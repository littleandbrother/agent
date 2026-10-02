# cache-v2 集成、完整 Pi 补齐与回归（最终 v2）

基线 littleandbrother/agent@338d60384d5805abf1e02252a4513860066a2c39。新工作树；没有 commit/push；旧封存证据未改。

## 已确认

- 两处 cache-v2 生产代码与独立评审补丁字节完全一致；另迁移旧路径测试，并加入11项正式回归
- 仿真链路22/22、独立缓存/数据流审计6/6、Node投影27/27通过；SDK/Studio类型检查通过
- Battery World619/620个文件、Pi1774/1774个文件逐项 Git blob 校验，无哈希不符。完整Pi源码、npm ci --ignore-scripts、npm run bf:build 均通过；构建后1774个源码文件未变
- 实际 CadQuery 生成并重新打开48/50mm两套22部件STEP；48mm重复为相同STEP摘要的缓存命中，50mm为新键
- 实际有限磁体力表 → Cache → 实际SPICE deck一致；篡改被拒绝，旧缓存目录字节未改。该审计的梁ROM来自合成COMSOL日志夹具的真实解析器，不是新COMSOL计算
- 实际 Cortex-M4 目标编译与主机共享库构建通过；SIL只执行主机库，无供电0包、供电夹具4次TX/1次虚拟接收。没有ARM指令、nRF52832/S132、RF或实物执行

## 最终总回归不是全绿

未改基线：425项被发现，413项执行，352项成功。
集成版：436项被发现，424项执行，363项成功。
两者均为32个failure、29个error、2个skip；29个error含2个class-setup error，导致另12项测试未运行。所有共同测试/fixture状态完全一致；新增11项全部通过，无观察到的新增回归。

7项provider单元测试使用严格限于测试作用域的内存key-loader夹具；原测试已mock HTTP，另加deny-all socket/opener保护。基线/集成配置相同，意外网络调用0、凭据文件0；exists()仍为False，不代表真实provider可用。

最终61条failure/error记录分组见FINAL-ROOT-CAUSES.json：36条研究隔离/编译/qualification连锁；21条agentlab隔离执行或后续断言；2条STM32L031 CMSIS；1条缺失历史投影；1条真实ngspice数值断言。平台连锁归因同时标明直接证据与源代码推导，不声称换平台后必然全通过。

ngspice44.2新启用的电学反作用测试得到9.750000000072201e-08m，未超过原1e-7m门槛；基线同样失败，未调整阈值。它只用于开源回归，未替代LTC3588供应商模型。

两个skip分别是旧pluck路径硬编码/opt/homebrew/bin/ngspice，以及不在当前磁耦合/nRF范围的STM32L031 CMSIS。未伪造可执行文件、Homebrew路径或目标元数据。

## 未完成的独立门槛

- ./init.sh 在macOS Seatbelt绑定的B2再生成处失败；没有弱化隔离
- 完整Studio生成缺少payload，不能从类型检查通过推导完整构建通过
- Battery World唯一未取得文件：25,279,931字节的历史profiled-report.json；blob传输关闭，文件范围读取为空。Pi的大PNG通过官方固定npm包取得并与Git blob精确匹配，只提取该图片
- COMSOL/LTspice、nRF52832/S132、实物测量、产品验收与研究晋升均未在本轮完成

## 分开提供的补丁

cache-v2-integrated.patch：2处生产代码 + 正常测试入口；已dry-run。
unsupported-runtime-diagnostic/unsupported-runtime.patch：独立建议，未应用到cache工作树。6项测试通过，实际Linux CLI明确报UNSUPPORTED_RUNTIME并退出1；可执行文件可用性检查不等于隔离认证。

最终权威：INTEGRATION-RECEIPT-v2.json、aggregate-comparison-final.json、FINAL-ROOT-CAUSES.json、aggregate-*-v4/。旧v2/v3日志和早期receipt保留为环境恢复历史，不能与最终数字混用。

新增付费模型调用0、商业求解器执行0、安全设置变更0。可信操作者缓存一致性不构成抗攻击认证、物理资格或Agent/RSI效果。
