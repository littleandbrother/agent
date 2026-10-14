"""Small, versioned method resources; wrong IDs never fall back silently."""
from ..store import identity
import hashlib

SKILLS = {
 'bf-design-task-control-v1': '''# Design-task control
Read the authoritative task and adopted snapshot on start/recovery. Keep a revisable plan and explicit CONTINUE/WAIT/BLOCKED intent. WAIT refers to a real pending operation. Reuse the same operation ID and exact frozen input on recovery; an UNKNOWN result requires factual reconciliation. A completed process is not acceptance. Compare actual check scope/binding with the selected D/E/V. Adopt a design with a CAS revision and reason; submit the selected executed revision and retain limits. Do not edit the evaluator or infer physical success from a source/package pass.''',
 'bf-compiled-event-port-v1': '''# Compiled event-port application
The finite C ABI is bf_reset(void), bf_state(void), bf_current_mA(void), bf_step(double dt_ms,double supply_V,double pgood_V), bf_event(uint32_t event_id,uint8_t kind), bf_payload(uint8_t out[12]). The trusted runner feeds time/supply/PGOOD and a virtual event from the actuator's opening onset. bf_step returns nonzero on completed transmission; the runner reads the actual payload then. Inspect the task for the wire layout and deadlines, and preserve the source's physical assumptions. Check state/data lifetime across supply resets, peripheral identity and stale events, serialized width/endian/checksum, complete TX timing, receiver identity/dedup and deadline. Current/timing envelopes are assumptions. The F0 core and Cortex-M4 object share participant sources, but object generation does not execute a SoC or prove target power/RF. If a change alters any load/state sample, the old native waveform loses its reuse witness and acceptance remains UNEVALUABLE until a qualified joint solve is run.'''
}
SKILLS['bf-native-coupling-v2'] = '''# Native coupled candidate execution
Use the task environment and supported_actions to identify the supported physical model, initialization, units, inputs and calibration limits. Candidate program C/H and explicitly allowed device.json circuit/extraction/gate fields are distinct dependencies. Changed program behavior must come from the actual compiled program; energy/current claims require the declared state-current model or independent calibration. An identical source/load may reuse its exact native witness. A changed load or allowed circuit choice needs a new converged native supply/program calculation and finer-step confirmation. Trial events are provisional and never received as committed mission outcomes. Check the returned numerical, rating, model-domain, event/receiver and version bindings separately. Source/geometry outside the supported ROM needs another qualified model, not a silent extrapolation. A compiled ARM object is not target peripheral execution; a virtual receiver is not physical BLE. The candidate builder graph marks affected downstream checks; old phase deliverables remain historical evidence. Adopt only the actual design you decide to retain and submit its exact execution/check version. This public resource is apparatus-maintainer guidance, not a Pi-generated method improvement.'''


def load(skill_id):
    if skill_id not in SKILLS:
        raise ValueError('SKILL_NOT_FOUND; available='+','.join(SKILLS))
    text=SKILLS[skill_id]
    return {'skill_id':skill_id,'version':'2.0.0' if skill_id=='bf-native-coupling-v2' else '1.0.0','text':text,'sha256':identity(text),
            'provenance':'Codex public environment/method resource; not Pi self-improvement',
            'compatible_task':'C-F1-native-D5-candidate-program-circuit-v2' if skill_id=='bf-native-coupling-v2' else 'magnetic-switch-v1/F0'}


def bundle(native=False):
    """Use the same immutable resource/activation contract as other BF skills."""
    selected={key:text for key,text in SKILLS.items() if native or key!='bf-native-coupling-v2'}
    files={key+'/SKILL.md':text.encode() for key,text in selected.items()}
    entries=[{'id':key,'description':text.splitlines()[0].lstrip('# '),
              'path':key+'/SKILL.md','plugin_id':'bf-design-lab','version':'2.0.0' if key=='bf-native-coupling-v2' else '1.0.0',
              'sha256':hashlib.sha256(files[key+'/SKILL.md']).hexdigest(),'adapter':'bf-design-task-v1'}
             for key,text in selected.items()]
    manifest={'schema_version':'bf-resource-manifest-v1','skills':entries,
        'plugins':[{'id':'bf-design-lab','version':'1.1.0' if native else '1.0.0','adapter':'bf-design-task-v1',
                    'tools':['bf_design'],'permissions':'existing owner-bound C authority; no new grants',
                    'skills':[{k:x[k] for k in ('id','description','path')} for x in entries]}],
        'files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()},
        'policy':'frozen project resources; Codex environment methods, not Pi self-improvement'}
    manifest['sha256']=identity(manifest)
    return manifest,files

