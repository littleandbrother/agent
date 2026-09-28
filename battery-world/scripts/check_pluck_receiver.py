#!/usr/bin/env python3
"""Offline receiver fault acceptance; synthetic captures explicitly labelled."""
import argparse
import json
from pathlib import Path
from pluck_receiver import group, fit_direction, direction


def run(output):
    output.mkdir(parents=True,exist_ok=False)
    payload=(b'BFP1'+bytes.fromhex('0102030405060708')).hex()
    def records(times, label):
        return [{'capture_id':label+'-'+str(i),'time_s':t,'payload_hex':payload,'origin':'synthetic-link-test'} for i,t in enumerate(times)]
    nominal=records([.4,.5,.6,.7,.8], 'nominal')
    duplicate=nominal+[nominal[2].copy()]
    loss=[x for i,x in enumerate(nominal) if i not in (1,3)]
    delayed=records([.4,.5,1.2,1.3], 'delayed')
    reboot=records([.4,.5,.65,.75], 'reboot')
    calibration=[{'id':f'{label}-{i}','label':label,'packets':n} for label,ns in [('open',[2,3,4]),('close',[8,9,10])] for i,n in enumerate(ns)]
    classifier=fit_direction(calibration)
    overlap=fit_direction([{'id':f'{label}-{i}','label':label,'packets':n} for label,ns in [('open',[2,3,5]),('close',[4,5,6])] for i,n in enumerate(ns)])
    cases={'nominal':nominal,'duplicate_capture':duplicate,'packet_loss':loss,'delay_over_group_gap':delayed,'reboot_without_identity':reboot,'no_event':[]}
    raw=[];results={}
    for label,rows in cases.items():
        raw += [{'case':label,**row} for row in rows]
        results[label]={'events':group(rows),'ground_truth':'synthetic receiver fixture; no physical motion'}
    heldout=[('open',3),('close',9),('unknown',6),('unknown',20)]
    confusion={label:{pred:0 for pred in ('open','close','unknown')} for label in ('open','close','unknown')}
    for label,n in heldout:confusion[label][direction(n,classifier)]+=1
    checks={
        'nominal_one_group':len(results['nominal']['events'])==1,
        'copied_row_deduplicated':results['duplicate_capture']['events'][0]['packets']==5,
        'loss_retains_three':results['packet_loss']['events'][0]['packets']==3,
        'delay_splits_reported':len(results['delay_over_group_gap']['events'])==2,
        'no_input_no_event':not results['no_event']['events'],
        'overlap_abstains':not overlap['qualified'] and direction(4,overlap)=='unknown',
        'out_of_range_abstains':direction(20,classifier)=='unknown',
        'unknown_reboot_not_invented':results['reboot_without_identity']['events'][0]['reboot_identity_available'] is False,
        'no_default_direction':all(e['direction']=='unknown' for v in results.values() for e in v['events']),
    }
    report={'schema_version':'bf-receiver-acceptance-v1','checks':checks,'software_checks_passed':all(checks.values()),'cases':results,
        'classifier':classifier,'overlap_classifier':overlap,'heldout_confusion':confusion,
        'hardware_verified':False,'direction_calibrated':False,'service_qualified':False,
        'limitations':['BFP1 has no boot/sequence identity: true radio duplicates and quick reboots cannot be distinguished.',
        'Silence grouping splits one event with a long outage and merges events less than 0.35 s apart.',
        'Separable synthetic distributions test the classifier implementation only; real direction remains unknown.']}
    (output/'captures.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in raw))
    (output/'calibration.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in calibration))
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    import shutil
    shutil.copy2(__file__,output/'check_pluck_receiver.py')
    shutil.copy2(Path(__file__).with_name('pluck_receiver.py'),output/'pluck_receiver.py')
    (output/'PROTOCOL.md').write_text('''# BFP1 接收协议与限制

BLE manufacturer company ID 0xffff（实验值）；负载12字节：ASCII BFP1 + 8字节nRF FICR设备ID。
广告间隔100ms，当前固件没有boot ID或packet sequence。接收器以同设备0.35s静默分组。
TX完成、广播报告、推断事件分别记录；没有实物真值时不宣称真正门窗动作被正确识别。
capture_id 仅消除重复导入的同一日志行，不能解决无线重复包。相邻重启可能合并，长丢包可能拆分。
未提供实物或经过校准的两类分布时方向为unknown。fit_direction的合成分布只测试代码，不能升级成产品准确率。

运行 `python check_pluck_receiver.py --output new-run` 生成独立回放。
运行 `python pluck_receiver.py --replay captures.jsonl` 回放；各case测试应单独取出，不能把不同case当同一真实capture。
有硬件后安装bleak，`python pluck_receiver.py --capture capture.jsonl --seconds 30`。
本轮未启动蓝牙采集，也未烧录MCU。
''')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(run(a.output)['checks']))
