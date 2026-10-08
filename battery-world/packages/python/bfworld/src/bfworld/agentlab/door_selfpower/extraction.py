"""Prospective D5 extraction circuits; never alters the sealed D4 deck.

Switching is powered by the piezo/envelope itself. No independent clock or
control supply is used. Device models are local, hash-bound inputs, not ideal
switches. The SECE circuit is a positive-output adaptation of the published
envelope detector, not a claim of byte-identical reproduction of its schematic.
"""
import re
import hashlib
from pathlib import Path
from ..simulation_chain.native import PMIC
from ..runtime_config import HOME_ROOT as WORK, configured
from .contracts import SI2333_MODEL_HASH

SWITCH_SOURCE_ROOT=configured('DOOR_SELFPOWER_ROOT',WORK/'reference-cases/door-selfpower-v1')/'sources'


def load_switch_model(name):
    if name=='BSS84':return local_model(name,'standard.mos')
    if name!='Si2333CDS':raise ValueError('SELFPOWER_LOAD_SWITCH_INVALID')
    path=SWITCH_SOURCE_ROOT/'Si2333CDS.spice.txt'
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SI2333_MODEL_HASH:
        raise ValueError('SELFPOWER_LOAD_SWITCH_VENDOR_MODEL_CHANGED')
    # Original manufacturer text, including its three-pin subcircuit and
    # nonlinear/capacitive devices. No ideal-switch replacement or parameter fit.
    return raw.decode('utf-8')


def local_model(name, filename):
    path = Path(PMIC).parent.parent / 'cmp' / filename
    raw = path.read_bytes()
    text = raw.decode('utf-16-le') if b'\0' in raw[:40] else raw.decode('cp1252')
    match = re.search(r'^\.model\s+' + re.escape(name) + r'\s+.*(?:\n\+.*)*', text, re.M | re.I)
    if not match:
        raise ValueError('LOCAL_DEVICE_MODEL_MISSING:' + name)
    return match.group(0)


def device_models(profile='prototype'):
    if profile=='schottky-parallel':return device_models('schottky')
    # BC546B/2N5401 are actual, declared prototype substitutions. They are NOT
    # relabeled as the MMBT devices from Tang et al. or the XN4601 from ViPSN.
    if profile in ('rated-sece','schottky'):
        p=WORK/'reference-cases/door-selfpower-v1/sources/MMBT5551.spice.txt'
        if hashlib.sha256(p.read_bytes()).hexdigest() != '38624454abd3eecad3761af8449495b20d6409aa25c5acef960f60b44549e492':
            raise ValueError('SELFPOWER_VENDOR_MODEL_CHANGED')
        return p.read_text()+'\n'+local_model('2N5401', 'standard.bjt')+'\n'+local_model('BAT46WJ' if profile=='schottky' else 'BAS21HY', 'standard.dio')+'\n'
    if profile != 'prototype':raise ValueError('EXTRACTION_DEVICE_PROFILE_UNKNOWN')
    return '\n'.join([local_model('BC546B', 'standard.bjt'),
                      local_model('2N5401', 'standard.bjt'),
                      local_model('1N4148', 'standard.dio')]) + '\n'


def bridge():
    return '''Dbr1 port rect 1N4148
Dbr2 pz2 rect 1N4148
Dbr3 0 port 1N4148
Dbr4 0 pz2 1N4148
'''


