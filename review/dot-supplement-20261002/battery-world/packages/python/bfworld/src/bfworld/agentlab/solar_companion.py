"""Source-bound starter assembly; dimensions are mm, engineering assumptions explicit."""
import copy

PV = 'https://www.powerfilmsolar.com/products/electronic-component-solar-panels/indoor-light-series/ll200-24-75'
CAP = 'https://www.eaton.com/content/dam/eaton/products/electronic-components/resources/data-sheet/eaton-kr-supercapacitors-coin-cells-data-sheet.pdf'
MCU = 'https://www.st.com/resource/en/datasheet/stm32l031k6.pdf'
PMIC = 'https://www.ti.com/lit/ds/symlink/bq25570.pdf'
LED = 'https://www.kingbrightusa.com/images/catalog/spec/WP710A10ID.pdf'


def definition():
    parts = []
    def part(key, name, role, size, center, color, kind='rounded_box', radius=0, rotation=None, url=None, note='设计尺寸，需样件检验', **extra):
        g = {'kind': kind, 'size_mm': size, 'center_mm': center, **extra}
        if radius: g['fillet_mm'] = radius
        if rotation: g['rotation_deg'] = rotation
        parts.append({'id': key, 'name': name, 'role': role, 'geometry': g, 'color': color,
                      'source': {'basis': 'datasheet-envelope' if url else 'design-assumption', 'note': note, **({'url': url} if url else {})}})
    cream, green, dark, orange = [.82,.79,.66], [.11,.31,.28], [.035,.055,.05], [.94,.34,.12]
    part('base','桌面防倾底座','mount',[94,90,12],[0,0,6],green,radius=5)
    holes = [{'kind':'cylinder','size_mm':[6.4,6.4,12],'center_mm':[x,-17,13],'rotation_deg':[90,0,0]} for x in [-13,13]]
    holes.append({'kind':'cylinder','size_mm':[7.5,7.5,12],'center_mm':[0,-17,0],'rotation_deg':[90,0,0]})
    part('housing','圆角前壳，2 mm 壁','housing',[70,36,62],[0,0,43],cream,'shell',8,wall_mm=2,cutouts=holes)
    part('cover','可拆后盖','cover',[70,2,62],[0,19,43],green,radius=.8)
    boardholes=[{'kind':'cylinder','size_mm':[2.6,2.6,4],'center_mm':[x,y,0]} for x in [-21,21] for y in [-8,8]]
    part('main_pcb','主板 50 × 24 × 1.6','pcb',[50,24,1.6],[0,0,24],green,cutouts=boardholes)
    for i,(x,y) in enumerate([(x,y) for x in [-21,21] for y in [-8,8]]):
        part('boss'+str(i),'主板支撑柱','mount',[5,5,8.2],[x,y,18.1],cream,'cylinder',cutouts=[{'kind':'cylinder','size_mm':[2.3,2.3,10],'center_mm':[0,0,0]}])
        part('screw'+str(i),'M2 固定螺钉包络','mount',[2,2,8],[x,y,22.2],dark,'cylinder')
    part('supercap','Eaton KR-5R5H105-R · 1 F / 5.5 V','storage',[19.4,19.4,6.7],[10,1,28.55],[.55,.59,.6],'cylinder',url=CAP,note='名义直径 19±0.2 mm，包络取 19.4 mm；高度上限 6.7 mm，容差及引线另行校核')
    part('mcu','STM32L031K6 · LQFP32 本体','controller',[7,7,1.4],[-14,-3,26],dark,url=MCU,note='本体 7×7×1.4 mm；焊盘和引脚伸出由电路封装另行检验')
    part('pmic','BQ25570 · QFN20 本体','power',[3.5,3.5,1],[-16,8,25.8],dark,url=PMIC,note='3.5×3.5 mm 本体；高度取 1 mm 保守设计包络')
    part('face_pcb','前面板 LED/按键子板','pcb',[40,1.6,22],[0,-10,52],green)
    for i,x in enumerate([-13,13]):
        part('eye'+str(i),'透光眼罩','feedback',[6,6,3],[x,-18,56],orange,'cylinder',rotation=[90,0,0])
        part('led'+str(i),'WP710A10ID LED 包络','feedback',[3,3,5],[x,-14,56],orange,'cylinder',rotation=[90,0,0],url=LED,note='3 mm T-1 LED，5 mm 长度为预留包络，详细引线弯折未验证')
    part('button','可按压鼻子','input',[6,6,3],[0,-19,43],green,'cylinder',rotation=[90,0,0])
    part('switch','触发开关预留位','input',[6,6,4],[0,-14,43],dark,rotation=[90,0,0],note='6 mm 轻触开关安装预留，确切料号/焊脚待电路选型，不作为采购事实')
    # Solar sail sits above and behind the body; shared transform keeps carrier and panel aligned.
    import math
    rot=[35,0,0];center=[0,13,115]
    part('solar','PowerFilm LL200-2.4-75','solar',[94,.22,73],center,dark,rotation=rot,url=PV,note='厂家 94×73×0.22 mm；200 lux 0.289 mW，1000 lux 1.899 mW，照明类型需实测匹配')
    normal=[0,math.cos(math.radians(35)),math.sin(math.radians(35))]
    part('solar_back','光伏支撑背板','mount',[98,2,77],[center[i]+normal[i]*1.3 for i in range(3)],green,radius=.8,rotation=rot)
    for i,x in enumerate([-29,29]):
        part('sail_post'+str(i),'光伏支架','mount',[5,6,73],[x,38,48.5],green,radius=1)
    part('cable','光伏线束预留','connector',[2,2,71],[23,27,59.5],dark,'cylinder')
    return {'title':'向光 · 无电池桌面陪伴器','units':'mm','parts':parts,
            'required_roles':['housing','cover','solar','storage','pcb','controller','power','input','feedback','mount','connector'],
            'requirements':['桌面静置，通过一次按键触发短时灯光回应；不承诺语音或连续屏幕。','仅光伏供能与超级电容储能，不使用锂电池。','原生 CAD、Blender 和 STEP 统一尺寸与版本。'],
            'assumptions':['桌面每天 8 小时等效 200 lux，光源需实测匹配厂家条件。','60 次/天回应，每次两只 LED 合计 4 mA 持续 100 ms。','首版采用规则状态机，不需要训练数据或神经网络。','制造公差、连接线弯折、弹性卡扣及真实开关料号待样件与电路验证。'],
            'interfaces':['主板外形 50×24 mm；4 个 Ø2.6 孔，中心 x±21,y±8 mm。','太阳能片 94×73 mm，支撑面倾斜 35 度；峰值与暗场服务受实测光照约束。','电源域：PV → BQ25570 → 1 F 电容 → 3.0 V MCU/LED；低电压停止回应。'],
            'allowed_contacts':[['solar_back','sail_post0'],['solar_back','sail_post1'],['solar','cable'],['solar_back','cable']],
            'energy':{'pv_source':PV,'pv_power_mw':.289,'illuminance_lux':200,'lit_hours':8,'conversion_efficiency':.70,'capacitance_f':1,'capacitance_tolerance_low':.8,'v_high':4.2,'v_low':3.3,'sleep_ua':2,'leakage_ua':8,'supply_v':3,'led_total_ma':4,'pulse_ms':100,'mcu_event_mj':.6,'events_per_day':60,'assumption_fields':['conversion_efficiency','sleep_ua','leakage_ua','mcu_event_mj'],'cap_source':CAP},
            'presentation':{'camera_deg':35},'schema_version':'bf-product-assembly-v1'}


