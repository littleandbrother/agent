"""Public JSONL tools for the four calibrated tasks; no model client."""
import argparse
import copy
import json
import inspect
import math
import sys

from common import OUT, G, beam, full, compact, response
import feedback
import active
import structure

PUBLIC = {'E1':'e1_formal_public_tasks.json','E2':'e2_public_tasks.json',
          'E3':'e3_public_tasks.json','E4':'e4_public_tasks.json'}
CONDITIONS = {'E1':['F0','F1','F2','F3'],'E2':['Blind','Active','Oracle'],
              'E3':['baseline','diagnostic'],'E4':['L0','L1','L2']}
ALIASES = {'main_length_mm':'harvester.length_mm','aux_length_mm':'trigger_beam.length_mm',
           'storage_uF':'circuit.storage_uF','start_V':'circuit.start_V',
           'wake_high_V':'circuit.wake_high_V','tip_mass_g':'harvester.tip_mass_g'}


def load(name):
    return json.loads((OUT/name).read_text())


def jsonlines(name):
    return [json.loads(line) for line in (OUT/name).read_text().splitlines() if line]


def gateway(r):
    return dict(pass_=r['verdict']=='PASS',delivered_on_time=r['metrics']['delivered_on_time'],
        expected=r['metrics']['faults'],false_alarms=r['metrics']['false_reports'],
        safety=dict(stress=r['checks']['stress_within_limit'],travel=r['checks']['travel_within_limit']))


def observed(r, level):
    out=gateway(r)
    if level:
        m=r['measurements']
        out['stage_counts']={k:m['stages'][k] for k in ('WAKE','CONFIRM','REJECT','BROWNOUT')}
        if level>=2:
            out['node_measurements']=dict(storage_before_event_V=m['storage_before_first_event_V'],
                main_peak_V=m['main_peak_voltage_V'],aux_peak_V=m['aux_peak_voltage_V'],
                envelope_peak_V=m['envelope_peak_V'],t_ready_s=m['t_ready_s'])
        if level>=3:
            out.update(loaded_phase=dict(harvester=m['phase']['main'],trigger=m['phase']['aux']),event_windows=m['windows'])
    return out


def setfield(obj, path, value):
    keys=path.split('.')
    for key in keys[:-1]:obj=obj.setdefault(key,{})
    obj[keys[-1]]=value


def schema(name, description, properties=None, required=()):
    return dict(name=name,description=description,parameters=dict(type='object',properties=properties or {},required=list(required)))


