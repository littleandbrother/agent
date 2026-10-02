"""Transparent first-order feasibility, with conservative storage and sensitivity.

This is a product engineering calculation, not a frozen BF scientific evaluator.
Only named catalogue operating points are accepted; no lux-to-sunlight conversion.
"""
import math


def timeline(e, *, light_scale=1, initial_v=None, burst=False, seconds=172800):
    """One-second reservoir simulation, conditional on stated charger assumptions.

    Below 1.8 V a separate assumed 20% cold-start conversion is used. This is
    sensitivity analysis, not a validated BQ25570 transient model.
    """
    c=e['capacitance_f']*e['capacitance_tolerance_low']
    ceiling=.5*c*e['v_high']**2
    stop=max(e['v_low'],e['supply_v']+.1)
    start=min(e['v_high'],e.get('restore_voltage_v',stop+.3))
    energy=.5*c*(initial_v if initial_v is not None else e['v_high'])**2
    on=energy>=.5*c*start**2
    event=(e['supply_v']*e['led_total_ma']*1e-3*e['pulse_ms']/1000+e['mcu_event_mj']/1000)/e['conversion_efficiency']
    accepted=denied=undervoltage=aborted=0;minimum=math.sqrt(2*energy/c);samples=[];first_ready=None
    rate=e['events_per_day']/86400
    for t in range(seconds):
        v=math.sqrt(max(0,2*energy/c))
        lit=(t%86400)<e['lit_hours']*3600
        eff=.2 if v<1.8 else e['conversion_efficiency']
        incoming=e['pv_power_mw']/1000*light_scale*eff if lit else 0
        draw=e['leakage_ua']*1e-6*v+(e['sleep_ua']*1e-6*e['supply_v']/e['conversion_efficiency'] if on else 0)
        energy=min(ceiling,max(0,energy+incoming-draw))
        v=math.sqrt(2*energy/c)
        if on and v<=stop:on=False;undervoltage+=1
        if not on and v>=start:on=True
        if on and first_ready is None:first_ready=t
        triggers=int((t+1)*rate)-int(t*rate)+(1 if burst and 36000<=t<36060 else 0)
        for _ in range(triggers):
            # 30 ohm is the catalogue maximum initial ESR at 1 kHz; use as a
            # sensitivity assumption for this pulse, not a measured DC ESR.
            peak=e['supply_v']*e['led_total_ma']*.001+.006
            sag=30*peak/max(.1,v)/e['conversion_efficiency']
            if not on:denied+=1
            elif energy-event>=.5*c*stop**2 and v-sag>=max(stop,e['supply_v']+.1):
                energy-=event;accepted+=1
            else:
                # There is no software energy oracle: an attempted pulse may
                # trip the hardware threshold. Count it as a failed response.
                energy=max(0,energy-event);on=False;aborted+=1
        minimum=min(minimum,math.sqrt(2*energy/c))
        if t%600==0:samples.append({'seconds':t,'voltage_v':round(math.sqrt(2*energy/c),5),'enabled':on})
    return {'light_power_scale':light_scale,'initial_v':initial_v,'duration_s':seconds,
            'accepted_events':accepted,'unavailable_events':denied,'aborted_pulses':aborted,'undervoltage_stops':undervoltage,
            'stop_voltage_v':stop,'restore_voltage_v':start,'minimum_v':minimum,'end_v':math.sqrt(2*energy/c),'first_ready_s':first_ready,
            'samples':samples,'hardware_verified':False,
            'assumptions':['600 mV cold-start input requirement must be separately checked; 20% cold-start efficiency is an assumption.',
                           'Power scale is a sensitivity factor, not a conversion from lux.',
                           'ESR=30 ohm and 6 mW MCU pulse power require waveform measurement.',
                           'Unavailable events mean no promised feedback; reservoir estimates are not circuit simulation.']}


def calculate(e):
    limits={'pv_power_mw':(0,100),'illuminance_lux':(0,100000),'lit_hours':(0,24),'conversion_efficiency':(.01,1),
            'capacitance_f':(.001,100),'capacitance_tolerance_low':(.01,1),'v_high':(.1,5.5),'v_low':(.1,5.4),
            'sleep_ua':(0,10000),'leakage_ua':(0,10000),'supply_v':(1.65,3.6),'led_total_ma':(0,100),
            'pulse_ms':(0,10000),'mcu_event_mj':(0,1000),'events_per_day':(0,100000)}
    for k,(lo,hi) in limits.items():
        if type(e.get(k)) not in (int,float) or not math.isfinite(e[k]) or not lo<=e[k]<=hi:raise ValueError('ENERGY_PARAMETER:'+k)
    if e['v_high']<=max(e['v_low'],e['supply_v']+.1):raise ValueError('ENERGY_VOLTAGE_ORDER_OR_BUCK_HEADROOM')
    if 'restore_voltage_v' in e and (type(e['restore_voltage_v']) not in (float,int) or not math.isfinite(e['restore_voltage_v']) or not max(e['v_low'],e['supply_v']+.1)<e['restore_voltage_v']<=e['v_high']):raise ValueError('ENERGY_RESTORE_VOLTAGE')
    c=e['capacitance_f']*e['capacitance_tolerance_low']
    available=.5*c*(e['v_high']**2-e['v_low']**2)
    harvest=e['pv_power_mw']/1000*e['conversion_efficiency']*e['lit_hours']*3600
    # Storage leakage conservatively charged at maximum storage voltage all day.
    sleep=e['sleep_ua']*1e-6*e['supply_v']/e['conversion_efficiency']*86400
    leakage=e['leakage_ua']*1e-6*e['v_high']*86400
    event=(e['supply_v']*e['led_total_ma']*1e-3*e['pulse_ms']/1000+e['mcu_event_mj']/1000)/e['conversion_efficiency']
    demand=sleep+leakage+event*e['events_per_day']
    dark=demand*(24-e['lit_hours'])/24
    checks={'daily_balance_positive':harvest>=demand,'dark_interval_storage_sufficient':available>=dark}
    # Cold start uses a different charger mode: this is an optimistic energy lower bound only.
    cold_lower=(.5*c*e['v_low']**2)/(e['pv_power_mw']/1000) /3600 if e['pv_power_mw'] else None
    points=[]
    for leak in (2,8,20,50):
        load=sleep+leak*1e-6*e['v_high']*86400+event*e['events_per_day']
        points.append({'leakage_ua':leak,'daily_margin_j':harvest-load,'dark_margin_j':available-load*(24-e['lit_hours'])/24})
    return {'model':'first-order-energy-v2','harvest_j_day':harvest,'demand_j_day':demand,'margin_j_day':harvest-demand,
            'effective_capacitance_f':c,'usable_storage_j':available,'dark_interval_demand_j':dark,'event_j':event,
            'cold_start_ideal_lower_bound_hours':cold_lower,'checks':checks,'calculation_passed':all(checks.values()),
            'leakage_sensitivity':points,'inputs':e,'hardware_verified':False,
            'scenarios':{name:timeline(e,**options) for name,options in [('normal',{}),('weak',{'light_scale':.25}),('dark',{'light_scale':0}),('cold',{'initial_v':0}),('burst',{'burst':True})]},
            'limitations':['效率、休眠电流、漏电、事件能量均须测量；没有将厂家光照点外推为任意光源。',
                           '每日回应均匀分布；集中连续触发需要固件限流与欠压保护。','冷启动下界忽略损耗且未建模冷启动电路，不能作为开机时间承诺。','电容 ESR、光照闪烁和元件容差需在电路与实物阶段另验。']}