def changed(value, camera=None, width=None):
    p=copy.deepcopy(value)
    if camera is not None:p['presentation']['camera_deg']=camera
    if width is not None:
        next(x for x in p['parts'] if x['id']=='base')['geometry']['size_mm'][0]=width
    return p


def engineering_definition(positions, bom):
    """Reference revision tied to actual EDA placements, with conservative heights.

    This is operator-authored integration, never an independent Pi result.
    """
    p=definition();by={x['id']:x for x in p['parts']}
    p['parts']=[x for x in p['parts'] if x['id'] not in ('mcu','pmic')]
    def add(key,name,role,size,center,kind='box',rotation=None,cutouts=None,color=None,note='设计尺寸；装配公差尚待样件验证',source=None):
        g={'kind':kind,'size_mm':size,'center_mm':center}
        if rotation:g['rotation_deg']=rotation
        if cutouts:g['cutouts']=cutouts
        p['parts'].append({'id':key,'name':name,'role':role,'geometry':g,'color':color or [.17,.20,.18],
                         'source':source or {'basis':'design-assumption','note':note}})
    by['supercap']['geometry']['center_mm']=[8,2,43.85]
    by['face_pcb']['role']='mount';by['face_pcb']['name']='前面板绝缘载板（手工线束，不是已布线 PCB）'
    by['face_pcb']['source']['note']='40×22×1.6mm 绝缘载板，固定 LED 与开关；采用独立导线接主板J3/J4'
    by['switch']['name']='TS-1088-AR02016 轻触开关'
    by['switch']['geometry']['size_mm']=[3.9,3,2]
    by['switch']['source']={'basis':'native-component','note':'立创 C720477，TS-1088-AR02016，3.9×3×2mm 包络；焊脚与致动行程需样件核对','url':'https://item.szlcsc.com/'}
    add('pushrod','按键推杆','input',[2,2,2.55],[0,-16.475,43],'cylinder',[90,0,0],note='与鼻子固定；距开关0.2mm，0.5mm工作行程为假设')
    p['allowed_contacts'].append(['button','pushrod'])
    add('cap_shelf','电容承托平台','mount',[25,29.5,1],[8,1,40],color=[.48,.59,.45])
    for i,x in enumerate([-3.5,19.5]):add('cap_post'+str(i),'电容承托后支柱','mount',[2,2,25.5],[x,14.5,26.75],color=[.48,.59,.45])
    add('cap_ring','电容定位圈','mount',[21.4,21.4,4],[8,2,42.5],'cylinder',cutouts=[{'kind':'cylinder','size_mm':[19.8,19.8,6],'center_mm':[0,0,0]}],color=[.48,.59,.45])
    refs={x['ref']:x['lcsc'] for x in bom}
    footprints={}
    for x in positions:
        ref=x['ref'];xx=x['x_mm']-25;yy=x['y_mm']-12
        if ref=='U1':size=[3.5,3.5,1];role='power';label='BQ25570'
        elif ref=='U2':size=[9,9,1.6];role='controller';label='STM32L031K6T6（含引脚包络）'
        elif ref=='L1':size=[6,6,4.5];role='power';label='SLF6045T-220M1R1-3PF 22uH'
        elif ref=='L2':size=[4,4,1.8];role='power';label='SRN4018-100M 10uH'
        elif ref in ('J1','J2','J4'):size=[5.1,2.54,8.5];role='connector';label='2.54mm 两针接口'
        elif ref=='J3':size=[8,5,6];role='connector';label='PH-3A 灯光线束接口'
        elif ref=='J5':size=[12,5,6];role='connector';label='PH-5A 调试接口'
        elif ref.startswith('R'):size=[1.6,.8,.6];role='power';label='0603 电阻'
        elif ref in ('C1','C2','C5'):size=[2,1.25,1.5];role='power';label='0805 电容'
        else:size=[1.6,.8,1];role='power';label='0603 电容'
        z=24.8+size[2]/2
        add('pcb_'+ref,ref+' · '+label,role,size,[xx,yy,z],rotation=[0,0,x.get('rotation',0)],
            source={'basis':'native-component','note':refs[ref]+'；XY来自立创原生布局；封装外形与高度为保守装配包络，非原厂精细3D模型'})
        footprints[ref]={'lcsc':refs[ref],'board_center_mm':[x['x_mm'],x['y_mm']],'body_envelope_mm':size}
    p['interfaces']+=['PCB 33个元件与原生立创布局同一XY坐标；电容移到40mm高的独立承托台。','J1=PV/GND，J2=VCAP/GND，J3=LED_L/LED_R/GND，J4=BUTTON/GND，J5=V3/GND/SWDIO/SWCLK/NRST。','前面板采用绝缘载板和手工线束；未把子板显示包络称为已完成的电路板。']
    p['assumptions']=[x for x in p['assumptions'] if '确切料号' not in x]
    p['assumptions']+=['后盖紧固和前面板载板安装仍需公差/样件审查；不承诺直接制造。','元件包络高度保守假设；原生电气检查不替代实体装配。']
    p['energy']['v_low']=3.3107;p['energy']['restore_voltage_v']=3.6104
    p['pcb_placement']=footprints
    return p
