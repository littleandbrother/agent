#!/usr/bin/env python3
"""Fixed edge regressions plus new paraphrases after the initial 48-case audit."""
import hashlib
import json
from pathlib import Path
from run import ROOT, DATA, model_call, parse_json, prompt, validate, save


def main():
    corpus={r['id']:r['request'] for r in json.loads((DATA/'requests.json').read_text())}
    cases=[{'id':q,'request':corpus[q],'kind':'known-regression'} for q in ('Q38','Q43','Q44','Q46','Q47')]
    extra=['这个想法先帮我判断可不可行，暂时别改工程。',
        '看一下附件里的方案有没有明显漏洞。',
        '我只想把桥式整流的损耗降下来。',
        '改变采样频率和储能容量，尽量减少漏采。',
        '设备不能用电池，也没有外部能量，要求持续发信号。',
        '先把这篇论文的曲线复现出来，再讨论产品怎么做。',
        '做一个按下就留下标记的机械装置，不要电路。',
        '只检查板子的连接器能不能和现有外壳对上。']
    cases += [{'id':f'N{i+1:02d}','request':q,'kind':'new-paraphrase'} for i,q in enumerate(extra)]
    save(ROOT/'edge-checks/freeze.json',{'prompt_sha256':hashlib.sha256(prompt().encode()).hexdigest(),'cases':cases,
        'interpretation':'Targeted engineering regression and new paraphrases, following inspection of the initial corpus.'})
    results=[]
    for c in cases:
        raw=model_call('edge-v3-'+c['id'],prompt(),c['request'],6500)
        row={**c,'finish_reason':raw['choices'][0]['finish_reason']}
        try:
            row['assessment']=parse_json(raw); row['validated']=validate(c['request'],row['assessment']);row['valid']=True
        except (ValueError,TypeError,KeyError) as e:row['valid']=False;row['error']=str(e)
        save(ROOT/'edge-checks'/f"{c['id']}.json",row);results.append(row)
        print(c['id'],row['valid'],flush=True)
    save(ROOT/'edge-checks/result.json',{'count':len(results),'valid':sum(r['valid'] for r in results),'results':results})


if __name__=='__main__':main()
