# 1.2.0-eritque-arcus.1

1. `execute` 支持 `timeoutMs` 覆写执行超时（上限 600s），回显生效值
2. 大结果分块传输 `result_chunk`：阈值 512 KB / 分片 256 KB，按 `(id, seq)` 重组
3. `error` 信封附带 `stack`

# 1.1.0

1. 二进制返回值 base64 编码为 `__edaBinary` 信封
2. 指数退避持续重试；缓存上次成功端口并优先重连
3. 代码执行加超时保护（`EXECUTE_TIMEOUT_MS`）
4. 注册时附带工程名标签
5. 结果序列化处理循环引用 / BigInt

---

以上为本分支（Eritque arcus）的改动，非上游发布；基线为上游 `1.0.5`。
