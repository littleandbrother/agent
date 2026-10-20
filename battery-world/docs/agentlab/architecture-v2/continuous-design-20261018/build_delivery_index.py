"""List the verified same-version PDF and engineering packages, without dispatch."""
import argparse
import hashlib
import json
from pathlib import Path


def read(path):return json.loads(path.read_text())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime',type=Path,default=Path.home()/'.local/share/bf-agent-architecture-v2')
    args=parser.parse_args()
    folder=Path(__file__).parent;root=args.runtime/'continuous-design'
    summary=read(folder/'results/summary.json');audit=read(root/'verification-all.json')
    repo=args.runtime/'workbench/design-lab/repository';rows=[]
    def item(label,system,passed,release):
        pdf=archive=None
        if release:
            pointer=read(repo/'task-reports/by-system'/(system+'.json'))
            pdf=repo/'task-reports'/pointer['id']/'task-report.pdf'
            archive=repo/'releases'/(release+'.zip')
            seal=read(archive.with_suffix('.seal.json'))
            if seal['target']!=system:raise ValueError('DELIVERY_INDEX_VERSION_MISMATCH')
        rows.append({'label':label,'system':system,'service_passed':passed,'release':release,
            'pdf':str(pdf) if pdf else None,
            'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest() if pdf else None,
            'archive':str(archive) if archive else None,
            'archive_sha256':seal['sha256'] if archive else None})
    for cycle in audit['cycles']:
        item('原会话第'+str(cycle['cycle'])+'轮',cycle['system'],cycle['task_passed'],cycle['release'])
    for trial in summary['trials']:
        if trial['stage']!='organizations':continue
        trial_root=root/'pilot/trials'/trial['key']
        final=read(trial_root/('recovery-final.json' if trial['preflight_recovery'] else 'final.json'))
        releases=[r['id'] for r in final['view']['releases'] if r['target']==trial['current_system']]
        item(trial['case']+' / '+trial['organization'],trial['current_system'],trial['valid_service'],
            releases[-1] if releases else None)
    value={'audit_sha256':hashlib.sha256((root/'verification-all.json').read_bytes()).hexdigest(),
        'summary_sha256':hashlib.sha256((folder/'results/summary.json').read_bytes()).hexdigest(),
        'deliveries':rows}
    (folder/'results/delivery-index.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    lines=['# 同版交付物','', '| 运行 | 服务结果 | PDF | 工程包 |', '|---|---|---|---|']
    for row in rows:
        link=lambda key,label:'['+label+'](<'+row[key]+'>)' if row[key] else '未生成'
        lines.append('| '+row['label']+' | '+('通过' if row['service_passed'] else '未通过')+
            ' | '+link('pdf','报告')+' | '+link('archive','ZIP')+' |')
    lines+=['','候选完整身份、文件摘要及核对记录见 `results/delivery-index.json`。','']
    (folder/'DELIVERIES.md').write_text('\n'.join(lines))
    print(json.dumps({'candidates':len(rows),'pdf_and_package':sum(bool(r['pdf']) for r in rows)}))


if __name__=='__main__':main()
