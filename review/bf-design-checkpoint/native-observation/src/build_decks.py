"""Generate exactly four prospective decks. Does not import or execute a simulator."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
PORTS = [
    ("PZ1", "0", "m_pz1", "VPM_PZ1"), ("PZ2", "0", "m_pz2", "VPM_PZ2"),
    ("CAP", "cap", "m_cap", "VPM_CAP"), ("Vin", "vin", "m_vin", "VPM_VIN"),
    ("SW", "sw", "m_sw", "VPM_SW"), ("Vout", "out", "m_out", "VPM_VOUT"),
    ("Vin2", "vin2", "m_vin2", "VPM_VIN2"), ("D1", "vin2", "m_d1", "VPM_D1"),
    ("D0", "0", "m_d0", "VPM_D0"), ("Pgood", "pgood", "m_pgood", "VPM_PGOOD"),
    ("GND", "0", "m_gnd", "VPM_GND"),
]
NODES = ["drv", "src_after_r", "pre_switch", "vin", "cap", "vin2", "sw",
         "l_after_r", "l_inner", "out", "cout_after_r", "cout_inner", "pgood", "sw_ctl"]
NODES += [x[2] for x in PORTS]
CURRENTS = ["Vdrive", "Vcontrol", "Vsupply", "V_L_TERMINAL", "V_COUT_BRANCH",
            "Cstorage", "Ccap", "Cvin2", "Cout", "L1", "Rsource", "R_L_ESR", "R_COUT_ESR", "Rload", "Sdrive"]
CURRENTS += [x[3] for x in PORTS]
SIGNALS = ["V(" + n + ")" for n in NODES] + ["I(" + x + ")" for x in CURRENTS]
CASES = {f"{mode}-{resolution}": {"mode": mode, "resolution": resolution,
    "maxstep_s": 5e-6 if resolution == "coarse" else 2.5e-6,
    "reltol": 1e-4 if resolution == "coarse" else 5e-5}
    for mode in ("source-open", "driven-down") for resolution in ("coarse", "fine")}

def render(case_id):
    c = CASES[case_id]
    drive = "PWL(0 0 0.005 0 0.05 4 0.20 4 0.25 5.5 0.50 5.5 "
    drive += "2.0 5.5)" if c["mode"] == "source-open" else "0.60 3.0 2.0 3.0)"
    control = ("PWL(0 1 0.499999 1 0.500001 0 2.0 0)"
               if c["mode"] == "source-open" else "PWL(0 1 2.0 1)")
    lines = [
        "* Native PMIC observation kit v1; PROSPECTIVE AND UNEXECUTED",
        "* Case: " + case_id,
        "* RC smoke, exact prospective review, runtime identity and authorization remain required.",
        "* PZ1 and PZ2 are explicitly clamped to ground; not open-piezo or door-world.",
        "* All VPM currents are positive from named external node INTO the macro pin.",
        "* Vendor body deliberately absent from this kit; never replace it with a placeholder.",
        '.lib "../vendor/LTC3588-1.sub"',
        "Vdrive drv 0 " + drive,
        "Rsource drv src_after_r 100",
        "Vsupply src_after_r pre_switch 0",
        "Vcontrol sw_ctl 0 " + control,
        "Sdrive pre_switch vin sw_ctl 0 SOURCE_SWITCH",
        ".model SOURCE_SWITCH SW(Ron=0.01 Roff=1e12 Vt=0.5 Vh=0 Lser=0 Vser=0)",
    ]
    lines += [f"{sensor} {external} {internal} 0" for _, external, internal, sensor in PORTS]
    lines += [
        "XU1 " + " ".join(x[2] for x in PORTS) + " LTC3588-1",
        "Cstorage vin 0 47u IC=0 Rser=0",
        "Ccap vin cap 1u IC=0 Rser=0",
        "Cvin2 vin2 0 4.7u IC=0 Rser=0",
        "R_L_ESR sw l_after_r 0.4",
        "V_L_TERMINAL l_after_r l_inner 0",
        "* Explicit 1T parallel shunt suppresses unspecified auto damping; loss is in ledger.",
        "* Ideal L current is I(V_L_TERMINAL)-V(l_inner,out)/1e12; do not assume I(L1) semantics.",
        "L1 l_inner out 10u IC=0 Rser=0 Rpar=1e12 Cpar=0",
        "R_COUT_ESR out cout_after_r 0.02",
        "V_COUT_BRANCH cout_after_r cout_inner 0",
        "Cout cout_inner 0 100u IC=0 Rser=0",
        "Rload out 0 10000",
        "* PGOOD has no external load/pullup; preserve unresolved output behavior if native model requires one.",
        ".temp 25",
        f".tran 0 2.0 0 {c['maxstep_s']:.10g} uic",
        f".options plotwinsize=0 numdgt=15 reltol={c['reltol']:.10g} abstol=1e-12 vntol=1e-9",
        ".options chgtol=1e-14 method=trap solver=norm gmin=1e-12 gshunt=0 cshunt=0 cshuntintern=0 tnom=27",
    ]
    for start in range(0, len(SIGNALS), 8):
        lines.append(".save " + " ".join(SIGNALS[start:start+8]))
    lines += [".meas TRAN vin_peak MAX V(vin)", ".meas TRAN vout_peak MAX V(out)",
              ".meas TRAN vin2_peak MAX V(vin2)", ".end", ""]
    return "\n".join(lines)

def write():
    d = ROOT / "decks"; d.mkdir(exist_ok=True)
    for case in CASES:
        (d / (case + ".cir")).write_text(render(case))
    return {"decks_created": list(CASES), "native_executions": 0}

if __name__ == "__main__":
    print(json.dumps(write(), indent=2))

