"""Closed power/program execution using the existing immutable task journal."""
import inspect
import json
from pathlib import Path
import shutil
import time

import numpy as np

from ..store import canonical
from .contracts import sealed
from .repository import file_hash
from . import feedback_native as physics, feedback_program as application
from .repository_feedback_contract import VERSION, ABI, NUMERICS
from .repository_reference_node import modal, sandbox_run


def environment():
    sources = [Path(__file__), Path(application.__file__), Path(physics.__file__),
               Path(__file__).with_name('repository_feedback_contract.py')]
    import hashlib
    return {'version':VERSION, 'abi':ABI, 'execution_sources':{p.name:file_hash(p) for p in sources},
        'shared_functions':{f.__name__:hashlib.sha256(inspect.getsource(f).encode()).hexdigest()
                            for f in (modal,sandbox_run,physics.read_raw,physics.conservative_sample)},
        'tools':physics.tools(), 'numerics':NUMERICS}


def couple(root, binary, design, scenario, tools, cache, step, budget):
    root.mkdir()
    count = int(np.ceil(scenario['duration_s']/step))
    grid = np.linspace(0,scenario['duration_s'],count+1)
    current = np.full(count,scenario['current_model']['values_a']['off'])
    previous = None; history = []
    for iteration in range(NUMERICS['max_iterations']):
        folder = root/f'iteration-{iteration:02}'
        pairs = physics.load_pairs(grid,current)
        deck = physics.deck(design,scenario,pairs,min(NUMERICS['native_max_step_s'],step/10))
        native = physics.native(folder,cache,deck,tools,budget,scenario['duration_s'])
        t, voltage = physics.waveform(folder,scenario['duration_s'])
        supply = physics.observe(t,voltage['v(out)'],grid)
        pgood = physics.observe(t,voltage['v(pgood)'],grid)
        trace, next_current, events = application.execute_program(folder/'application',binary,scenario,grid,supply,pgood)
        delta_i = float(np.max(abs(next_current-current)))
        delta_v = float(np.max(abs(supply-previous))) if previous is not None else None
        entry = {'iteration':iteration, 'native':native, 'max_current_difference_a':delta_i,
            'max_voltage_difference_v':delta_v, 'completed_tx':sum(e['state']=='tx' and e['completed'] for e in events),
            'program_sha256':file_hash(folder/'application/program.csv'),
            'load_sha256':__import__('hashlib').sha256(canonical(pairs).encode()).hexdigest()}
        history.append(entry)
        (root/'iterations.json').write_text(canonical(history))
        (folder/'provisional-events.json').write_text(canonical({'converged':False,'events':events}))
        if delta_i <= NUMERICS['current_tolerance_a'] and (delta_v is None or delta_v <= NUMERICS['voltage_tolerance_v']):
            for name in ('system.cir','system.log','system.raw.zlib'):
                shutil.copyfile(folder/name,root/name)
            shutil.copyfile(folder/'application/program.csv',root/'program.csv')
            (root/'load.json').write_text(canonical(pairs))
            (root/'events.json').write_text(canonical(events))
            sealed(root/'convergence.json', {'converged':True,'step_s':step,'iterations':history,
                'final_native':native['key'],'program_sha256':file_hash(root/'program.csv'),
                'load_sha256':file_hash(root/'load.json')})
            return {'converged':True,'iterations':history,'events':events,'step_s':step}
        previous, current = supply, next_current
    raise ValueError('FEEDBACK_FIXED_POINT_NOT_REACHED')


def run(root, system, inputs, cache):
    start = time.monotonic(); env = environment()
    scenario = system['task_definition']['scenario']; design = json.loads(inputs['design.json'])
    binary = application.compile_program(root,inputs['firmware/main.c'],env['tools'])
    native_calls = []
    def budget():
        if len(native_calls) >= 2*NUMERICS['max_iterations'] or time.monotonic()-start > 2400:
            raise ValueError('FEEDBACK_EXECUTION_BUDGET')
        native_calls.append(len(native_calls)+1)
    for phase, step in [('coarse',NUMERICS['program_step_s']),
                        ('fine',NUMERICS['program_step_s']/NUMERICS['refinement'])]:
        couple(root/phase,binary,design,scenario,env['tools'],cache,step,budget)
    (root/'design.json').write_text(inputs['design.json'])
    (root/'main.c').write_text(inputs['firmware/main.c'])
    (root/'execution-environment.json').write_text(canonical(env))
    (root/'source-model.json').write_text(canonical(physics.coefficients(design,scenario)))
    outputs = {name:(root/name).read_bytes() for name in ('design.json','main.c','execution-environment.json','source-model.json')}
    outputs.update({f'program/{name}':(root/'program-build'/name).read_bytes()
                    for name in ('firmware','build.log','feedback.h','runner.c')})
    for phase in ('coarse','fine'):
        for name in ('system.cir','system.log','system.raw.zlib','program.csv','load.json','events.json','convergence.json','iterations.json'):
            outputs[phase+'/'+name] = (root/phase/name).read_bytes()
    fine = json.loads(outputs['fine/convergence.json'])
    metrics = {'scope':'vendor-PMIC/program-feedback', 'abi':ABI,'converged':True,
        'firmware_sha256':file_hash(binary), 'native_dispatches':native_calls,
        'iterations':{p:len(json.loads(outputs[p+'/iterations.json'])) for p in ('coarse','fine')},
        'final_native':fine['final_native'], 'physical':'NOT_TESTED'}
    return metrics,outputs
