"""Prospective D4 operator screening, native calculation and immutable receipts."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from bfworld.agentlab.door_system import contracts, model, native, solver
from bfworld.agentlab.simulation_chain.contracts import write_json

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def screen(out, rom_path):
    out.mkdir(parents=True, exist_ok=True); started = time.time()
    rom = json.loads(rom_path.read_text()); records = []
    # Discrete bracket poses and polarity, not changes to damping/door speed/load.
    for gap in (28., 36., 48.):
        for dz in (0., -30.265):
            for polarity in (-1, 1):
                design = contracts.normalize({'mechanical': {'gap_mm': gap, 'closed_dz_mm': dz, 'polarity': polarity}})
                directory = out/(f'g{gap:g}-z{dz:g}-p{polarity}'); directory.mkdir(exist_ok=True)
                if (directory/'receipt.json').exists():
                    old = json.loads((directory/'receipt.json').read_text())
                    if old['source_rom_sha256'] != sha(rom_path) or old['template_sha256'] != contracts.template_hash():
                        raise ValueError('SCREEN_RECEIPT_IDENTITY_CHANGED; use new version directory')
                    records.append(old); continue
                write_json(directory/'design.json', design)
                begin = time.time()
                try: result = model.resistive_screen(directory, design, rom)
                except Exception as exc: result = {'status': getattr(exc, 'status', 'failed'), 'error': str(exc)}
                result.update(design_id=design['design_id'], candidate=design, source_rom_sha256=sha(rom_path),
                              template_sha256=contracts.template_hash(), operator_assisted=True, model_calls=0,
                              elapsed_s=time.time()-begin)
                write_json(directory/'receipt.json', result); records.append(result)
                print(json.dumps({k: result.get(k) for k in ('design_id', 'status', 'resistor_energy_J', 'peak_tip_mm', 'peak_piezo_V', 'elapsed_s')}), flush=True)
    receipt = {'schema_version': 'bf-door-space-screen-v1', 'count': len(records), 'records': records,
               'source_rom_sha256': sha(rom_path), 'source_rom': str(rom_path),
               'model_calls': 0, 'elapsed_s': time.time()-started,
               'frozen_protocol': contracts.FROZEN,
               'claim_boundary': 'Finite resistive screening; not PMIC self-power success or proof of global infeasibility.'}
    write_json(out/'screen-summary.json', receipt)
    return receipt

def native_run(out, design_path, rom_path, force_path):
    if out.exists(): raise ValueError('NATIVE_DIRECTORY_EXISTS; retained runs are immutable')
    out.mkdir(parents=True); started=time.time()
    design=json.loads(design_path.read_text()); contracts.verify_design(design)
    write_json(out/'design.json',design); rom=json.loads(rom_path.read_text())
    fw=out/'firmware';fw.mkdir(); native.firmware(fw,design)
    solution=out/'solution';solution.mkdir()
    try: metrics=solver.solve(solution,native.solver_spec(design),rom,force_path,fw); result={'status':'completed','metrics':metrics}
    except Exception as exc: result={'status':getattr(exc,'status','failed'),'error':str(exc)}
    result.update(design_id=design['design_id'],source_rom_sha256=sha(rom_path),source_force_sha256=sha(force_path),
                  template_sha256=contracts.template_hash(),operator_assisted=True,model_calls=0,elapsed_s=time.time()-started)
    write_json(out/'receipt.json',result);print(json.dumps(result,indent=2),flush=True);return result

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('action', choices=['screen','native']); p.add_argument('--out', type=Path, required=True); p.add_argument('--rom', type=Path, required=True);p.add_argument('--design',type=Path);p.add_argument('--force',type=Path)
    a = p.parse_args()
    if a.action=='screen':screen(a.out,a.rom)
    else:native_run(a.out,a.design,a.rom,a.force)
