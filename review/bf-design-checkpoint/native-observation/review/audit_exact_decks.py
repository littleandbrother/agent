"""Independent static review only; does not import, bind, or execute any simulator."""
from pathlib import Path
import hashlib,json,re,math,os
ROOT=Path(os.environ.get('NATIVE_OBSERVATION_KIT_ROOT',str(Path(__file__).resolve().parents[1]/'native-observation-kit-v1-20261001')))
EXPECTED={
'VPM_PZ1':'0 m_pz1 0','VPM_PZ2':'0 m_pz2 0','VPM_CAP':'cap m_cap 0',
'VPM_VIN':'vin m_vin 0','VPM_SW':'sw m_sw 0','VPM_VOUT':'out m_out 0',
'VPM_VIN2':'vin2 m_vin2 0','VPM_D1':'vin2 m_d1 0','VPM_D0':'0 m_d0 0',
'VPM_PGOOD':'pgood m_pgood 0','VPM_GND':'0 m_gnd 0',
'XU1':'m_pz1 m_pz2 m_cap m_vin m_sw m_out m_vin2 m_d1 m_d0 m_pgood m_gnd LTC3588-1',
'Rsource':'drv src_after_r 100','Vsupply':'src_after_r pre_switch 0',
'Sdrive':'pre_switch vin sw_ctl 0 SOURCE_SWITCH',
'Cstorage':'vin 0 47u IC=0 Rser=0','Ccap':'vin cap 1u IC=0 Rser=0',
'Cvin2':'vin2 0 4.7u IC=0 Rser=0','R_L_ESR':'sw l_after_r 0.4',
'V_L_TERMINAL':'l_after_r l_inner 0','L1':'l_inner out 10u IC=0 Rser=0 Rpar=1e12 Cpar=0',
'R_COUT_ESR':'out cout_after_r 0.02','V_COUT_BRANCH':'cout_after_r cout_inner 0',
'Cout':'cout_inner 0 100u IC=0 Rser=0','Rload':'out 0 10000'}
PORTS=['PZ1','PZ2','CAP','VIN','SW','VOUT','VIN2','D1','D0','PGOOD','GND']

def audit(p):
 text=p.read_text();lines=[l.strip() for l in text.splitlines() if l.strip() and not l.lstrip().startswith('*')]
 elems=[l for l in lines if not l.startswith('.')];names=[l.split()[0].upper() for l in elems]
 assert len(set(names))==len(names),'duplicate elements'
 lookup={l.split()[0].upper():' '.join(l.split()[1:]) for l in elems}
 for name,rest in EXPECTED.items():assert lookup[name.upper()].lower()==rest.lower(),name
 assert set(lookup)==set(n.upper() for n in EXPECTED)|{'VDRIVE','VCONTROL'},'unreviewed extra elements'
 assert [l for l in lines if l.lower().startswith('.lib')]==['.lib "../vendor/LTC3588-1.sub"']
 assert [l for l in lines if l.lower().startswith('.model')]==['.model SOURCE_SWITCH SW(Ron=0.01 Roff=1e12 Vt=0.5 Vh=0 Lser=0 Vser=0)']
 signals=[s.lower() for l in lines if l.lower().startswith('.save ') for s in l.split()[1:]]
 assert len(signals)==len(set(signals)), 'duplicate saves'
 nodes={n.lower() for l in elems if l[0].upper() not in ['X','S'] for n in l.split()[1:3]}-{'0'}
 assert all('v('+n+')' in signals for n in nodes),'missing node voltage'
 assert all('i(vpm_'+n.lower()+')' in signals for n in PORTS),'missing macro port current'
 assert all('i('+n.lower()+')' in signals for n in EXPECTED if n.upper() not in ['XU1']),'missing explicit branch current'
 assert not any(',' in s for s in signals),'require node saves, derive differentials'
 assert lines[-1].lower()=='.end'
 mode='source-open' if p.name.startswith('source-open') else 'driven-down'
 fine='fine' in p.name
 drive='drv 0 PWL(0 0 0.005 0 0.05 4 0.20 4 0.25 5.5 0.50 5.5 '+('2.0 5.5)' if mode=='source-open' else '0.60 3.0 2.0 3.0)')
 control='sw_ctl 0 '+('PWL(0 1 0.499999 1 0.500001 0 2.0 0)' if mode=='source-open' else 'PWL(0 1 2.0 1)')
 assert lookup['VDRIVE']==drive;assert lookup['VCONTROL']==control
 assert '.tran 0 2.0 0 '+('2.5e-06' if fine else '5e-06')+' uic' in lines
 opts={k.lower():v.lower() for l in lines if l.lower().startswith('.options ') for k,v in (s.split('=',1) for s in l.split()[1:])}
 for k,v in {'plotwinsize':'0','numdgt':'15','reltol':'5e-05' if fine else '0.0001','abstol':'1e-12','vntol':'1e-9','chgtol':'1e-14','method':'trap','solver':'norm','gmin':'1e-12','gshunt':'0','cshunt':'0','cshuntintern':'0','tnom':'27'}.items():assert opts[k]==v,(k,v)
 assert '.temp 25' in lines,'temperature must be explicit'
 return {'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'signals':len(signals),'element_count':len(elems),'static_pass':True,'mode':mode,'resolution':'fine' if fine else 'coarse'}

def algebra():
 # Arbitrary synthetic node voltages and oriented currents, not a circuit solution.
 drv,pre,vin,cap,vin2,sw,out,ci,li=5.5,5.1,4.9,.2,4.7,4.2,3.3,3.29,4.18
 src,cc,cin,c2,il,co,load,d1=4e-3,5e-6,1e-3,2e-6,.5e-3,.1e-3,.33e-3,1e-8
 macro={'vin':src-cc-cin,'cap':cc,'vin2':-c2-d1,'d1':d1,'sw':-il,'out':il-co-load}
 p_macro=vin*macro['vin']+cap*macro['cap']+vin2*(macro['vin2']+macro['d1'])+sw*macro['sw']+out*macro['out']
 p_external=(drv-pre)*src+(pre-vin)*src+(vin-cap)*cc+vin*cin+vin2*c2+(sw-li)*il+(li-out)*il+(out-ci)*co+ci*co+out*load
 residual=drv*src-p_macro-p_external
 assert abs(residual)<1e-15,residual
 i_ideal=il-(li-out)/1e12
 assert math.isclose((li-out)*il,(li-out)*i_ideal+(li-out)**2/1e12,rel_tol=1e-14)
 return {'scope':'synthetic sign/KCL power identity only; not native simulation','power_identity_residual_W':residual,'inductor_parallel_branch_identity_pass':True}

if __name__=='__main__':
 files=sorted((ROOT/'decks').glob('*.cir'));assert len(files)==4
 result={'native_executions':0,'decks':[audit(p) for p in files],'signed_ledger_algebra':algebra()}
 print(json.dumps(result,indent=2))
