"""Versioned terminal screening; no repetitive-pulse use of single-surge ratings.

BAT46WJ's 250mA forward-current limit is used as a conservative sufficient
peak screen. Exceeding it is *unqualified*, not proof of damage: a separate
pulse/thermal qualification would be required. 2.5A IFSM is never substituted.
"""
import numpy as np

VERSION = 'bf-component-rating-v2'
POWER_DIODES = ('dbr1', 'dbr2', 'dbr3', 'dbr4', 'dblock', 'dtransfer')
NODES = {'dbr1': ('rect', 'port'), 'dbr2': ('rect', 'pz2'),
         'dbr3': ('port', '0'), 'dbr4': ('pz2', '0'),
         'denv': ('env', 'rect'), 'dbase': ('nb', 'base'),
         'dblock': ('collector', 'rect'), 'dtransfer': ('lx', 'vin')}
SOURCES = {'2N5401': 'https://www.onsemi.com/download/data-sheet/pdf/2n5401-d.pdf',
           'BAT46WJ': 'https://assets.nexperia.com/documents/data-sheet/BAT46WJ.pdf',
           'BAS21HY': 'https://fscdn.rohm.com/en/products/databook/datasheet/discrete/diode/switching/bas21hy-e.pdf'}


def diode_nodes(design):
    bank = design['parts'].get('diode_bank')
    for name, (anode, cathode) in NODES.items():
        if bank and name in POWER_DIODES:
            for i in range(1, 4):
                yield name+'_'+str(i), name+'_a'+str(i), cathode
        else:
            yield name, anode, cathode


def saved_channels(design):
    if design['extraction']['topology'] != 'sece': return ''
    channels = ['Ic(QP)', 'Ib(QP)', 'Ie(QP)', 'Ic(QN)']
    for name, anode, _ in diode_nodes(design):
        channels.append('I('+name+')')
        if '_a' in anode: channels.append('V('+anode+')')
    return ' '.join(channels)


def diode_facts(t, current, voltage, limit):
    positive = np.maximum(current, 0)
    mask = positive > limit
    edges = np.flatnonzero(np.diff(np.r_[False, mask, False]))
    # Bracket complete sampled crossings conservatively; do not downsample
    # microsecond peaks into the 0.5ms display CSV before checking them.
    widths = [t[min(e, len(t)-1)]-t[max(s-1, 0)]
              for s, e in zip(edges[::2], edges[1::2])]
    duration = t[-1]-t[0]
    return {'forward_peak_A': float(max(positive)),
            'reverse_peak_V': float(max(np.maximum(-voltage, 0))),
            'forward_average_A': float(np.trapezoid(positive, t)/duration),
            'rms_A': float(np.sqrt(np.trapezoid(current**2, t)/duration)),
            'positive_terminal_power_average_W': float(np.trapezoid(np.maximum(current*voltage, 0), t)/duration),
            'peak_screen_A': limit, 'pulse_count_over_screen': len(widths),
            'max_pulse_width_over_screen_s': float(max(widths, default=0)),
            'repetitive_peak_covered': bool(not np.any(mask))}


