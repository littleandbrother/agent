# 本地大型原生文件完整性收据补充

LOCAL-INTEGRITY-20261001.json 是所提供脱敏收据的原样 UTF-8 JSON（含末尾换行）：9633 bytes，SHA-256 `9c762dcb27edc4f345ede839cf8fada0b3147ce780b80b31362c659d051ef5e1`。来源记录称本地于2026-10-01 19:44:15–19:44:56 UTC 对24个保留文件读取688230224字节，大小与哈希全部符合预期且检查期间稳定。P/R是一个数据集的路径别名。

CROSSCHECK.json 仅独立核对该收据自身字节身份、相对路径集合、期望/实际大小和哈希与固定轻量归档中的 large-native-artifacts.json 相符。该清单 SHA-256 为 `55e7ada0d4e9bc091a65e7a2c8f34cdefddadbf1c322c2eb7e49518dd1816590`。本检查没有打开任何大型原生文件，没有重新读取它们，没有收到或重放RAW。

```bash
python3 -B research/bf-design-integration/analysis/pilot/check_local_receipt.py --archive release/evidence/door-design-pilot-v1.zip --receipt research/bf-design-integration/analysis/pilot/source-receipts/LOCAL-INTEGRITY-20261001.json --out /tmp/new-local-integrity-crosscheck.json
python3 -B -m unittest discover -s research/bf-design-integration/analysis/pilot -p 'test_local_receipt.py' -v
```

原 AUDIT.json 和旧交付清单保持字节不变。其“云端缺原生字节”判断仍成立；新收据只补充本地保留文件完整性的来源。缺失通道、能量积分未重放、物理验收和Agent资格均不改变。原始未脱敏收据的哈希仅为来源声明，本目录未持有其字节；不把该声明当作独立复核结果。
