#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import time
APP=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(APP/'packages/python/bfworld/src'))
from bfworld.agentlab.design_lab.physical import readiness,CHANNELS
from bfworld.agentlab.design_lab.contracts import sealed
root=APP/'docs/agentlab/refactor-r3-r5-20261012'/('physical-readiness-'+str(time.time_ns()))
root.mkdir(parents=True)
v=readiness();sealed(root/'readiness.json',v)
(root/'capture-template.csv').write_text(','.join(CHANNELS)+'\n')
sealed(root/'measurement-template.json',{'origin':'UNCONFIRMED','acquisition_id':None,'instrument_id':None,
 'calibration_receipt':None,'design_id':None,'target_build_id':None,'board_revision':None,
 'units':dict(zip(CHANNELS,['s','V','V','A','uint32','uint32'])),'initial_storage_V':None,
 'event_zero_definition':None,'channels_and_probes':{},'raw_sha256':None,
 'scope':'Template only, not an actual measurement or authorization to flash an unidentified target'})
(root/'MEASUREMENT-PLAN.md').write_text('''# R5 实物标定与端到端验证准备

当前没有已确认可用的板卡／采能器／测量仪器或本次原始测量。准备文件不授予物理 PASS。

1. 固定 Case、采用设计 D、实际板卡/BOM/接收端与目标 ELF/HEX；核对 D5 提取和门控实际是否上板。旧 D4 板不自动取得 D5 资格。
2. 记录测量仪器、探头、采样频率、时钟、量程、校准及误差；探头负载和电流取样压降计入回路。
3. 定义事件时间零点；放空／测量初始储能。同步采集储能、MCU 电源、电流和实际 RX；禁止把 TX GPIO 当接收确认。
4. 先断源、错事件、接收丢失等负控，再做规定动作。A 记录全部外部请求和连续趋势；B 一次动作并排除次动作补能；C 覆盖完整关门积能与开门响应。
5. 保存仪器原始格式和无损 CSV、通道单位、采集日期、设备及设计身份。操作人员独立登记 acquisition；Agent 自填 measured 不会获得测量资格。
6. 对照数字预测及不确定性，记录供电、时序、信息和器件门。模型被否定时发布新 E，不追改旧结果。物理结果与 H 方法比较分别报告。

下一步需要确认具体硬件和测量条件。当前未采购、未烧录、未连接未知目标。
''')
print(json.dumps({'readiness':str(root/'readiness.json'),'physical':'NOT_TESTED','serial_ports':v['serial_ports']}))
