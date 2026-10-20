# 只读核对与重建入口

权威集成工作区：`workbench/bf-campaign-s0-20261019/battery-world`。不要在原 V2 或旧 owner 上运行 start/drive/prepare。四个尝试已终止，不允许补跑；以下不请求模型或求解。

## 核对固定事实

在集成 battery-world 内：

```sh
rtk proxy python3 docs/research/parallel-20261019/methods/audit_paid.py
rtk proxy python3 docs/research/parallel-20261019/methods/verify_artifacts.py --check
```

第一条从原 runtime 请求、轨迹、设备与停止回执生成确定性审计；第二条只读核对全部已结束尝试的缓存、产物及三份交付包，不覆盖封存检查回执。

A/R 原始封存复核命令见 `docs/research/parallel-20261019/reference/REPRODUCE.md`；P1 的控制、格式事实、观察程序与复现命令见 `docs/research/parallel-20261019/interfaces/PROTOCOL.md`。

## 测试必须带登记隔离环境

不能仅执行裸 `./init.sh`，因为 S0 源码有运行环境保护标记。以下使用已登记 profile；不更改它、密钥、旧数据库或工具身份：

```sh
rtk proxy python3 - <<'PYCODE'
import json, os, subprocess
from pathlib import Path
runtime = Path.home()/'.local/share/bf-campaign-20261019-s0'
p = json.loads((runtime/'profile.json').read_text())
env = dict(os.environ, **{'BF_'+k:v for k,v in p['paths'].items()})
env.update(BF_RUNTIME_ROOT=str(runtime), BF_RUNTIME_CONFIG=p['configuration'],
           BF_DEVELOPMENT_PROFILE=str(runtime/'profile.json'),
           PI_CODING_AGENT_DIR=str(runtime/'workbench/pi-config'),
           PYTHONPATH=str(Path.cwd()/'packages/python/bfworld/src'),
           BFWORLD_VERIFY_PROFILE='architecture-v2-ci')
subprocess.run(['./init.sh'], env=env, check=True, timeout=90)
subprocess.run([p['paths']['CAD_PYTHON'],'-m','unittest',
 'tests.agentlab.test_campaign_reference','tests.agentlab.test_campaign_interfaces',
 'tests.agentlab.test_campaign_methods','-v'], env=env, check=True, timeout=60)
PYCODE
```

这是 343 项 V2 回归与 34 项本批定向资格检查，不等于全根仓库检查或硬件验收。最终原始日志在 `shared/final-init.log`、`shared/final-targeted-tests.log`。

## 稿件

结果生成器及构建日志保存在各自 `papers/` 目录。论文二先运行 `render_results.py`，再从其目录使用安装的 `pdflatex -interaction=nonstopmode -halt-on-error -output-directory=build main.tex` 两遍。论文一使用 `manuscript.tex`。重建 PDF 可能改变时间戳；封存版本的 SHA 和全部页面检查见 `shared/manuscript-verification.json`。两篇均为正文骨架和结果段落，尚非完整投稿稿。

集成源码的逐件核对与可移植增量由根目录的 `publish_integration.py` 管理，见 `integrated-v1/manifest.json`。该版本不是 Git 提交；原始共同输入基线继续保留，后续任务应显式登记新输入身份。
