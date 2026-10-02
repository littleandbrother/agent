"""Operator-only architecture and development observations; never an executor API.

Snapshots contain allowlisted source bytes, including uncommitted files. The
module manifest is a declared architecture, not an inferred function call graph.
"""
import contextlib
import difflib
import fcntl
import hashlib
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from .store import canonical

REPO = Path(__file__).resolve().parents[6]
from .runtime_config import PI
PY = 'packages/python/bfworld/src/bfworld/'
LAB = PY + 'agentlab/'
MODULES = [
    dict(id='ui', title='任务与工作台', layer='界面', description='对话、控制台与全景的展示和交互。', console='trace', x=45, y=55,
         paths=[('world', 'apps/agent-studio/')]),
    dict(id='sessions', title='会话与产品', layer='服务', description='会话、文件夹、消息恢复和产品方案版本。', console='context', x=365, y=55,
         paths=[('world', LAB+n) for n in ['server.py','chat.py','concurrency.py','organization.py','product.py','assembly.py','progress.py','recall.py','product_authority.py','deliverables.py','design_review.py']]),
    dict(id='pi', title='Pi Agent', layer='执行', description='模型对话循环与公开工具事件；不推测私有推理。', console='trace', x=685, y=55,
         paths=[('pi','packages/bf-agent/src/'),('pi','packages/coding-agent/src/core/agent-session.ts')]),
    dict(id='harness', title='Harness 程序', layer='策略', description='求解与改进程序，独立冻结并验证实际加载身份。', console='harness', x=1005, y=55,
         paths=[('pi','packages/bf-harness/src/')]),
    dict(id='memory', title='记忆与配置', layer='配置', description='Memory、提示词和候选配置；保存不等于当前已加载。', console='memory', x=1005, y=295,
         paths=[('world',LAB+'developer.py')]),
    dict(id='tools', title='工具与工程环境', layer='能力', description='Tools、Skills、MCP、联网参考、原生 CAD / Blender / COMSOL / 立创、布线及耦合瞬态求解。', console='tools', x=685, y=295,
         paths=[('world',LAB+n) for n in ['engineering.py','engineering_projects.py','beam_event.py','engineering_templates/','jlceda.py','eda_mcp.py','product_build.py','freerouting.py','references.py','event_design.py','event_measurement.py']]),
    dict(id='runtime', title='受控执行与存储', layer='运行时', description='任务、预算、冻结版本、实验和不可变产物。', console='experiments', x=365, y=295,
         paths=[('world',LAB+n) for n in ['store.py','provider.py','launcher.py','runtime_config.py','context.py','experiments.py']]+[('world',PY+n) for n in ['runtime/','bundle/','application/']]),
    dict(id='world', title='科学计算环境', layer='环境', description='耦合计算与参考环境；计算结果不代表硬件验证。', console='experiments', x=45, y=295,
         paths=[('world',PY+'coupled/'),('world',PY+'worlds/')]),
    dict(id='trace', title='Trace 与观测', layer='证据', description='原始记录、请求用量、工具与开发变化的只读投影。', console='trace', x=365, y=535,
         paths=[('world',LAB+n) for n in ['trace_review.py','trace_analysis.py','panorama.py']]),
    dict(id='validation', title='验证与版本演化', layer='验证', description='代码检查、候选谱系及既有实验报告；各自绑定范围。', console='rsi', x=685, y=535,
         paths=[('world',PY+'verification/'),('world','tests/agentlab/'),('world','scripts/run_panorama_check.py')]+[('world',LAB+n) for n in ['study.py','recursive.py','product_evidence.py','product_energy.py']]),
]
EDGES = [dict(id=f'{a}-{b}', source=a, target=b, relation=r, provenance='declared') for a,b,r in [
    ('ui','sessions','HTTP / 消息'),('sessions','pi','启动与消息'),('harness','pi','加载程序'),
    ('memory','harness','生成候选'),('pi','tools','工具调用'),('tools','runtime','工程任务'),
    ('pi','runtime','实验请求'),('runtime','world','计算'),('runtime','trace','持久记录'),
    ('pi','trace','公开事件'),('world','validation','验证产物'),('validation','harness','候选检查'),
    ('sessions','tools','产品版本 / 工程输入'),('tools','validation','原生读回 / 引脚 / 固件'),('validation','sessions','版本绑定检查'),
]]
MODULES += [
    dict(id='research', title='研究协议与机制实验', layer='研究', description='冻结状态、隔离分支、证据支持、独立验收与 A/B/C 先导；受阻项不冒充成果。', console='research', x=365, y=775,
         paths=[('world',LAB+'research/'),('world','scripts/run_research.py'),('world','tests/agentlab/test_research.py')]),
    dict(id='firmware', title='MCU 固件与烧录', layer='部署', description='目标 C 源码、ELF/BIN、引脚、构建和烧录脚本；板上测量独立记录。', console='delivery', x=45, y=535,
         paths=[('world',LAB+'deployment.py'),('world',LAB+'engineering_templates/companion_main.c'),('world',LAB+'engineering_templates/flash_mcu.py')]),
    dict(id='tinyml', title='神经网络与 NAS', layer='学习', description='数据划分、候选架构、训练、量化、参数量和资源；估算与 MCU 实测分离。', console='delivery', x=1005, y=535,
         paths=[('world',LAB+'tinyml.py'),('world',LAB+'engineering_templates/tinyml_search.py')]),
]
EDGES += [dict(id='tools-tinyml',source='tools',target='tinyml',relation='有界训练与搜索',provenance='declared'),
          dict(id='research-runtime',source='research',target='runtime',relation='冻结条件 / 隔离试验 / 研究预算',provenance='declared'),
          dict(id='research-validation',source='research',target='validation',relation='独立验收 / 支持关系',provenance='declared'),
          dict(id='research-trace',source='research',target='trace',relation='声明范围的研究事件与导出',provenance='declared'),
          dict(id='tinyml-firmware',source='tinyml',target='firmware',relation='量化 C 模型 / 目标编译',provenance='declared'),
          dict(id='firmware-validation',source='firmware',target='validation',relation='构建与测量证据',provenance='declared')]
