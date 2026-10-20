# 只读复核

在battery-world目录运行：

```sh
python3 docs/agentlab/architecture-v2/node-engineering-20261019/verify_saved.py
BFWORLD_VERIFY_PROFILE=architecture-v2-ci ./init.sh
```

第一条核对已封存工程文件、ZIP、原生工程、STEP读回和目标构建记录；第二条运行Repository回归及封存协议检查。两条均不派发模型或原生作业。

Pi源码检查：在`../pi-bf-aiot`运行`npm run check`。

目标固件异目录复建见工程包README：`rebuild-target.py --sdk <fixed SDK> --compiler-bin <fixed GCC bin> --output <new directory>`。这一步只编译目标源码。

工程包解压后打开`index.html`；CAD打开`assembly.step`；立创专业版导入`native/project.epro2`。原始求解资料保存在`reference/`。本轮完整handoff.zip和平台审查ZIP路径记录在RESULTS.json与Lab下载入口中。
