#!/usr/bin/env python3
"""One engineering phase derived from a frozen feedback experiment."""
import argparse
import datetime
import hashlib
import json
import re
from pathlib import Path
import urllib.request

from bf_v2_environment import environment
from v2_common import RUNTIME, action, create_pi, request, restart

ROOT = RUNTIME/'node-engineering'
SOURCE_PROJECT = 'PR-1cc2ff668e2184268a65f6fd0d4a43bd2804f62f99b3cda2263f92a1590f81b3'
SOURCE_SYSTEM = 'SC-449702b8940052cbc636b78f56d79f46b380d0e7a45e6363288c1f61e0bdf4c0'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2)+'\n'
    if path.exists() and path.read_text()!=text: raise ValueError('RECEIPT_EXISTS:'+str(path))
    path.write_text(text)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode', choices=['publish','create','start','finish','status'])
    args=parser.parse_args(); ROOT.mkdir(exist_ok=True)
    if args.mode=='publish': print(json.dumps(restart())); return
    if args.mode=='create':
        if (ROOT/'owner.json').exists(): print((ROOT/'owner.json').read_text()); return
        p,_=environment(RUNTIME)
        key=Path(p['paths']['PROVIDER_KEY_FILE']).read_text().strip()
        provider={}
        for label,url in [('balance','https://api.deepseek.com/user/balance'),('models','https://api.deepseek.com/models')]:
            req=urllib.request.Request(url,headers={'Authorization':'Bearer '+key})
            with urllib.request.urlopen(req,timeout=25) as response: provider[label]=json.load(response)
        preflight={'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),**provider}
        (ROOT/'provider-preflight.json').write_text(json.dumps(preflight,ensure_ascii=False,indent=2))
        if not provider['balance']['is_available'] or 'deepseek-flash' not in [m['id'] for m in provider['models']['data']]:
            raise ValueError('PROVIDER_NOT_READY')
        view=json.loads((ROOT/'source-view.json').read_text())
        allowed={'profile','intent','goal','scenario','parameters','acceptance','phase','report','functions','components','assignments','design_space','service'}
        definition={k:v for k,v in view['project']['requirements'].items() if k in allowed}
        definition['phase']='node-engineering-realization'
        definition['goal']='把已通过的压电节点参考候选落实为可理解、可接手的数字工程；保留原工况与参考程序。'
        sdk=Path.home()/'.local/share/bf-agent-runtime/reference-cases/literature-rsi-20261008/vendor/nordic-nrf5-sdk-17.1.0/source/nRF5_SDK_17.1.0_ddde560'
        config=(sdk/'examples/ble_peripheral/ble_app_uart/pca10040/s132/config/sdk_config.h').read_text()
        config='\n'.join(line for line in re.sub(r'/\*.*?\*/|//[^\n]*','',config,flags=re.S).splitlines() if line.strip())+'\n'
        reference=('本阶段沿用冻结参考执行，不修改 design.json 和 firmware/main.c，不运行 task_execute。\n'
            'Codex 已提供固定 nRF5 SDK 17.1.0/S132 7.2.0 构建器与原生 EDA 实现；本阶段的板级设计属于工程指导，不计入组织对照。\n'
            '目标：E73-2G4M04S1B (nRF52832-QFAA)，LTC3588-1 2.5 V，PGOOD → P0.11。模块有 32.768 kHz 晶体；本适配器先用 LFRC 并记录校准。\n'
            '参考时序：PGOOD+VDD>=2.3 V 后启动；首任务延后 1.5 s，周期 0.8 s，采样状态 11 ms，发送状态 4 ms。\n'
            '目标端请实现事件驱动 APP_TIMER/RTC、PGOOD 输入、SAADC 的 VDD 输入、内部 TEMP 采样、S132 非连接 BLE 广播。\n'
            '仅设 sd_ble_gap_adv_start 返回成功不能称接收成功。广播最小间隔、随机延迟及结束事件与主机 4 ms TX 的差异必须写明。\n'
            'TEMP 原始数值为 1/4 摄氏度；参考接收 fixture 恒值 2500，目标端以明确的编码与单位发真实温度，记录差异。\n'
            '程序断电丢 RAM，PGOOD 低时禁止服务并回到等待；电源 BOR/POR 与程序 IDLE 分开。不要启用模块 DCDC（本板 LDO）。\n'
            '广播 manufacturer data 用实验公司标识 0xFFFF，含 seq、温度和 (seq ^ value ^ 0xA5)&255；这是试验编码。\n'
            '源手册：https://www.analog.com/media/en/technical-documentation/data-sheets/35881fc.pdf；https://www.ebyte.com/product/239.html；https://docs-be.nordicsemi.com/bundle/nRF52832_PS_v1.9/raw/resource/enus/nRF52832_PS_v1.9.pdf。\n'
            'notes/target/sdk_config.h 已放入官方 UART 例程配置，裁去 UART/NUS、BSP、日志和 LED 等无用功能，保留你实际使用的外设。\n'
            '编译器是固定官方链；不支持自定义构建脚本，所有自有 C/H 放 notes/target/，至少 main.c、sdk_config.h、custom_board.h。\n'
            '机械：自由梁沿 x=0..90 mm、宽30 mm；PCB 位于 y>=35 mm 的侧区，四孔直径3.2 mm。选板尺寸50x32x1.6 mm便于容纳模块和电源。\n'
            '夹持新增结构按理想刚性边界处理，先复用名义波形；夹持柔度、模组状态电流、有效电容/ESR、实际射频接收是明确待验证项。\n')
        conversation=create_pi('压电节点 · 数字工程深化','node-engineering-owner-20261019')
        owner=conversation['id']
        created=action(owner,'repository_task_create',operation_id='node-engineering-create-v1',title='压电节点 · 可接手数字工程',
            definition=definition,source_project=SOURCE_PROJECT,source_system=SOURCE_SYSTEM,
            files={'notes/operator-reference.md':reference,'notes/target/sdk_config.h':config})
        auth=action(owner,'authorize',wall_authorization_text='持续运行 不设置时间限制',model_profile='engineering-reasoning-efficient-v5')
        auth.pop('participant_token',None);save(ROOT/'authority.json',auth)
        who={'owner':owner,'project_id':created['project_id'],'initial_system':created['id'],
             'source_project':SOURCE_PROJECT,'source_system':SOURCE_SYSTEM,'finite_scope':'one engineering phase; no new physics or organization trials'}
        save(ROOT/'owner.json',who);print(json.dumps(who));return
    who=json.loads((ROOT/'owner.json').read_text());owner=who['owner']
    if args.mode=='status':
        summary=action(owner,'repository_summary')
        print(json.dumps({'state':action(owner,'repository_state'),'summary':summary},ensure_ascii=False));return
    if args.mode=='start':
        goal=('完成本工程阶段第一步：读 notes/operator-reference.md 和任务工具合同，保留参考设计与程序不变。'
              '由你决定机械安装配置，提交 notes/engineering-realization.json，并编写 notes/target/main.c、sdk_config.h、custom_board.h。'
              '目标程序要落实 PGOOD、VDD 检测、RTC定时、真实温度和 BLE；说明与主机程序的实际差异。'
              'task_realize 会对完整源树执行固定目标构建、CAD与报告生成，复用已完成波形，最多修复三次编译错误。'
              '先完成可构建的目标和机械数据，记录未关闭工程问题；原生 EDA 正由开发者在独立工程完成。'
              '本步得到 BUILT 后停止操作，报告当前 SC 和待接入原生产物；不要运行仿真、不要 release/decide/close、不要建立其他 Agent。')
    else:
        goal=('继续当前工程候选。原生 EDA 回执已绑定，请读取最新状态，先执行独立验证，再调用 task_realize，检查 CAD、目标构建、原理图/PCB和运行图是否齐全。'
              '原生回执绑定当前SC，不再修改文件、manifest或新建提交；本轮只做检查与交付，不重新仿真。'
              'task_realize 应返回 native=true、target_status=BUILT、new_physics_solves=0；若出错，保存具体错误并停止，不改工程规避。'
              '调用 task_report，按实际资格选择审查保留或采用，生成本候选同版release并close。'
              '最终报告简洁列出目标实现差异与未关闭问题。只有记录了未通过项的审查交付也可结束，不扩大任务。')
    result=action(owner,'repository_start',goal=goal)
    save(ROOT/(args.mode+'-dispatch.json'),{'goal':goal,**result});print(json.dumps(result))


if __name__=='__main__': main()
