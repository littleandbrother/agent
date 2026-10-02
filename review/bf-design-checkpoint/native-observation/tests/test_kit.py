"""Synthetic/static checks ONLY. Never imports or calls a native simulator."""
import copy,json,struct,sys,tempfile,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))
from build_decks import CASES,PORTS,SIGNALS,render
from static_audit import audit_deck,static_audit,runtime_identity,parse_deck
from retained_raw import EvidenceError,read_raw,require_columns,require_finished_log,Raw
from analyze_retained import cumtrap,integral,event_brackets,pg_events,analyze_trace,validate_receipt
from compare_refinement import compare_events,compare,LEDGER_KEYS

def raw_bytes(t,values,names=None,flags="real double",encoding="utf-16-le",ascii_mode=False,kinds=None):
    names=names or ["v(out)"]; kinds=kinds or ["voltage"]*len(names); n=len(names)+1
    h=f"Title: SYNTHETIC TEST ONLY\nPlotname: Transient Analysis\nFlags: {flags}\nNo. Variables: {n}\nNo. Points: {len(t)}\nVariables:\n\t0\ttime\ttime\n"
    for i,(name,kind) in enumerate(zip(names,kinds),1):h+=f"\t{i}\t{name}\t{kind}\n"
    if ascii_mode:
        h+="Values:\n"; body=""
        for i,(tt,row) in enumerate(zip(t,values)):
            body+=f"{i}\t{tt:.17g}\n"+"".join(f"\t{v:.17g}\n" for v in row)
        return (h+body).encode(encoding)
    h+="Binary:\n"
    dtype=np.dtype([("t","<f8"),("v","<f8" if "double" in flags.split() else "<f4",(n-1,))])
    a=np.empty(len(t),dtype);a["t"]=t;a["v"]=values
    return h.encode(encoding)+a.tobytes()