EXTENSIONS = {'.py','.ts','.js','.cjs','.mjs','.css','.html','.java','.c','.h','.ld'}
MAX_BYTES = 2_000_000


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def is_cloud_file(path):
    # macOS UF_DATALESS: reading may block indefinitely on FileProvider.
    return bool(getattr(Path(path).stat(), 'st_flags', 0) & 0x40000000)


def local_text(path):
    if is_cloud_file(path):
        raise ValueError('PANORAMA_CLOUD_FILE_UNAVAILABLE: 请先下载本机云端占位文件 ' + Path(path).name)
    return Path(path).read_text()


class Panorama:
    def __init__(self, root, repos=None, modules=None):
        self.root = Path(root) / 'panorama'
        self.repos = repos or {'world': REPO, 'pi': PI}
        self.modules = modules if modules is not None else MODULES
        self.mutex = threading.RLock()
        for directory in ['snapshots','blobs','checks']:
            (self.root/directory).mkdir(parents=True, exist_ok=True)

    @contextlib.contextmanager
    def locked(self):
        with self.mutex, (self.root/'lock').open('a') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            yield

    def put(self, path, raw):
        if path.exists():
            if is_cloud_file(path):
                raise ValueError('PANORAMA_CLOUD_FILE_UNAVAILABLE: ' + path.name)
            if path.read_bytes() != raw:
                raise ValueError('PANORAMA_IMMUTABLE_HASH_MISMATCH')
            return
        temporary = path.with_suffix('.tmp-'+str(os.getpid()))
        temporary.write_bytes(raw)
        os.replace(temporary, path)

    def read_snapshot(self, key):
        if not re.fullmatch('[a-f0-9]{64}', key or ''):
            raise ValueError('PANORAMA_SNAPSHOT_REQUIRED')
        path = self.root/'snapshots'/(key+'.json')
        if not path.is_file():
            raise ValueError('PANORAMA_SNAPSHOT_NOT_FOUND')
        value = json.loads(local_text(path))
        if digest(canonical(value['manifest']).encode()) != key:
            raise ValueError('PANORAMA_SNAPSHOT_HASH_MISMATCH')
        return value

    def scan(self):
        """One observed workspace snapshot, not a claim of atomic filesystem state."""
        with self.locked():
            files, skipped = {}, []
            for module in self.modules:
                for repo, prefix in module['paths']:
                    root = Path(self.repos[repo]).resolve()
                    base = root/prefix
                    paths = sorted(base.rglob('*')) if base.is_dir() and not base.is_symlink() else [base]
                    if not base.exists():
                        skipped.append(dict(path=repo+':'+prefix, reason='missing'))
                    for p in paths:
                        if p.suffix not in EXTENSIONS or not p.is_file() or '__pycache__' in p.parts:
                            continue
                        if p.is_symlink() or any(q.is_symlink() for q in p.parents if q != root and root in q.parents) or not p.resolve().is_relative_to(root):
                            skipped.append(dict(path=repo+':'+str(p.relative_to(root)),reason='symlink'))
                            continue
                        key = repo+':'+p.relative_to(root).as_posix()
                        if key in files:
                            files[key]['modules'].append(module['id'])
                            continue
                        try:
                            before = p.stat()
                            if is_cloud_file(p):
                                skipped.append(dict(path=key, reason='cloud_placeholder')); continue
                            if before.st_size > MAX_BYTES:
                                skipped.append(dict(path=key,reason='too_large')); continue
                            raw = p.read_bytes()
                            after = p.stat()
                            if (before.st_mtime_ns,before.st_size) != (after.st_mtime_ns,after.st_size):
                                skipped.append(dict(path=key,reason='changed_during_read')); continue
                            raw.decode('utf-8')
                        except (OSError,UnicodeError):
                            skipped.append(dict(path=key,reason='unreadable')); continue
                        sha = digest(raw)
                        self.put(self.root/'blobs'/sha, raw)
                        files[key] = dict(path=p.relative_to(root).as_posix(),repo=repo,sha256=sha,size=len(raw),modules=[module['id']])
            manifest = dict(schema_version='bf-panorama-snapshot-v1',files=files,skipped=skipped,modules=self.modules,edges=EDGES)
            key = digest(canonical(manifest).encode())
            path = self.root/'snapshots'/(key+'.json')
            if not path.exists():
                previous = json.loads(local_text(self.root/'latest.json'))['id'] if (self.root/'latest.json').exists() else None
                self.put(path,canonical(dict(id=key,created=time.time(),parent=previous,manifest=manifest)).encode())
            (self.root/'latest.json').write_text(canonical(dict(id=key,observed_at=time.time())))
            return self.read_snapshot(key)

    def blob(self, key):
        if not re.fullmatch('[a-f0-9]{64}',key or ''):
            raise ValueError('PANORAMA_BLOB_DENIED')
        p = self.root/'blobs'/key
        if not p.is_file() or is_cloud_file(p):
            raise ValueError('PANORAMA_SOURCE_MISSING_OR_CLOUD_ONLY')
        if digest(p.read_bytes()) != key:
            raise ValueError('PANORAMA_SOURCE_MISSING_OR_CORRUPT')
        return p.read_text()

    def file(self, snapshot, key, baseline=None):
        current = self.read_snapshot(snapshot)
        item = current['manifest']['files'].get(key)
        old = self.read_snapshot(baseline)['manifest']['files'].get(key) if baseline else None
        if item is None and old is None:
            raise ValueError('PANORAMA_FILE_NOT_IN_SNAPSHOT')
        content = self.blob(item['sha256']) if item else ''
        before = self.blob(old['sha256']) if old else ''
        return dict(path=key,snapshot=snapshot,baseline=baseline,exists=item is not None,content=content,
                    sha256=item['sha256'] if item else None,
                    diff=''.join(difflib.unified_diff(before.splitlines(True),content.splitlines(True),fromfile='基线/'+key,tofile='所选版本/'+key)) if baseline else None)

    def checks(self, snapshot):
        out=[]
        for p in sorted((self.root/'checks').glob('*.json'),reverse=True):
            row=json.loads(p.read_text())
            row['freshness']='current' if row['snapshot']==snapshot and row['snapshot']==row['end_snapshot'] else 'stale'
            out.append(row)
        return sorted(out,key=lambda c:c['ended'],reverse=True)

    def projection(self, snapshot=None, baseline=None):
        with self.locked():
            latest = json.loads(local_text(self.root/'latest.json')) if (self.root/'latest.json').exists() else None
            if latest is None:
                return dict(empty=True,modules=self.modules,edges=EDGES,snapshots=[],checks=[])
            current = self.read_snapshot(snapshot or latest['id'])
            paths=list((self.root/'snapshots').glob('*.json'))
            unavailable=[p.stem for p in paths if is_cloud_file(p)]
            history = sorted([self.read_snapshot(p.stem) for p in paths if p.stem not in unavailable], key=lambda x:x['created'],reverse=True)
            baseline = baseline or (current['parent'] if current['parent'] not in unavailable else None) or current['id']
            old = self.read_snapshot(baseline)
            files, before = current['manifest']['files'], old['manifest']['files']
            changes=[]
            skipped_keys={x['path'] for x in current['manifest']['skipped'] if x['reason'] != 'missing'}
            for key in sorted(set(files)|set(before)):
                a,b=before.get(key),files.get(key)
                if a and b and a['sha256']==b['sha256']:continue
                changes.append(dict(key=key,kind='unavailable' if key in skipped_keys else 'added' if not a else 'deleted' if not b else 'modified',modules=(b or a)['modules']))
            return dict(schema_version='bf-panorama-view-v1',empty=False,snapshot=current['id'],baseline=baseline,
                        created=current['created'],observed_at=latest['observed_at'],latest=latest['id'],
                        modules=current['manifest']['modules'],edges=current['manifest']['edges'],files=files,changes=changes,
                        snapshots=[dict(id=s['id'],created=s['created'],parent=s['parent'],files=len(s['manifest']['files'])) for s in history],
                        checks=self.checks(current['id']),skipped=current['manifest']['skipped'],unavailable_snapshots=unavailable,
                        actor=None,scope='工作台、Pi 定制入口与关联计算模块；非全仓库调用图',
                        boundary='连线为架构声明；文件来自所选快照。工作区变更不自动归因于 Agent。检查仅适用于其绑定版本及范围。')

    def run_check(self, command, cwd, label, timeout=600):
        """Local operator CLI only. The HTTP interface never dispatches commands."""
        start=self.scan(); started=time.time()
        log=self.root/'checks'/(str(time.time_ns())+'.log')
        with log.open('wb') as output:
            try:
                result=subprocess.run(command,cwd=cwd,stdout=output,stderr=subprocess.STDOUT,timeout=timeout)
                code=result.returncode
            except subprocess.TimeoutExpired:
                output.write(b'\nCHECK_TIMEOUT\n');code=124
        end=self.scan(); ended=time.time()
        row=dict(schema_version='bf-development-check-v1',id=log.stem,label=label,command=command,cwd=str(cwd),
                 snapshot=start['id'],end_snapshot=end['id'],started=started,ended=ended,exit_code=code,
                 result='passed' if code==0 else 'failed',log=log.name,log_sha256=digest(log.read_bytes()),
                 scope='命令实际覆盖范围；不代表全部功能或产品达标',actor='local-operator-command')
        with self.locked():self.put(log.with_suffix('.json'),canonical(row).encode())
        return row

    def check_log(self, key):
        if not re.fullmatch(r'\d+',key or ''):raise ValueError('PANORAMA_CHECK_DENIED')
        meta=json.loads((self.root/'checks'/(key+'.json')).read_text())
        raw=(self.root/'checks'/meta['log']).read_bytes()
        if digest(raw)!=meta['log_sha256']:raise ValueError('PANORAMA_CHECK_HASH_MISMATCH')
        return dict(record=meta,text=raw.decode('utf-8',errors='replace'))
