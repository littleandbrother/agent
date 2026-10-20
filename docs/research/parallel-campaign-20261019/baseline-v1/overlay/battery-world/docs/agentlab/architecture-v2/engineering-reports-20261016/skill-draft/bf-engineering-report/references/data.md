# 数据合同草稿

- `report-input.json`：明确项目、系统候选、采用版、所选作业、当前检查及来源文件。
- `assets[]`：kind、path、job_id、local_path、sha256、bytes、system_commit。
- `report-facts.json`：从候选及独立检查提取的参数；保留每类参数的来源。
- `asset-inventory.json`：每页已有材料、缺项、负责专业与验收条件。
- `native-previews.json`：原生 SVG、派生图片的摘要以及渲染器版本。
- `verification/result.json`：PDF 身份、页数、字体、来源摘要、状态保护核对。

Pi 补齐的每份图需提交：图源、输出图、来源文件与摘要、处理命令、图注、所属候选。新增分析需写明输入、单位、计算口径与结果。工程修订通过原设计工具提交，报告按新候选重新收集。
