# Pilot 保存证据的补充审计

状态为 `SCOPED_AUDIT_PASS_WITH_MISSING_RAW`。这是对已有归档的只读审计，不调用 report_design_pilot.py、不生成旧报告、不重新评价科学门槛，也不导入求解器或发起新实验。仅需 Python 3 标准库。

```bash
python3 -B research/bf-design-integration/analysis/pilot/audit_pilot.py --archive release/evidence/door-design-pilot-v1.zip --out /tmp/pilot-audit-new.json
python3 -B -m unittest discover -s research/bf-design-integration/analysis/pilot -p 'test_*.py' -v
```

输出必须是新路径，现有文件、链接和目录不覆盖。归档固定 SHA-256 校验在 ZIP 解析之前完成；不解压，不读取归档中的本地路径。独立测试覆盖损坏哈希、清单遗漏、重复/越界成员、时间网格漂移及输出保护；另对真实保存归档重放并与 AUDIT.json 比较。tests.log 保留实际测试结果。

AUDIT.json 的 source_index 将 17 个源文件绑定到归档内快照和哈希；DELIVERY.json 绑定此审计的代码、输出和说明。pilot 的封存基线为 `338d60384d5805abf1e02252a4513860066a2c39`，发布基线为 `87e7d75b4c5cd13c96560b8aaa4168a292ddc3c9`，两者不互换。

已核对：268 个归档成员、267 项清单；12 个预声明设计、2 个冷对照、3 次显式环境恢复，共17次尝试。原始3次 tool_fail 仍保留；10次 completed 包含2次冷对照，4次 out_of_domain 不是产品物理不可行。恢复通过原始收据/结果哈希关联同一候选，不计为新的独立设计。源/运行目录迁移、P/R 路径及符号链接不计为独立重复。

任务规范哈希、候选、结果、产物及 C 程序源码已按保存字节核对。physics_hash 仅重算保存的 spec/implementation/tools 身份组合；stage key 仅核对结果内部对应关系，未凭缺失的缓存输入重新生成 key。外部软件、供应商二进制和大型原生包只有声明哈希，未核对其实际字节。冷缓存独立性仍是历史收据声明，不能从本轻量包重新证明缓存初态。

冷对照波形的逐通道差异、相同时间网格、程序 time/state/current 与接收记录由保存 CSV/JSON 独立读回核对。RAW 上的峰值标量差异没有独立验证，重采样最大值不冒充原生最大值。当前保存的10条完成记录均只有 RESET 状态、无完整发送事件；这是冻结模型下的记录，不是实际硬件或 Agent 结果。

能量只核对 energy.json 与结果副本及终点代数平衡是否落在报告的路径最大残差内。没有将终点残差当作路径最大值。初始机械/压电能量非零，不能把零电容初压描述为总初能量为零。波形有4001个采样点，程序有40001个点；虽包含2秒驱动停止点，但缺少单侧功率、原生自适应网格、力/端口电流和完整 ROM 参数，因此不复算原始能量积分，也不认证 PMIC 内损耗。MISSING_RAW / hash_verified=false 是预期限制，不能被 scoped pass 掩盖。

[材料来源映射](MATERIAL-SOURCE-MAP.zh.md) 是另一个有限来源说明；不把新网页冒充历史快照，也不改 COMSOL 材料或现有常数。