class Episode:
    def __init__(self, task_id, condition, half=0, budget=6):
        self.family=task_id[:2];self.condition=condition;self.half=half;self.budget=budget
        if condition not in CONDITIONS[self.family]:raise ValueError('Condition not available for this experiment')
        self.public=copy.deepcopy(next(r for r in load(PUBLIC[self.family]) if r['id']==task_id))
        self.initial=self.public['initial'];self.env=self.public.get('environment',self.public.get('task'))
        self.allowed={ALIASES.get(k,k):v for k,v in self.public['domain'].items() if isinstance(v,list) and len(v)==2 and all(type(x) in (int,float) for x in v)}
        self.views=None;self.diagnostic=None;self.calls=0;self.diagnostic_calls=0;self.finished=False
        if self.family=='E1':
            self.private=next(r for r in load('e1_formal_tasks.json') if r['id']==task_id)
            rows=load('e1_impact_calibration.json') if self.public['case']=='impact' else jsonlines('e1_calibration.jsonl')
            a=next(r for r in rows if r['id']==task_id and r['which']=='initial')
            result=a['result'];initial_feedback=a['feedback'][int(condition[1])]
        elif self.family=='E2':
            self.private=next(r for r in load('e2_tasks.json') if r['id']==task_id)
            a=next(r for r in jsonlines('e2_calibration.jsonl') if r['id']==task_id and r['half']==half and r['which']=='initial')
            result=a['result'];initial_feedback=gateway(result)
            if condition=='Oracle':self.diagnostic=active.diagnose(self.private,half,result);self.diagnostic['cost']=0
        elif self.family=='E3':
            x=load('e3_summary.json');rows=x['proxy_tasks']+x['structure']['local_controls']['tasks']+x['structure']['architecture_required']['tasks']
            self.private=next(r for r in rows if r['id']==task_id)
            result=self.private['initial_result'];initial_feedback=self.visible(result,self.initial)
        else:
            self.private=next(r for r in load('e4_summary.json')['tasks'] if r['public_id']==task_id)
            self.views=load('e4_feedback_views.json')[task_id][condition]
            if self.private['state']=='S1':
                result=next(r['result'] for r in self.private['window']['samples'] if r['length_mm']==self.initial['harvester']['length_mm'])
            else:result=self.private['direct_result'] if self.private['state']=='S2' else self.private['witness_result']
            initial_feedback=copy.deepcopy(self.views)
            for point in initial_feedback['history']:
                safety=point['result']['safety']
                point['result']['safety']=dict(stress=safety['stress_within_limit'],travel=safety['travel_within_limit'])
        self.records=[dict(eval_id=0,design=copy.deepcopy(self.initial),result=result,feedback=initial_feedback)]
        self.public['editable_fields']=copy.deepcopy(self.allowed)
        if self.family in ('E3','E4'):
            self.public['module_defaults']=dict(boost_input_R_ohm=10000.,shunt_ohm=47000.,shunt_threshold_V=1.)
            choices={f'modules.{k}':[False,True] for k in self.public.get('branches',{}).get('modules',self.public['domain'].get('modules',{}))}
            if 'branches' in self.public:
                branches=self.public['branches']
                choices.update(supply=branches['supply'],mcu_gate=branches['mcu_gate'],
                    detector_source=['none','harvester','aux'],
                    **{'circuit.envelope_charge_ohm':branches['readout_charge_ohm']})
            if 'branch' in self.public['domain']:choices['branch']=self.public['domain']['branch']
            self.public['connection_rule']='Auxiliary detector_source requires module A; wake_low_V must be below wake_high_V.'
            self.public['editable_choices']=choices
        self.public['patch_semantics']='Each evaluate patch is applied to the original initial design, not to the previous candidate.'
        self.public['service']='Deliver all target events on time; zero false reports and brownouts; obey stated stress/travel and area limits.'
        if self.diagnostic is not None:self.public['diagnostic']=self.diagnostic
        self.tools=[schema('task','Read the public task and current evaluation budget.'),
            schema('evaluate','Evaluate a flat dot-path patch to the initial design in the declared legal domain.',{'patch':dict(type='object',additionalProperties=True)},['patch']),
            schema('finish','Submit a decision and an evaluated design ID; an infeasibility claim is recorded, not automatically accepted.',
                   {'label':dict(type='string',enum=['FEASIBLE','INFEASIBLE_CURRENT','INFEASIBLE_ALL','UNSURE']),
                    'eval_id':dict(type='integer',minimum=0),'confidence':dict(type='number',minimum=0,maximum=1)},['label','confidence'])]
        if self.family=='E2' and condition=='Active':self.tools.append(schema('diagnose','Measure the initial physical instance; cost 0.2 evaluation units, once.'))
        if self.family=='E4' and condition!='L0':self.tools.append(schema('bounds','Read the supplied bound over the current branch (L1) or all declared branches (L2).'))

    def status(self):
        return dict(evaluations_used=self.calls,evaluations_remaining=self.budget-self.calls,
                    diagnostic_calls=self.diagnostic_calls,cost_units=self.calls+.2*self.diagnostic_calls)

    def ready(self):
        return dict(kind='ready',public_task=self.public,initial=self.records[0]['feedback'],tools=self.tools,
                    budget=self.budget,nominal_source='import numpy as np\nG = '+repr(G)+'\n'+inspect.getsource(beam)+'\n'+inspect.getsource(response),**self.status())

    def visible(self, result, design):
        level=int(self.condition[1]) if self.family=='E1' else 3 if self.family=='E3' and self.condition=='diagnostic' else 0
        out=observed(result,level)
        if self.family=='E3':
            out['open_circuit_voltage_V']=float(abs(response(design['harvester'],self.env['background_Hz'],self.env['background_peak_g'])[1]))
            if 'mechanical_area_limit_mm2' in self.public:out['mechanical_area_mm2']=structure.area_mm2(design)
        return out

    def candidate(self, patch):
        d=copy.deepcopy(self.initial);branches=self.public.get('branches',{});domain=self.public['domain'];supply=None
        for key,value in patch.items():
            key=ALIASES.get(key,key)
            if key in self.allowed:
                lo,hi=self.allowed[key]
                if type(value) not in (float,int) or not math.isfinite(value) or not lo<=value<=hi:raise ValueError(f'Outside declared domain: {key}')
                setfield(d,key,value)
            elif key in [f'modules.{k}' for k in 'ABCD'] and type(value) is bool and ('modules' in domain or 'modules' in branches):
                d.setdefault('modules',dict(A=True,B=False,C=False,D=False))
                setfield(d,key,value)
                if key=='modules.A' and 'aux_resonator' in d.get('connections',{}):d['connections']['aux_resonator']=value
            elif key=='supply' and value in branches.get('supply',[]):
                supply=value
            elif key=='branch' and value in domain.get('branch',[]):
                supply=value
            elif key=='mcu_gate' and value in branches.get('mcu_gate',[]):setfield(d,'connections.mcu_gate',value)
            elif key=='detector_source' and branches and value in ['none','harvester','aux']:setfield(d,'connections.detector_source',value)
            elif key=='circuit.envelope_charge_ohm' and value in branches.get('readout_charge_ohm',[]):setfield(d,key,value)
            else:raise ValueError(f'Field is fixed or unavailable: {key}')
        c=d['circuit']
        if supply=='direct':c.pop('converter_input_R_ohm',None)
        elif supply is not None:c.setdefault('converter_input_R_ohm',self.public['module_defaults']['boost_input_R_ohm'])
        if self.family in ('E3','E4') and d.get('modules',{}).get('D',False):
            c.setdefault('shunt_ohm',self.public['module_defaults']['shunt_ohm'])
            c.setdefault('shunt_threshold_V',self.public['module_defaults']['shunt_threshold_V'])
        if c['wake_low_V']>=c['wake_high_V']:raise ValueError('wake_low_V must be less than wake_high_V')
        if d.get('connections',{}).get('detector_source')=='aux' and not d.get('modules',{}).get('A',True):raise ValueError('Auxiliary readout requires module A')
        return d

    def call(self, tool, args):
        if tool not in [t['name'] for t in self.tools]:raise ValueError('Tool unavailable in this condition')
        if self.finished:raise ValueError('Episode already finished')
        if tool=='task':return dict(public_task=self.public,initial_feedback=self.records[0]['feedback'],**self.status())
        if tool=='bounds':return dict(bounds=self.views['bounds'],**self.status())
        if tool=='diagnose':
            if self.diagnostic is None:
                self.diagnostic=active.diagnose(self.private,self.half,self.records[0]['result']);self.diagnostic_calls=1
            return dict(measurement=self.diagnostic,**self.status())
        if tool=='finish':
            label=args['label'];index=args.get('eval_id',0);confidence=args['confidence']
            if label not in ['FEASIBLE','INFEASIBLE_CURRENT','INFEASIBLE_ALL','UNSURE'] or not 0<=confidence<=1:raise ValueError('Invalid decision')
            if type(index) is not int or not 0<=index<len(self.records):raise ValueError('eval_id must reference this episode')
            record=self.records[index];self.finished=True
            return dict(label=label,confidence=confidence,eval_id=index,design=record['design'],
                verified_pass=record['result']['verdict']=='PASS',selected_feedback=record['feedback'],**self.status())
        if self.calls>=self.budget:raise ValueError('No evaluation budget remains; submit finish')
        design=self.candidate(args['patch']);self.calls+=1
        cached=next((r for r in self.records if r['design']==design),None)
        if cached:result=cached['result'];facts=cached['feedback']
        elif self.family=='E3' and structure.area_mm2(design)>self.public.get('mechanical_area_limit_mm2',float('inf')):
            result=dict(verdict='FAIL');facts=dict(pass_=False,failure='AREA_FAIL',mechanical_area_mm2=structure.area_mm2(design))
        else:
            actual=feedback.actual(self.private,design) if self.family=='E1' else active.realize(self.private,self.private['private']['halves'][self.half],design) if self.family=='E2' else design
            result=compact(full(actual,self.env));facts=self.visible(result,design)
        eval_id=len(self.records)
        self.records.append(dict(eval_id=eval_id,design=design,result=result,feedback=facts))
        return dict(eval_id=eval_id,feedback=facts,reused=cached is not None,**self.status())


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--task');p.add_argument('--condition');p.add_argument('--half',type=int,choices=[0,1],default=0);p.add_argument('--budget',type=int,default=6);p.add_argument('--list',action='store_true');a=p.parse_args()
    if a.list:
        print(json.dumps([dict(id=r['id'],half=h,experiment=e,conditions=CONDITIONS[e]) for e,n in PUBLIC.items() for r in load(n) for h in range(2 if e=='E2' else 1)]));return
    episode=Episode(a.task,a.condition,a.half,a.budget)
    print(json.dumps(episode.ready(),ensure_ascii=False),flush=True)
    for line in sys.stdin:
        request=json.loads(line)
        try:reply=dict(id=request['id'],result=episode.call(request['tool'],request.get('args',{})))
        except (ValueError,KeyError,IndexError,RuntimeError) as error:reply=dict(id=request['id'],error=str(error))
        print(json.dumps(reply,ensure_ascii=False),flush=True)
        if episode.finished:break


if __name__=='__main__':main()
