"""Datasheet-derived ideal settled rails and event logic, never a transient PMIC.

Source: Analog Devices LTC3588-1 rev C, pp.3,7,8,9,13.
4.8 V rail relations are the datasheet's ideal diagram, not a dynamic law.
Event logic consumes an independently supplied converter sleep event. It does
not invent a charging time, turn-on delay, dissipative path, or rail source.
"""
from dataclasses import dataclass
import math

CONTRACT_VERSION='ltc3588-rail-state-contract-v2-static-only'
class MissingDynamicEvidence(ValueError):pass

def finite_nonnegative(x,name):
    if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<0:
        raise ValueError('INVALID_'+name)
    return float(x)

def ideal_settled_rails(vin_v,cap_f=1e-6,vin2_f=4.7e-6):
    """Static energy arithmetic only; no finite settling time is asserted."""
    vin=finite_nonnegative(vin_v,'VIN');cc=finite_nonnegative(cap_f,'CCAP');c2=finite_nonnegative(vin2_f,'CVIN2')
    differential=min(vin,4.8);cap=vin-differential;vin2=differential
    return {'vin_v':vin,'cap_v':cap,'vin2_v':vin2,'vin_minus_cap_v':differential,
        'cap_charge_c':cc*differential,'vin2_charge_c':c2*vin2,
        'cap_energy_j':.5*cc*differential**2,'vin2_energy_j':.5*c2*vin2**2,
        'total_bypass_energy_j':.5*(cc+c2)*differential**2,
        'instantaneous_startup_threshold_j':None,'settling_time_s':None,
        'meaning':'ideal settled relationship, not a finite-time circuit solution'}

@dataclass(frozen=True)
class LogicState:
    buck_enabled:bool=False
    pgood:bool=False

@dataclass(frozen=True)
class Nominal3V3Policy:
    uvlo_rise_v:float=5.05
    uvlo_fall_v:float=3.67
    vout_target_v:float=3.3
    sleep_threshold_v:float=3.312
    pgood_fall_fraction:float=.92

def advance_nominal_event_logic(previous,vin_v,vout_v,*,converter_sleep_event=False,policy=Nominal3V3Policy()):
    """Threshold/event logic only, valid only in declared nominal policy scope.

    converter_sleep_event must be observed/generated independently from a
    qualified converter, not inferred by this function from time or energy.
    Equality is assigned to the crossed state as an explicit numerical convention.
    """
    if (not isinstance(previous,LogicState) or
        not isinstance(previous.buck_enabled,bool) or
        not isinstance(previous.pgood,bool) or
        not isinstance(converter_sleep_event,bool)):
        raise ValueError('EXPLICIT_LOGIC_STATE_AND_EVENT_REQUIRED')
    if not isinstance(policy,Nominal3V3Policy):
        raise ValueError('EXPLICIT_NOMINAL_POLICY_REQUIRED')
    for name in ('uvlo_rise_v','uvlo_fall_v','vout_target_v','sleep_threshold_v','pgood_fall_fraction'):
        finite_nonnegative(getattr(policy,name),'POLICY_'+name)
    vin=finite_nonnegative(vin_v,'VIN');vout=finite_nonnegative(vout_v,'VOUT')
    if not (policy.uvlo_rise_v>policy.uvlo_fall_v>policy.vout_target_v>0 and
        policy.sleep_threshold_v>=policy.vout_target_v and 0<policy.pgood_fall_fraction<1):
        raise ValueError('INVALID_NOMINAL_POLICY')
    enabled=previous.buck_enabled
    if enabled and vin<=policy.uvlo_fall_v: enabled=False
    elif not enabled and vin>=policy.uvlo_rise_v: enabled=True
    if converter_sleep_event and (not enabled or vout<policy.sleep_threshold_v):
        raise ValueError('SLEEP_EVENT_INCONSISTENT_WITH_NOMINAL_POLICY')
    good=previous.pgood
    if vout<=policy.pgood_fall_fraction*policy.vout_target_v:good=False
    elif converter_sleep_event:good=True
    return LogicState(enabled,good)

def require_transient_startup_prediction():
    raise MissingDynamicEvidence('BLOCKED: rail currents, charging/discharge dynamics, converter energy transfer, native model interface and independent trace qualification are missing; static rail arithmetic cannot predict startup')
