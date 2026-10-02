"""Detached reference capsule. Standard library only; no simulator/history import.

Predicts a precharged, no-harvest acquisition/inference/TX burst from empirical
action loads. The result concerns electrical completion, not diagnostic quality.
"""
import json
import math
import sys

def predict(parameters,design,condition):
    if condition.get('harvest_during_burst',True) or condition.get('signal_program')!='difference-feature-int8-v1':
        return {'in_scope':False,'reason':'unsupported energy condition or action program','energy_feasible':None}
    c=design['capacitance_f'];r=design['esr_ohm'];v=condition['initial_v'];release=design.get('release_s',.025)
    if not(.0003<=c<=.0047 and 0<=r<=18 and 2.6<=v<=3.1 and .02<=design['tx_power_w']<=.065 and .02<=release<=.1):
        return {'in_scope':False,'reason':'parameter domain not covered','energy_feasible':None}
    eta=parameters['efficiency'];dt=.0001;minimum=v;steps=0
    actions=[('cold-start',.004,0),('boot',parameters['boot_duration_s'],parameters['boot_power_w']),
             ('idle',max(0,release-.016),parameters['idle_power_w']),
             ('sense',parameters['sense_duration_s'],parameters['sense_power_w']),
             ('infer',parameters['infer_duration_s'],parameters['infer_power_w']),
             ('tx',parameters['tx_duration_s'],design['tx_power_w'])]
    for name,duration,power in actions:
        for _ in range(round(duration/dt)):
            pin=power/eta
            discriminant=v*v-4*r*pin
            if discriminant<0:return {'in_scope':True,'energy_feasible':False,'minimum_terminal_v':min(minimum,v/2),'failure_stage':name,'steps':steps}
            current=2*pin/(v+math.sqrt(discriminant)) if pin else 0
            v=max(.001,v-dt*(current+v/parameters['leakage_r_ohm'])/c)
            terminal=v-current*r;minimum=min(minimum,terminal);steps+=1
            if terminal<condition.get('off_v',1.8):
                return {'in_scope':True,'energy_feasible':False,'minimum_terminal_v':minimum,'failure_stage':name,'steps':steps}
    return {'in_scope':True,'energy_feasible':minimum>=condition.get('off_v',1.8)+.02,
            'minimum_terminal_v':minimum,'failure_stage':None,'steps':steps,
            'claim':'electrical burst only; 20 mV conservative admission margin'}

if __name__=='__main__':
    from pathlib import Path
    arguments=json.loads(sys.stdin.read())
    parameters=json.loads(Path(__file__).with_name('parameters.json').read_text())
    print(json.dumps(predict(parameters,arguments['design'],arguments['condition']),allow_nan=False))