def interface(topology, ce=680e-12, inductance=1e-3, dcr=15., profile='prototype'):
    if profile=='schottky-parallel':
        if topology!='sece':raise ValueError('PARALLEL_BANK_REQUIRES_SECE')
        source=interface(topology,ce,inductance,dcr,'schottky');rows=[]
        for line in source.splitlines():
            words=line.split()
            if words and words[0] in ('Dbr1','Dbr2','Dbr3','Dbr4','Dblock','Dtransfer'):
                name,anode,cathode,part=words
                for index in range(1,4):
                    node=name.lower()+'_a'+str(index)
                    rows.extend([f'Rbal_{name}_{index} {anode} {node} 0.22',
                                 f'{name}_{index} {node} {cathode} {part}'])
            else:rows.append(line)
        return '\n'.join(rows)+'\n'

    if profile in ('rated-sece','schottky'):
        return interface(topology, ce, inductance, dcr).replace('BC546B','MMBT5551').replace('1N4148','BAT46WJ' if profile=='schottky' else 'BAS21HY')
    if topology == 'seh':
        return bridge() + 'Dstore rect vin 1N4148\n'
    if topology == 'sece':
        # Polarity reflection of the published peak-detector/series switch.
        # Rectification is negative: the high-side switch isolates Cp until a
        # peak, then L charges; on opening, L's positive flyback feeds VIN.
        # The prior low-side prototype had a continuous path to VIN and was
        # rejected. This is a declared positive-storage adaptation, not the
        # original part-for-part paper implementation.
        return f'''* Isolated self-powered SECE, negative rectifier / positive flyback.
Dbr1 rect port 1N4148
Dbr2 rect pz2 1N4148
Dbr3 port 0 1N4148
Dbr4 pz2 0 1N4148
Denv env rect 1N4148
Cenv env 0 {ce} IC=0
QN base rect env BC546B
Dbase nb base 1N4148
Rbase nb 0 100Meg
Dblock collector rect 1N4148
QP collector nb lx 2N5401
Lextract lx 0 {inductance} Rser={dcr}
Dtransfer lx vin 1N4148
'''
    if topology == 'sece-floating':
        # Preserve the original PNP detector + NPN series switch. Its inductor
        # flyback charges a negative storage terminal. The PMIC/MCU ground is
        # that terminal, so their local VIN is positive without an inverter or
        # an external source. Observation-only B nodes are not power nodes.
        return bridge()+f'''Denv rect env 1N4148
Cenv env 0 {ce} IC=0
QP base rect env 2N5401
Dbase base nb 1N4148
Rbase nb 0 100Meg
Dblock rect collector 1N4148
QN collector nb lx BC546B
Lextract lx 0 {inductance} Rser={dcr}
Dtransfer return lx 1N4148
'''
    if topology == 'psshi':
        # Transcribed pin/wire graph from ViPSN EEU_PSSHI.SchDoc, commit
        # 5a6b13f..., sha256 74b91058... . Original XN4601/NSR0240
        # devices are explicitly substituted; the topology and 510k/680p/1mH
        # peak detector are retained. PZ2 from the sheet is `port` here.
        return f'''* Reference-derived self-powered single-inductor P-SSHI.
Rpeakp port dp 510k
Denvp dp envp 1N4148
Cenvp envp pz2 {ce} IC=0
QPp ctrlp port envp 2N5401
Dbasep ctrlp nbp 1N4148
Dblockp port cnp 1N4148
QNp cnp nbp lc BC546B
Rpeakn port dn 510k
Denvn envn dn 1N4148
Cenvn envn pz2 {ce} IC=0
QNn ctrln port envn BC546B
Dbasen bpn ctrln 1N4148
QPn cpn bpn lc 2N5401
Dblockn cpn port 1N4148
Lp lc pz2 {inductance} Rser={dcr}
XU1 port pz2 cap vin sw out vin2 vin2 0 pgood 0 LTC3588-1
'''
    raise ValueError('EXTRACTION_TOPOLOGY_UNKNOWN')


def reserve_divider(high_V, low_V, total_ohm=3e6):
    """MIC841 three-resistor divider, datasheet equations 4-1/4-2.

    Exact design values are reported; physical E96 selection/tolerance remains
    an independent sensitivity check, never a silently ideal hardware claim.
    """
    if not 1.5 <= low_V < high_V <= 12. or not 0 < total_ohm <= 3e6:
        raise ValueError('ENERGY_GATE_THRESHOLD_INVALID')
    r3=1.24*total_ohm/high_V
    r2=1.24*total_ohm/low_V-r3
    return total_ohm-r2-r3,r2,r3