def check(t, v, design):
    actual = t > 1e-7
    time = t[actual]
    def node(name):
        return np.zeros(len(time)) if name == '0' else v['v('+name+')'][actual]
    def peak(a): return float(np.max(np.abs(a)))
    top = design['extraction']['topology']
    pz = peak(v['v(pz1,pz2)'][actual])
    out = {'schema_version': VERSION, 'piezo_peak_V': pz, 'sources': SOURCES,
           'pmic_input_peak_V': float(max(node('vin'))),
           'coverage_complete': top == 'sece', 'unqualified_limits': []}
    if top != 'sece':
        out.update(passed=False, reason='Terminal screening for this topology is not yet implemented.')
        return out
    coil = v['i(lextract)'][actual]
    collector = v['ic(qp)'][actual]
    detector = v['ic(qn)'][actual]
    out.update(detector_Vce_V=peak(node('base')-node('env')),
               switch_Vce_V=peak(node('collector')-node('lx')),
               detector_reverse_Vbe_V=float(max(node('env')-node('rect'))),
               switch_reverse_Vbe_V=float(max(node('nb')-node('lx'))),
               collector_peak_A=peak(collector), collector_limit_A=.6,
               detector_collector_peak_A=peak(detector), detector_collector_limit_A=.6,
               coil_peak_A=peak(coil), coil_peak_limit_A_typ=design['parts']['coil']['Isat10_A_typ'],
               coil_rms_A=float(np.sqrt(np.trapezoid(coil**2, time)/(time[-1]-time[0]))),
               coil_voltage_peak_V=peak(node('lx')))
    # Installed BAS21HY is a200mA part. Its pulse qualification is also not
    # inferred from a surge specification. Keep the screen explicit per die.
    limit = .25 if design['parts']['diodes'].startswith('BAT46WJ') else .2
    reverse_limit = 100. if design['parts']['diodes'].startswith('BAT46WJ') else 200.
    diodes = {name: diode_facts(time, v['i('+name+')'][actual], node(anode)-node(cathode), limit)
              for name, anode, cathode in diode_nodes(design)}
    out['diodes'] = diodes
    out['diode_reverse_limit_V'] = reverse_limit
    out['diode_reverse_peak_V'] = max(x['reverse_peak_V'] for x in diodes.values())
    out['diode_forward_peak_A'] = max(x['forward_peak_A'] for x in diodes.values())
    out['diode_repetitive_current_covered'] = all(x['repetitive_peak_covered'] for x in diodes.values())
    out['unqualified_limits'] = [name+': repetitive pulse exceeds conservative forward-current screen; IFSM does not qualify it'
                                for name, x in diodes.items() if not x['repetitive_peak_covered']]
    branch = sum((v['i('+name+')'][actual] for name in diodes if name.startswith('dblock')), start=np.zeros(len(time)))
    out['collector_KCL_max_A'] = peak(collector+branch)
    out['collector_KCL_passed'] = out['collector_KCL_max_A'] < 1e-4
    out['collector_current_passed'] = out['collector_peak_A'] < .6
    out['coil_current_passed'] = (out['coil_peak_A'] < out['coil_peak_limit_A_typ']
                                  and out['coil_rms_A'] < design['parts']['coil']['rated_rms_A'])
    out['sece_terminals_passed'] = bool(out['diode_reverse_peak_V'] < reverse_limit
        and out['detector_reverse_Vbe_V'] < 6. and out['switch_reverse_Vbe_V'] < 5.
        and out['diode_repetitive_current_covered'] and out['coil_voltage_peak_V'] < 120.)
    switch = design['parts'].get('load_switch_model', {'Vds_limit_V': 50., 'Vgs_limit_V': 20.})
    out['load_switch_terminals_passed'] = True
    if design['gate'] != 'off':
        out['load_switch_Vds_peak_V'] = peak(node('mcu')-node('out'))
        out['load_switch_Vgs_peak_V'] = peak(node('gate')-node('out'))
        out['load_switch_terminals_passed'] = bool(out['load_switch_Vds_peak_V'] < switch['Vds_limit_V']
                                                   and out['load_switch_Vgs_peak_V'] < switch['Vgs_limit_V'])
    out['passed'] = bool(pz < 120. and out['detector_Vce_V'] < 160. and out['switch_Vce_V'] < 150.
        and out['collector_current_passed'] and out['detector_collector_peak_A'] < .6
        and out['collector_KCL_passed'] and out['coil_current_passed']
        and out['pmic_input_peak_V'] < 20. and max(node('mcu')) <= 3.6
        and out['sece_terminals_passed'] and out['load_switch_terminals_passed'])
    out['scope'] = ('Nominal terminal screening. No single-surge allowance for repeated pulses. '
        'Pulse thermal SOA, tolerance/mismatch, coil saturation curve, PCB and hardware remain unqualified.')
    return out
