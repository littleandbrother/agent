"""Small dimension-explicit calculations; source applicability is a separate check."""
import math


def calculate(spec):
    if not isinstance(spec,dict) or set(spec)-{'kind','inputs','reported_value'}:
        raise ValueError('CALCULATION_FIELDS_INVALID')
    formulas={
        'elastic_displacement':({'energy_uJ','stiffness_N_m'},'mm','sqrt(2 * energy_uJ * 1e-6 / stiffness_N_m) * 1e3',
            lambda x:math.sqrt(2*x['energy_uJ']*1e-6/x['stiffness_N_m'])*1e3),
        'capacitor_energy':({'capacitance_uF','voltage_V'},'uJ','0.5 * capacitance_uF * voltage_V ** 2',
            lambda x:.5*x['capacitance_uF']*x['voltage_V']**2),
        'natural_frequency':({'stiffness_N_m','mass_g'},'Hz','sqrt(stiffness_N_m / (mass_g * 1e-3)) / (2*pi)',
            lambda x:math.sqrt(x['stiffness_N_m']/(x['mass_g']*1e-3))/(2*math.pi)),
    }
    if spec.get('kind') not in formulas:raise ValueError('CALCULATION_KIND_INVALID')
    fields,unit,formula,fn=formulas[spec['kind']];inputs=spec.get('inputs')
    if not isinstance(inputs,dict) or set(inputs)!=fields:raise ValueError('CALCULATION_UNITS_OR_FIELDS_INVALID')
    for key,value in inputs.items():
        if type(value) not in (float,int) or not math.isfinite(value) or not 0<value<1e12:
            raise ValueError('CALCULATION_INPUT_INVALID:'+key)
    value=fn(inputs);reported=spec.get('reported_value');error=None
    if reported is not None:
        if type(reported) not in (float,int) or not math.isfinite(reported) or reported<0:
            raise ValueError('CALCULATION_REPORTED_VALUE_INVALID')
        error=abs(reported-value)/max(abs(value),1e-20)
    return {'schema_version':'reference-calculation-v1','kind':spec['kind'],'inputs':inputs,
        'formula':formula,'value':value,'unit':unit,'reported_value':reported,
        'relative_error':error,'arithmetic_check':'not_compared' if error is None else 'pass' if error<=.01 else 'fail',
        'scope':'Arithmetic with explicit units only. Does not verify source transcription, physical efficiency, model domain or applicability.',
        'design_admission':False}