class TestKit(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name);self.plan=json.loads((ROOT/"EXACT-PLAN.json").read_text())
    def tearDown(self): self.tmp.cleanup()
    def read(self,data):
        f=self.p/"synthetic.raw";f.write_bytes(data);return read_raw(f)
    def test_four_static_decks(self):
        r=static_audit();self.assertEqual(len(r["decks"]),4);self.assertFalse(r["runtime_ready"]);self.assertEqual(r["native_runs"],0)
    def test_source_prefix_and_suffix_distinct(self):
        a=render("source-open-coarse");b=render("driven-down-coarse")
        self.assertIn("0.499999 1 0.500001 0",a);self.assertIn("0.60 3.0",b);self.assertNotIn("0.60 3.0",a)
    def test_only_resolution_changes_within_pair(self):
        for mode in ["source-open","driven-down"]:
            a=[l for l in render(mode+"-coarse").splitlines() if not l.startswith(("* Case:",".tran",".options plotwinsize"))]
            b=[l for l in render(mode+"-fine").splitlines() if not l.startswith(("* Case:",".tran",".options plotwinsize"))]
            self.assertEqual(a,b)
    def test_all_11_sensors(self):
        es,ds=parse_deck(render("source-open-coarse"));self.assertEqual(len(PORTS),11)
        for p,e,n,s in PORTS:self.assertEqual(es[s.lower()][1:],[e,n,"0"])
    def test_initial_states_and_temperature(self):
        text=render("source-open-coarse");self.assertEqual(text.count("IC=0"),5);self.assertIn(".temp 25",text);self.assertIn("tnom=27",text)
    def test_explicit_esr_and_parallel_shunt(self):
        text=render("driven-down-fine");self.assertIn("L1 l_inner out 10u IC=0 Rser=0 Rpar=1e12 Cpar=0",text);self.assertIn("Cout cout_inner 0 100u IC=0",text)
    def test_saves_are_nodes_not_differential(self):
        self.assertEqual(len(SIGNALS),51);self.assertTrue(all("," not in x for x in SIGNALS))
    def test_deck_tamper_rejected(self):
        with self.assertRaises(EvidenceError):audit_deck(render("source-open-coarse").replace("47u","10u"),"source-open-coarse")
    def test_duplicate_element_rejected(self):
        with self.assertRaises(EvidenceError):parse_deck("R1 a 0 1\nR1 b 0 2")
    def test_absent_model_never_runtime_success(self):
        with self.assertRaises(EvidenceError):runtime_identity(None,None,None)
    def test_placeholder_model_rejected(self):
        f=self.p/"fake.sub";f.write_text("* INERT PLACEHOLDER")
        with self.assertRaises(EvidenceError):runtime_identity(f,f,f)
    def test_binary_double(self):
        r=self.read(raw_bytes([0,.1],[[1.1234567890123],[2.1234567890123]]));self.assertAlmostEqual(r.columns["v(out)"][0],1.1234567890123,13);self.assertFalse(r.metadata["native_execution_authenticated"])
    def test_binary_float32(self):
        r=self.read(raw_bytes([0,.1],[[1.25],[2.5]],flags="real forward"));self.assertEqual(r.columns["v(out)"][1],2.5)
    def test_ascii_utf8(self):
        r=self.read(raw_bytes([0,.1],[[1.25],[2.5]],encoding="utf-8",ascii_mode=True));self.assertEqual(r.metadata["format"],"ascii")
    def test_ascii_utf16(self):
        r=self.read(raw_bytes([0,.1],[[1.25],[2.5]],ascii_mode=True));self.assertEqual(r.columns["v(out)"][0],1.25)
    def test_unsupported_flags(self):
        for flag in ["real FastAccess","complex","real stepped"]:
            with self.subTest(flag=flag),self.assertRaises(EvidenceError):self.read(raw_bytes([0,.1],[[0],[1]],flags=flag))
    def test_truncation_and_extra_bytes(self):
        data=raw_bytes([0,.1],[[0],[1]])
        for bad in [data[:-1],data+b"x"]:
            with self.assertRaises(EvidenceError):self.read(bad)
    def test_negative_time_not_absolute(self):
        with self.assertRaises(EvidenceError):self.read(raw_bytes([0,-.1],[[0],[1]]))
    def test_duplicate_time_not_dropped(self):
        with self.assertRaises(EvidenceError):self.read(raw_bytes([0,0],[[0],[1]]))
    def test_nonfinite_values_rejected(self):
        for x in [np.nan,np.inf,-np.inf]:
            with self.assertRaises(EvidenceError):self.read(raw_bytes([0,.1],[[0],[x]]))
    def test_wrong_variable_kinds(self):
        for name,kind in [("v(vin)","device_current"),("i(vdrive)","voltage")]:
            with self.assertRaises(EvidenceError):self.read(raw_bytes([0,.1],[[0],[1]],names=[name],kinds=[kind]))
    def test_correct_device_current_kind(self):
        r=self.read(raw_bytes([0,.1],[[0],[1]],names=["i(vdrive)"],kinds=["device_current"]));self.assertEqual(r.columns["i(vdrive)"][1],1)
    def test_duplicate_header_rejected(self):
        data=raw_bytes([0,.1],[[0],[1]])
        for field in ["No. Points: 2","Flags: real double"]:
            bad=data.replace(field.encode("utf-16-le"),(field+"\n"+field).encode("utf-16-le"))
            with self.assertRaises(EvidenceError):self.read(bad)
    def test_duplicate_channel_rejected(self):
        with self.assertRaises(EvidenceError):self.read(raw_bytes([0,.1],[[0,0],[1,1]],names=["v(out)","V(OUT)"]))
    def test_required_signal_missing(self):
        r=self.read(raw_bytes([0,.1],[[0],[1]]))
        with self.assertRaises(EvidenceError):require_columns(r,["v(vin)"])
    def test_missing_file_rejected(self):
        with self.assertRaises(EvidenceError):read_raw(self.p/"none.raw")
    def test_raw_size_cap_before_read(self):
        f=self.p/"large.raw"
        with f.open("wb") as h:h.truncate(1073741825)
        with self.assertRaisesRegex(EvidenceError,"BUDGET"):read_raw(f)
    def test_good_completed_log(self):
        f=self.p/"synthetic.log";f.write_text("vin_peak: MAX(v(vin))= 5.5 FROM 0 TO 2\nTotal elapsed time: 1 second\n")
        self.assertEqual(require_finished_log(f,["vin_peak"])["measures"]["vin_peak"],5.5)
    def test_malformed_measures_rejected(self):
        for value in ["1.#INF","nan","inf","1e+","1e3garbage"]:
            f=self.p/"synthetic.log";f.write_text(f"vin_peak: MAX= {value}\nTotal elapsed time: 1 second\n")
            with self.subTest(value=value),self.assertRaises(EvidenceError):require_finished_log(f,["vin_peak"])
    def test_duplicate_measure_rejected(self):
        f=self.p/"synthetic.log";f.write_text("vin_peak: MAX=1\nvin_peak: MAX=2\nTotal elapsed time: 1\n")
        with self.assertRaises(EvidenceError):require_finished_log(f,["vin_peak"])
    def test_incomplete_and_error_logs(self):
        for text in ["vin_peak: MAX=1\n","Fatal error\nvin_peak: MAX=1\nTotal elapsed time:1\n"]:
            f=self.p/"synthetic.log";f.write_text(text)
            with self.assertRaises(EvidenceError):require_finished_log(f,["vin_peak"])
    def test_event_brackets_no_interpolation(self):
        e=event_brackets(np.array([0.,1.,2.]),np.array([0.,3.,0.]),1.5)
        self.assertEqual(e[0]["time_bracket_s"],[0,1]);self.assertEqual(e[1]["direction"],"falling")
    def test_capacitor_identities_analytic_ramp(self):
        t=np.linspace(0,1,1001);C=1e-6;v=2*t;i=np.full_like(t,2*C)
        self.assertLess(np.max(np.abs(cumtrap(t,i)-C*v)),1e-18)
        self.assertLess(abs(integral(t,v*i)-.5*C*v[-1]**2),1e-18)
    def test_inductor_parallel_split(self):
        v=2.;R=1e12;total=.01+v/R;ideal=total-v/R
        self.assertAlmostEqual(ideal,.01);self.assertEqual(v*v/R,4e-12)
    def test_pgood_unresolved_not_no_events_success(self):
        t=np.linspace(0,2,4001);c={k:np.zeros_like(t) for k in ["v(pgood)","v(vin)","v(out)"]}
        r=pg_events(t,c,self.plan["analysis"]);self.assertIsNone(r["events"])
        self.assertFalse(compare_events(None,None,self.plan["analysis"],"PGOOD")["passed"])
    def test_pgood_first_assertion_and_fall_are_distinct(self):
        t=np.linspace(0,2,20001);x=np.where((t>=.3)&(t<.8),3.3,0.)
        c={"v(pgood)":x,"v(vin)":np.zeros_like(t),"v(out)":np.full_like(t,3.3)}
        r=pg_events(t,c,self.plan["analysis"]);self.assertEqual([e["direction"] for e in r["events"]],["rising","falling"])
    def test_synthetic_inconsistent_trace_cannot_pass(self):
        t=np.linspace(0,2,4001);c={s.lower():np.zeros_like(t) for s in SIGNALS}
        raw=Raw(t,c,"SYNTHETIC",{"synthetic":True,"native_execution_authenticated":False})
        plan=copy.deepcopy(self.plan);plan["cases"]["source-open-coarse"]["maxstep_s"]=.0005
        r=analyze_trace(raw,"source-open-coarse",plan)
        self.assertFalse(r["all_numerical_checks_passed"]);self.assertIsNone(r["PGOOD"]["events"])
    def positive_summary(self,resolution):
        event={"direction":"rising","time_bracket_s":[.299999,.3],"signal_bracket":[0,3.3],"analysis_level":1.65,"vin_V_bracket":[5.05,5.06],"vout_V_bracket":[3.31,3.312]}
        return {"schema_version":"native-observation-retained-metrics-v1","case_id":"driven-down-"+resolution,"all_numerical_checks_passed":True,"initial_state":{"zero_screen_passed":True},"numerical_checks":[{"name":"synthetic","max_abs_residual":0.,"tolerance":1e-9,"passed":True}],"energy_ledger":{k:0. for k in LEDGER_KEYS},"PGOOD":{"status":"OBSERVED_SIGNAL_BRACKETS","events":[event]},"VIN_reference_crossings":{"5.05":[],"3.67":[]},"switch_control_crossings":[],"pre_uvlo_observation":{"rails":{k:{"voltage_start_V":0.,"voltage_end_V":1.,"delta_charge_C":1e-6,"delta_energy_J":1e-6} for k in ["Ccap","Cvin2"]}}}
    def test_complete_synthetic_summary_comparison_passes(self):
        self.assertTrue(compare(self.positive_summary("coarse"),self.positive_summary("fine"),self.plan)["all_resolved_numerical_gates_passed"])
    def test_event_field_missing_in_both_rejected(self):
        a=self.positive_summary("coarse")["PGOOD"]["events"];del a[0]["vout_V_bracket"]
        with self.assertRaises(EvidenceError):compare_events(a,copy.deepcopy(a),self.plan["analysis"],"PGOOD")
    def test_report_string_flags_rejected(self):
        for path in ["numerical","initial"]:
            a,b=self.positive_summary("coarse"),self.positive_summary("fine")
            if path=="numerical":b["all_numerical_checks_passed"]="false"
            else:b["initial_state"]["zero_screen_passed"]="false"
            with self.assertRaises(EvidenceError):compare(a,b,self.plan)
    def test_expected_reference_keys_required(self):
        a,b=self.positive_summary("coarse"),self.positive_summary("fine");a["VIN_reference_crossings"]={};b["VIN_reference_crossings"]={}
        with self.assertRaises(EvidenceError):compare(a,b,self.plan)
    def test_nonfinite_summary_rejected(self):
        a,b=self.positive_summary("coarse"),self.positive_summary("fine");b["energy_ledger"]["macro_absorption_J"]=float("nan")
        with self.assertRaises(EvidenceError):compare(a,b,self.plan)
    def test_numeric_flag_inconsistency_rejected(self):
        a,b=self.positive_summary("coarse"),self.positive_summary("fine");b["numerical_checks"][0]["max_abs_residual"]=1.
        with self.assertRaises(EvidenceError):compare(a,b,self.plan)
    def test_missing_run_receipt_fails(self):
        with self.assertRaises(EvidenceError):validate_receipt({},"source-open-coarse",self.plan)
    def test_partial_trace_fails(self):
        t=np.array([0.,1.]);raw=Raw(t,{s.lower():np.zeros_like(t) for s in SIGNALS},"",{})
        with self.assertRaises(EvidenceError):analyze_trace(raw,"source-open-coarse",self.plan)

if __name__=="__main__":unittest.main(verbosity=2)

