# PSI-5A4E 来源映射及未决差异

状态：仅记录来源，不放行来源门槛，不修改材料常数、模型或历史收据。2026-10-01 在线阅读核对了以下官方页面；未提交供应商全文、HTML 或 PDF。

| 来源 | 可支持的事实 | 未决差异 |
|---|---|---|
| [当前官方材料 HTML](https://piezo.com/pages/piezo-material)，PSI-5A4E 列 | Y₁ᴱ=66 GPa；d₃₁=−190 pC/N；ε₃₃ᵀ/ε₀=1800（1 kHz）；密度7800 kg/m³ | 只支持这些典型标量，不证明完整张量或实际器件牌号；同表 k₃₁=0.35 |
| [20201112 官方 PDF，第1页](https://info.piezo.com/hubfs/Data-Sheets/piezo-material-properties-data-sheet-20201112.pdf)，PZT-5A 列 | 密度7.95 g/cm³，即7950 kg/m³ | 与当前 HTML 的7800不同，不混用表格 |
| [官方支持页](https://support.piezo.com/article/62-material-properties) | 将 PSI-5A4E 对应至3195HD | 型号映射不消除不同表格的数值差异 |
| [旧材料 PDF，第1页](https://info.piezo.com/hubfs/Data-Sheets/piezo-PZT-5A_PZT-5H-material-properties.pdf)，3195HD 列 | 相对介电常数1900；Y₁₁ᴱ=67 GPa | 与当前 HTML 的1800、66 GPa不同，不代入替换现有输入 |

所提供的新采集记录对应[官方材料页面](https://piezo.com/pages/piezo-material)，采集时间为 `2026-10-01T19:19:52Z`，来源身份为 `PSI-5A4E.current-official-HTML.20261001T191952Z`，110488 bytes，SHA-256 `857eb898d824bec3eee1a35bee214047c1eeeeab8039b1ec6a261d6602810136`。该字节身份来自所提供的采集记录；本审计仅在线核对内容，没有取得或重新验证该特定快照字节，不能把动态页面当作同一文件哈希证明。

原 `840af517…` HTML 和 catalog 历史快照仍未取得；历史来源封存保持 blocked。新来源身份不能补写为旧来源，也不授权重新运行或改写历史实验。

`ε̄ = εᵀ − Y d²` 是带有横向应力自由等约束假设的条件标量约化，不是完整三维夹持介电张量 εˢ。使用上述四个标量推导的 k₃₁ 约0.38665，与表列0.35不一致；仍待澄清，不能通过混用另一张表使其表面一致。原生 COMSOL PZT-5A 完整张量及实际器件牌号仍未知。此说明不建立这些材料身份间的等价关系。
