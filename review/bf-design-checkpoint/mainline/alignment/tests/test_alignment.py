import copy,json,math,pathlib,re,sys,unittest
import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import expm
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import adapters as a
from contract import validate,assess,fixture_copy
OUT=None

def record(name,value):a.write(OUT/(name+'.json'),value)

def analytic_exact(duration=.004):
    """Independent piecewise analytic RC solution for declared diagnostic only."""
    tau=.001;src=6.;eq_on=-4.;rise=5.05;fall=3.67;t=0.;v=0.;enabled=False;events=[]
    while t<duration-1e-15:
        eq=eq_on if enabled else src;level=fall if enabled else rise
        h=min(tau*math.log((v-eq)/(level-eq)),duration-t)
        v=eq+(v-eq)*math.exp(-h/tau);t+=h
        if t<duration-1e-14:events.append((t,'uvlo_fall' if enabled else 'uvlo_rise'));enabled=not enabled
    return events,v

class Alignment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.u=json.loads((ROOT/'contracts/upstream-default.json').read_text());cls.c=json.loads((ROOT/'contracts/cloud-default.json').read_text());cls.e=json.loads((ROOT/'contracts/event-v2.json').read_text())
        cls.up=OUT/'host-upstream';cls.cloud=OUT/'host-cloud'
        a.compile_host(cls.up,'upstream');a.compile_host(cls.cloud,'cloud')
        cls.stable=a.replay_pair(cls.up,cls.cloud);record('firmware-stable-defaults',cls.stable)
    def test_01_input_hashes_still_bound(self):
        rows=json.loads((ROOT/'contracts/source-lock.json').read_text())['sources'];self.assertEqual(len(rows),16)
        for key,row in rows.items():self.assertEqual(a.sha(row['path']),row['sha256'],key)
    def test_02_contracts_validate(self):
        for c in (self.u,self.c,self.e):validate(c)
    def test_03_reject_unknown_contract_fields(self):
        c=copy.deepcopy(self.u);c['firmware']['unbound_hack']=1
        with self.assertRaises(Exception):validate(c)
    def test_04_reject_wrong_units(self):
        c=copy.deepcopy(self.u);c['units']['length']='mm'
        with self.assertRaises(Exception):validate(c)
    def test_05_reject_nonfinite_quantity(self):
        c=copy.deepcopy(self.u);c['geometry']['gap_m']=float('nan')
        with self.assertRaises(Exception):validate(c)
    def test_06_reject_deadline_after_horizon(self):
        c=copy.deepcopy(self.u);c['mission']['deadline_s']=5
        with self.assertRaisesRegex(ValueError,'DEADLINE'):validate(c)
    def test_07_default_closed_loop_comparison_rejected(self):
        x=assess(self.u,self.c);record('closed-loop-admission',x);self.assertFalse(x['admitted'])
        self.assertIn('circuit',[r['axis'] for r in x['axes'] if not r['compatible']])
    def test_08_direct_force_kernel_contract_admitted(self):
        self.assertTrue(assess(self.u,self.c,'direct_force_kernel')['admitted'])
    def test_09_matched_fixture_does_not_promote_defaults(self):
        # Explicitly imposed firmware/receiver fixture can be shared, but it
        # cannot imply that either source default implements the other policy.
        fixture=fixture_copy(self.c,firmware=self.u['firmware'],packet=self.u['packet'],receiver=self.u['receiver'],mission=self.u['mission'])
        self.assertTrue(assess(self.u,fixture,'imposed_firmware_replay')['admitted'])
        self.assertFalse(assess(self.u,fixture,'closed_loop_mission')['admitted'])
        self.assertNotEqual(self.u['firmware'],self.c['firmware'])
        record('explicit-fixture-admission',{'contract':fixture,'admission':assess(self.u,fixture,'imposed_firmware_replay'),'status':'DECLARATIVE_FIXTURE_ONLY; not an implemented cloud policy migration'})
    def test_10_nominal_geometry_equal(self):
        rows=[]
        for deg in (0,5,30,65):
            angle=np.deg2rad(deg);u=a.upstream_native.coordinates(angle,48);c=a.cloud_coordinates(angle,48)
            rows.append({'gap_mm':48,'angle_deg':deg,'upstream_m':list(u),'cloud_m':list(c),'delta_m':list(np.array(u)-c)})
            np.testing.assert_allclose(u,c,rtol=0,atol=1e-14)
        record('geometry-nominal',rows)
    def test_11_non_nominal_gap_trajectory_mismatch(self):
        rows=[]
        for gap in (40,60):
            for deg in (0,5,30,65):
                angle=np.deg2rad(deg);u=np.array(a.upstream_native.coordinates(angle,gap));c=np.array(a.cloud_coordinates(angle,gap));delta=u-c
                expected=(gap-48)/1000*np.array([np.cos(angle)-1,-np.sin(angle)])
                np.testing.assert_allclose(delta,expected,rtol=0,atol=2e-16)
                rows.append({'gap_mm':gap,'angle_deg':deg,'upstream_m':u.tolist(),'cloud_m':c.tolist(),'delta_m':delta.tolist(),'distance_mm':float(np.linalg.norm(delta)*1000)})
                if deg:self.assertGreater(np.linalg.norm(delta),1e-5)
        record('geometry-nonnominal-mismatch',rows)
    def test_12_direct_force_kernel_equal_at_matched_coordinates(self):
        rows=[]
        for deg in (0,5,30,65):
            for q in (-.004,0,.004):
                angle=np.deg2rad(deg);u=a.force_at('upstream',angle,q);c=a.force_at('cloud',angle,q)
                self.assertLessEqual(abs(u-c),1e-12);rows.append({'angle_deg':deg,'q_m':q,'upstream_N':float(u),'cloud_N':float(c),'abs_difference_N':float(abs(u-c))})
        record('force-kernel-matched',rows)
    def test_13_gap_mismatch_changes_applied_force(self):
        rows=[]
        for gap in (40,60):
            for deg in (5,30):
                u=a.force_at('upstream',np.deg2rad(deg),0,gap);c=a.force_at('cloud',np.deg2rad(deg),0,gap)
                rows.append({'gap_mm':gap,'angle_deg':deg,'upstream_N':float(u),'cloud_N':float(c),'relative_difference':float(abs(u-c)/max(abs(c),1e-12))})
                self.assertGreater(abs(u-c),1e-9)
        record('force-trajectory-mismatch',rows)
    def test_14_force_interpolation_discretizations_not_identical(self):
        rows=[]
        for deg,q in [(.13,.0002),(.37,-.0022),(1.13,.0032),(4.87,-.0032),(8.13,.0002)]:
            angle=np.deg2rad(deg);u=a.interpolated_force('upstream',angle,q);c=a.interpolated_force('cloud',angle,q);direct=a.force_at('upstream',angle,q,n=10)
            rows.append({'angle_deg':deg,'q_m':q,'upstream_N':u,'cloud_N':c,'direct_n10_N':float(direct),'abs_difference_N':abs(u-c)})
        self.assertGreater(max(r['abs_difference_N'] for r in rows),1e-7)
        record('force-interpolation-mismatch',{'scope':'five original-grid local-cell evaluations, not complete table/FEM qualification','rows':rows})
    def test_15_unmatched_remanence_not_silently_accepted(self):
        with self.assertRaisesRegex(ValueError,'CLOUD_FIXED'):a.force_at('cloud',0,0,br=1.4)
        f=a.force_at('upstream',0,0,br=1.25);g=a.force_at('upstream',0,0,br=1.4)
        self.assertAlmostEqual(g/f,(1.4/1.25)**2,places=12)
    def test_16_firmware_default_timing_and_payload_mismatch(self):
        u=self.stable['upstream']['events'];c=self.stable['cloud']['events']
        self.assertTrue(u and c);self.assertNotEqual(u[0]['time_s'],c[0]['time_s']);self.assertNotEqual(u[0]['payload_hex'],c[0]['payload_hex'])
        record('firmware-default-summary',{'upstream_first_tx_s':u[0]['time_s'],'cloud_first_tx_s':c[0]['time_s'],'upstream_packets':len(u),'cloud_packets':len(c),'upstream_payload':u[0]['payload_hex'],'cloud_payload':c[0]['payload_hex'],'fixture':'3.3V supply and PGOOD; 100us imposed sample grid for 0.4s; original firmware defaults','no_closed_loop_power_claim':True})
    def test_17_pgood_loss_inflight_policy_differs(self):
        rows=a.replay_pair(self.up,self.cloud,duration=.12,perturb={'after_tx_s':.0004,'pgood_V':0.})
        record('firmware-inflight-pgood-drop',{'fixture':'State-relative: PGOOD drops permanently 400us after each implementation enters first TX. Supply remains 3.3V. Absolute drop times differ to isolate policy.','traces':rows})
        self.assertEqual(len(rows['upstream']['events']),0);self.assertEqual(len(rows['cloud']['events']),1)
    def test_18_brownout_threshold_differs(self):
        rows=a.replay_pair(self.up,self.cloud,duration=.09,perturb={'after_tx_s':.0004,'supply_V':1.75})
        record('firmware-inflight-1p75V',{'fixture':'State-relative supply drop to 1.75V; PGOOD artificially held 3.3V for threshold isolation, not physical PMIC behavior','traces':rows})
        self.assertEqual(len(rows['upstream']['events']),0);self.assertGreaterEqual(len(rows['cloud']['events']),1)
    def test_19_common_C_payload_can_be_explicitly_matched(self):
        conf={'device_id':[0x04030201,0x08070605]};d=OUT/'host-cloud-matched-id';a.compile_host(d,'cloud',conf)
        rows=a.replay_pair(self.up,d,duration=.1,cloud_config=conf)
        self.assertEqual(rows['upstream']['events'][0]['payload_hex'],rows['cloud']['events'][0]['payload_hex'])
        record('payload-matched-fixture',{'configuration':conf,'payload_hex':rows['cloud']['events'][0]['payload_hex'],'scope':'byte-level encoding only; no timing/policy equivalence'})
    def test_20_decoder_grouping_matches_given_identical_records(self):
        records=copy.deepcopy(self.stable['upstream']['events']);records.append(copy.deepcopy(records[0]))
        u=a.upstream_solver.receive(self.up,records,a.upstream_contracts.DEFAULT['link'])['events'];c=a.cloud_firmware.receive(records)['events']
        self.assertEqual(u,c);record('decoder-matched-records',{'input':records,'groups':u})
    def test_21_receiver_loss_model_differs(self):
        records=copy.deepcopy(self.stable['upstream']['events']);link={**a.upstream_contracts.DEFAULT['link'],'loss_probability':1.}
        u=a.upstream_solver.receive(self.up,records,link);c=a.cloud_firmware.receive(records)
        self.assertEqual(u['events'],[]);self.assertGreater(len(c['events']),0)
        record('receiver-link-mismatch',{'fixture_link':link,'upstream_groups':len(u['events']),'cloud_groups':len(c['events']),'scope':'cloud receives all records on ideal link; same lossy link must be an explicit shared fixture'})
    def test_22_receiver_deadline_is_explicit(self):
        records=[{'time_s':.7,'payload_hex':'424644320102030405060708','capture_id':'late','tx_complete':True}]
        d=OUT/'deadline-fixture';d.mkdir()
        ctx={'output_dir':str(d),'inputs':{'coupled_power':{'result':{'metrics':{'packet_events':records}}}},'design':{'mission':{'duration_s':1.,'receiver_deadline_s':.5,'minimum_radio_events':1}}}
        c=a.cloud_firmware.receiver_stage(ctx);u=a.upstream_solver.receive(self.up,records,a.upstream_contracts.DEFAULT['link'])
        self.assertEqual(c['design_status'],'unsatisfied');self.assertEqual(len(u['events']),1)
        record('mission-deadline-mismatch',{'cloud_receiver_stage':c,'upstream_unfiltered_replay_group_count':len(u['events']),'scope':'upstream has no explicit earlier deadline input; its emitted events are bounded only by solve horizon'})
    def test_23_conservative_sampling_detects_subgrid_loss(self):
        t=np.array([0,.00002,.00003,.00004,.0001,.0002]);v=np.array([3.3,3.3,0,3.3,3.3,3.3]);grid=np.array([0,.0001,.0002])
        out=a.upstream_solver.conservative_sample(t,v,grid)
        self.assertEqual(out[1],0);self.assertEqual(np.interp(grid,t,v)[1],3.3)
        record('subgrid-sampling',{'raw_t_s':t.tolist(),'raw_V':v.tolist(),'grid_s':grid.tolist(),'upstream_conservative_V':out.tolist(),'linear_interpolation_V':np.interp(grid,t,v).tolist(),'scope':'sampling semantics only; cloud accepted-interval min sample mechanism is different'})
    def test_24_actual_deck_coefficients_and_passive_analytic_fixture(self):
        d=OUT/'passive-deck-fixture';d.mkdir();table=d/'force-table.npz';np.savez(table,angles=[0.,1.2],qs=[-.008,.008],values=np.zeros((2,2)))
        placeholder=d/'placeholder.sub';placeholder.write_text('* INERT FILE-COPY PLACEHOLDER. NO VENDOR MODEL.\n')
        rom=a.cloud_power.parameters();spec=a.upstream_contracts.validate({});old=a.upstream_solver.PMIC;a.upstream_solver.PMIC=placeholder
        try:a.upstream_solver.deck(d,spec,rom,table,np.array([0.,.02]),np.zeros(2),resistor=1e5)
        finally:a.upstream_solver.PMIC=old
        deck=(d/'system.cir').read_text();self.assertEqual(deck.count('Cpiezo '),1)
        mass=float(re.search(r'Cmass u 0 ([^ ]+)',deck)[1]);cp=float(re.search(r'Cpiezo pz1 pz2 ([^ ]+)',deck)[1]);theta=float(re.search(r'Bpiezo pz2 pz1 I=([^*]+)',deck)[1]);k=float(re.search(r'V\(force\)-([^*]+)\*V\(q\)',deck)[1]);damping=float(re.search(r'\*V\(q\)-([^*]+)\*V\(u\)',deck)[1]);R=float(re.search(r'Rtest port pz2 ([^\n]+)',deck)[1])
        self.assertIn('-'+str(theta)+'*V(pz1,pz2)',deck)
        A=np.array([[0,1,0],[-k/mass,-damping/mass,-theta/mass],[0,theta/cp,-1/(R*cp)]])
        initial=np.array([.001,0.,0.]);duration=.02;exact=expm(A*duration)@initial
        def rhs(t,z):
            q,v,vp=z[:3];return [*(A@z[:3]),damping*v*v+vp*vp/R]
        sol=solve_ivp(rhs,[0,duration],[*initial,0.],method='DOP853',rtol=1e-11,atol=1e-14)
        np.testing.assert_allclose(sol.y[:3,-1],exact,rtol=1e-8,atol=1e-11)
        E0=.5*k*initial[0]**2;z=sol.y[:,-1];Ef=.5*k*z[0]**2+.5*mass*z[1]**2+.5*cp*z[2]**2;residual=abs(Ef+z[3]-E0)/E0
        self.assertLess(residual,1e-7)
        record('passive-analytic-fixture',{'ROM':rom,'deck_parsed_coefficients':{'mass':mass,'cp':cp,'theta':theta,'k':k,'damping':damping,'R':R},'initial_state':[.001,0.,0.],'analytic_final':exact.tolist(),'numeric_final':sol.y[:3,-1].tolist(),'energy_relative_residual':float(residual),'scope':'Synthetic free-decay from explicitly replaced .001m initial state with zero force. Tests reciprocal equations parsed from actual generated passive deck, independently integrated against matrix exponential. Deck was NOT executed. Inherited cloud ROM deliberately injected; no assertion of missing upstream native ROM equality.'})
    def test_25_event_v2_and_macro_against_same_analytic_RC_fixture(self):
        event=a.load_module('alignment_event_v2',a.EVENT/'event_power.py');event.verify_parent()
        design={'mechanics':{'mode':'controlled_input','controlled_input':{'voltage_V':6.,'series_resistance_ohm':10000.,'duration_s':.004}},'power':{'input_capacitance_uF':.1,'pmic':{'startup_rail_energy_J':1.,'input_quiescent_A':0.,'input_leakage_ohm':1e30,'output_leakage_ohm':1e30}},'mission':{'duration_s':.004,'step_s':.0005}}
        expected,v=analytic_exact();results={}
        for name,module in [('cloud_macro',a.cloud_power),('event_v2',event)]:
            r=module.simulate(design,a.cloud_power.ConstantLoad(0),step_s=.0005)
            record('analytic-'+name,r);results[name]={'final_vin_V':r['trace'][-1][4],'final_v_error_V':abs(r['trace'][-1][4]-v),'energy_residual':r['metrics']['relative_energy_residual'],'pmic_events':[(e['time_s'],n) for e in r.get('pmic_events',[]) for n in e['events']]}
        observed=results['event_v2']['pmic_events'];self.assertEqual([e[1] for e in observed],[e[1] for e in expected])
        err=max(abs(x[0]-y[0]) for x,y in zip(observed,expected));self.assertLessEqual(err,2e-9);self.assertLessEqual(results['event_v2']['final_v_error_V'],2e-7)
        self.assertGreater(results['cloud_macro']['final_v_error_V'],1e-4)
        record('analytic-RC-differential',{'fixture_design':design,'expected_events':expected,'expected_final_vin_V':v,'event_time_abs_error_s':err,'results':results,'scope':'Both are the same deliberately altered behavioral analytic fixture; upstream vendor PMIC absent, excluded and not approximated by this test.'})
    def test_26_same_behavioral_physics_not_same_numerical_revision(self):
        # Hold all physical assumptions fixed and retain revision separation.
        for axis in ('geometry','force','initial_energy','source_trajectory','circuit','firmware','packet','receiver','mission','units'):self.assertEqual(self.c[axis],self.e[axis])
        self.assertNotEqual(self.c['version'],self.e['version'])
        self.assertFalse(assess(self.u,self.e)['admitted'])
    def test_27_no_missing_native_evidence_claim(self):
        self.assertFalse(self.u['version']['native_evidence_available'])
        self.assertIsNone(self.u['initial_energy']['mechanical_J'])
        self.assertFalse((OUT/'native-LTspice-result.json').exists())
    def test_28_pinned_CAD_declared_placement_matches_force_coordinates(self):
        from cad_source_check import declared_centers
        fetch=json.loads((ROOT/'source-supplement/fetch-receipt.json').read_text())
        for item in fetch['files']:
            path=ROOT/'source-supplement'/item['display_title'];data=path.read_bytes()
            self.assertEqual(a.hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest(),item['sha'])
        rows=[]
        for gap in (40,48,60):
            row=declared_centers(gap);tip=np.array(row['world_mm']['tip_magnet'])/1000;driver=np.array(row['world_mm']['driver_magnet'])/1000
            for deg in (0,5,30,65):
                angle=np.deg2rad(deg);x=driver[0]*np.cos(angle)-driver[1]*np.sin(angle);z=driver[0]*np.sin(angle)+driver[1]*np.cos(angle)
                actual=[tip[0]-x,z-tip[1]];expected=a.upstream_native.coordinates(angle,gap)
                np.testing.assert_allclose(actual,expected,atol=2e-16,rtol=0)
            rows.append(row)
        record('upstream-CAD-force-placement',{'rows':rows,'conclusion':'Declared upstream CAD placement and force trajectory match across tested gaps. Cross-chain gap convention represents different designs, not a demonstrated internal upstream correctness bug.','native_CAD_executed':False})
    def test_29_native_rail_observation_gap_and_save_only_derivative(self):
        from rail_observation import audit,add_saves,REQUIRED
        d=OUT/'native-rail-unexecuted-fixture';d.mkdir();table=d/'force-table.npz';np.savez(table,angles=[0.,1.2],qs=[-.008,.008],values=np.zeros((2,2)))
        placeholder=d/'placeholder.sub';placeholder.write_text('* INERT PLACEHOLDER: no vendor model\n');old=a.upstream_solver.PMIC;a.upstream_solver.PMIC=placeholder
        try:a.upstream_solver.deck(d,a.upstream_contracts.validate({}),a.cloud_power.parameters(),table,np.array([0.,4.]),np.zeros(2))
        finally:a.upstream_solver.PMIC=old
        original=(d/'system.cir').read_text();before=audit(original);self.assertEqual(set(before['required_missing']),set(REQUIRED));self.assertFalse(before['rail_charge_discharge_observable'])
        rec=add_saves(d/'system.cir',d/'observation-only.cir');after=audit((d/'observation-only.cir').read_text());self.assertTrue(after['rail_charge_discharge_observable']);self.assertEqual((d/'system.cir').read_text(),original)
        self.assertFalse(rec['physical_stimulus_changed']);self.assertFalse(rec['vendor_executed'])
        record('native-rail-observation-gap',{'before':before,'after':after,'derivative':rec,'generated_deck':'native-rail-unexecuted-fixture/system.cir','scope':'Actual pinned deck builder with inert model-copy placeholder and synthetic zero-force table/inherited ROM. No vendor/native simulation. Added saves alone are necessary, not proof that model topology and signals are correct.'})
    def test_30_cannot_overwrite_rail_evidence(self):
        from rail_observation import add_saves
        d=OUT/'native-rail-unexecuted-fixture'
        with self.assertRaisesRegex(ValueError,'OUTPUT_MUST_BE_NEW'):add_saves(d/'system.cir',d/'system.cir')