def energy_gate(high_V=8., low_V=4.3, iq_A=1.5e-6, divider_ohm=None, load_switch='BSS84'):
    r1,r2,r3=reserve_divider(high_V,low_V) if divider_ohm is None else divider_ohm
    total=r1+r2+r3
    if not all(x>0 for x in (r1,r2,r3)) or total>3e6:
        raise ValueError('ENERGY_GATE_DIVIDER_INVALID')
    if abs(1.24*total/r3-high_V)>1e-6 or abs(1.24*total/(r2+r3)-low_V)>1e-6:
        raise ValueError('ENERGY_GATE_DIVIDER_THRESHOLD_MISMATCH')
    # MIC841L asserts HIGH at LOW VIN, releases LOW at HIGH VIN (Table3-1).
    # Its two powered output paths drive the high-side PMOS with that polarity.
    # MIC841N's low-at-low-VIN open drain would require a physical inverter;
    # the former N label without that inverter was an invalid part claim.
    # The latch is a declared supply-qualified MIC841L behavioral approximation,
    # not a vendor SPICE macro-model. Control nodes have no power connection to
    # VIN/MCU; real divider, IQ, output paths, PMOS capacitance/Ron and MCU bypass are
    # in the native power network. Output RC approximates propagation, not a
    # calibration to an unavailable physical device. Below VDD=1.5V stays off.
    switch_model=load_switch_model(load_switch)
    switch_line='Mpass mcu gate out out BSS84' if load_switch=='BSS84' else 'Xpass mcu gate out Si2333CDS'
    return f'''* MIC841L reserve gate: high at LOW VIN, low at HIGH VIN; powered behavioral output.
Rmon1 vin lth {r1}
Rmon2 lth hth {r2}
Rmon3 hth 0 {r3}
Bmonitor out 0 I={iq_A}*limit(V(out)/1.5,0,1)
Bctl ctl 0 V=if(V(out)>1.5,V(hth)*{total/r3},0)
Rctl ctl ctl_delay 1k
Cctl ctl_delay 0 10n IC=0
Smonitor gate 0 ctl_delay 0 MONITOR
.model MONITOR SW(Ron=200 Roff=1T Vt={(high_V+low_V)/2} Vh={(high_V-low_V)/2})
* Complementary push-pull path supplied by VOUT; no independent gate power.
Bctl_high ctl_high 0 V=-V(ctl_delay)
Smonitor_high gate out ctl_high 0 MONITOR_HIGH
.model MONITOR_HIGH SW(Ron=200 Roff=1T Vt={-(high_V+low_V)/2} Vh={(high_V-low_V)/2})
* Push-pull L output: the N-version 470k pull-up is physically absent.
{switch_line}
Cmcu mcu 0 100n IC=0
Rdischarge mcu 0 10Meg
{switch_model}
'''


def replace_power(text, spec, topology, *, ce=680e-12, inductance=1e-3, dcr=15., charging_only=False, profile='prototype', gate=None):
    start = text.index('XU1 port pz2')
    end = text.index('.tran ', start)
    circuit = spec['circuit']
    if topology == 'd4':
        if gate is None:return text
        # Direct interface negative control with the same gate and losses.
        topology='direct'
    extraction = ('XU1 port pz2 cap vin sw out vin2 vin2 0 pgood 0 LTC3588-1\n'
                  if topology=='direct' else interface(topology, ce, inductance, dcr, profile))
    if topology not in ('psshi','direct'):
        extraction += 'XU1 0 0 cap vin sw out vin2 vin2 0 pgood 0 LTC3588-1\n'
    power = extraction + f'''Cstorage vin 0 {circuit['cin_uF']*1e-6} IC=0
Ccap vin cap 1u
Cvin2 vin2 0 4.7u
L1 sw out 10u Rser=0.4
Cout out 0 {circuit['cout_uF']*1e-6} Rser=0.02 IC=0
Vload schedule 0 PWL FILE="load.pwl"
Bload {'mcu' if gate else 'out'} 0 I={'0' if charging_only else 'V(schedule)*limit(V('+('mcu' if gate else 'out')+')/1.8,0,1)'}
.lib LTC3588-1.sub
{device_models(profile)}
{energy_gate(**gate) if gate else ''}
'''
    if topology=='sece-floating':
        if gate is not None:raise ValueError('FLOATING_GATE_REQUIRES_NATIVE_MAPPING')
        # Translate the supply network, leaving the piezo/peak detector fixed.
        power=power.replace('XU1 0 0 cap vin sw out vin2 vin2 0 pgood 0',
                            'XU1 return return cap 0 sw reg_raw vin2 vin2 return good_raw return')
        power=power.replace('Cstorage vin 0','Cstorage 0 return').replace('Ccap vin cap','Ccap 0 cap')
        power=power.replace('Cvin2 vin2 0','Cvin2 vin2 return').replace('L1 sw out','L1 sw reg_raw')
        power=power.replace('Cout out 0','Cout reg_raw return').replace('Bload out 0','Bload reg_raw return')
        power+='Bvin_observe vin 0 V=-V(return)\nBout_observe out 0 V=V(reg_raw,return)\nBgood_observe pgood 0 V=V(good_raw,return)\n'
    return text[:start] + power + text[end:]
