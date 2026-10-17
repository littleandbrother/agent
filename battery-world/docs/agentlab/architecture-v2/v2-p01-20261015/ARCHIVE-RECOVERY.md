# 恢复归档读取入口

实际 Lead 恢复反复读取 `context-records/*.tool.txt`，返回 `WORKSPACE_FILE_NOT_FOUND`。归档位于 owner 的 `participants` 目录，原工具把它当成设计工作区文件。

- 新入口：`bf_repository(action="archive_read",path,offset?,limit?,pointer?)`。
- 按 owner 与内容 SHA 读取；校验原始记录及工具文本；支持 JSON 字段选择。
- 旧 `read` / `workspace_read` 归档引用兼容；提示明确给出实际入口。
- 路径越界、跨 owner、篡改、符号链接及私有模型推理被拒绝。
- 归档读取保持工程、原始会话、费用、作业不变。

168 项 Repository 回归、114 项上下文回归通过；Pi 离线构建与完整检查通过。

连续设计审查从指定起点计算提交链。旧基准审查分支保留为历史；声明变更、缺独立结果、缺 BF 决定或缺同版包不计为完整设计轮次。
