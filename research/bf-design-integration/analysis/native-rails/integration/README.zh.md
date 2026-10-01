# 仓库集成核对

14个已审查文件通过Git交付提交75665207239e5c9f6de265473a9ba3c7677daad4进入此目录，保持原始字节。bundle-sha256.json列出的13个载荷大小/哈希均匹配；脚本与结果额外对照指定的固定SHA。integration/是单独的集成说明和本环境检查记录，不属于原审查包。

本环境已运行：

```bash
python3 -B research/bf-design-integration/analysis/native-rails/replay_native_rails.py --self-test
```

21项内置合成/安全检查通过。软件版本和逐项结果见VERIFY.json。本环境未取得coarse/fine CSV以及完整输入集，没有进行真实CSV重放；原results.json是保存的已审查结果，不是本环境新生成结果。独立审查所记完整重放、21内置+61附加检查见原independent-review.json / review-summary.txt，执行来源保持区分。

原冻结末0.5/1秒窗口判据通过并存在小幅漂移，只说明这些窗口判据。波形收敛判定仍为null；source-off为合成基线标记，不能当作物理断源。CAP/VIN2只是局部支路记账，不证明全系统能量闭合、无隐藏初能、自供能、硬件或Agent收益。

保留method-freeze.json与既有结果，不改阈值、不重写历史收据、不执行求解器或模型。此处不包含CSV、RAW、供应商正文或二进制，也未复制ZIP。需要完整复核时，具有原始授权输入的本地协调者按上级README.txt调用离线重放，输出必须为新的直接子目录。生产桥接、原生观察、Pi和UI仍由BFA-035负责。
