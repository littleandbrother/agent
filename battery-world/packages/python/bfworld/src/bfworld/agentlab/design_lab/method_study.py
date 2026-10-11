"""Independent finite method study. Solver and Improver cannot modify E/V.

Cases use new asynchronous/synchronous callback sequences and a compiled C
core. The hidden sequences stay outside the participant tool view. Candidate
generation and all solving are performed by the actual fixed-model Pi SDK.
"""
import json
from pathlib import Path
from .case_c import command,CLANG,SDK,object_symbols
from .contracts import sha,sealed
from ..store import identity

ABI='''C ABI: void reset(void); void handle(int kind, uint32_t connection, uint32_t operation);
int pending(void); uint32_t connection(void); uint32_t operation(void); int deliveries(void).
Events 1=connect, 2=disconnect, 3=request, 4=sample_ready, 5=send_done, 6=timeout.
Connect installs current connection and clears pending work. Only request on
the current connection starts/replaces an operation. Valid sample_ready keeps
the request pending for send_done. Only send_done for the currently pending
(connection,operation) completes and increases deliveries once. Timeout for
the current pending pair cancels it. Disconnect for the current connection
disconnects and cancels; stale callbacks/disconnect/timeouts leave state intact.
Identity is exact uint32 equality, including 0 and values above 65535; operation
identity can be reused on a different connection. Idle pending=0, operation=0.
Synchronous task accepts request followed directly by send_done; sample_ready
is optional. Initialization has connection=0 but disconnected; connect(0) is
a real connected epoch. No allocation, I/O, process or network external calls.'''

STARTER=r'''#include <stdint.h>
static uint16_t c,op;static int p,d,connected;
void reset(void){c=op=p=d=connected=0;}
void handle(int k,uint32_t x,uint32_t y){
 if(k==1){c=(uint16_t)x;connected=1;p=0;op=0;}
 else if(k==2){connected=0;p=0;op=0;}
 else if(k==3&&connected&&x==c){op=(uint16_t)y;p=1;}
 else if(k==4){p=1;}
 else if(k==5&&p){d++;p=0;op=0;}
 else if(k==6){p=0;op=0;}
}
int pending(void){return p;}uint32_t connection(void){return c;}
uint32_t operation(void){return op;}int deliveries(void){return d;}
'''


def cases():
    # These are development/held-out *variants*, not independent papers.
    return {
        'reconnect':[(1,11,0),(3,11,7),(1,12,0),(3,12,8),(2,11,0),(4,11,7),(5,11,7),(4,12,8),(5,12,8),(5,12,8)],
        'same-operation-new-epoch':[(1,31,0),(3,31,5),(1,32,0),(3,32,5),(6,31,5),(5,31,5),(5,32,5)],
        'wide-and-zero-identity':[(1,4294967293,0),(3,4294967293,4294902001),(4,4294967293,4294902001),
                                  (5,4294967293,4294902001),(1,0,0),(3,0,0),(5,0,0),(5,0,0)],
        'replacement-and-late-timeout':[(1,17,0),(3,17,8),(3,17,9),(6,17,8),(5,17,8),(4,17,9),(5,17,9)],
        'synchronous-negative-scope':[(1,9,0),(3,9,3),(5,9,3),(3,9,4),(5,9,4),(2,9,0)]
    }


def expected(sequence):
    connected=False;c=op=0;p=d=0;rows=[]
    for k,x,y in sequence:
        if k==1:connected=True;c=x;op=0;p=0
        elif k==2 and connected and x==c:connected=False;op=0;p=0
        elif k==3 and connected and x==c:op=y;p=1
        elif k==5 and connected and p and x==c and y==op:d+=1;p=0;op=0
        elif k==6 and connected and p and x==c and y==op:p=0;op=0
        rows.append([p,c,op,d])
    return rows


def evaluate(source, directory, sequences):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    if not isinstance(source,str) or len(source.encode())>32000:raise ValueError('METHOD_CORE_SIZE')
    if any(x in source for x in ('__asm','asm(','constructor')):raise ValueError('METHOD_CORE_ESCAPE')
    (directory/'program.c').write_text(source)
    runner='''#include <stdio.h>\n#include <stdint.h>\nvoid reset(void);void handle(int,uint32_t,uint32_t);
int pending(void);uint32_t connection(void);uint32_t operation(void);int deliveries(void);
int main(void){int k;unsigned x,y;reset();while(scanf("%d %u %u",&k,&x,&y)==3){
if(k==0){reset();continue;}handle(k,x,y);printf("%d %u %u %d\\n",pending(),connection(),operation(),deliveries());}return 0;}'''
    (directory/'runner.c').write_text(runner)
    command([CLANG,'-isysroot',SDK,'-std=c11','-O2','-Wall','-Werror','program.c','runner.c','-o','application'],
            directory,[CLANG.parent.parent.parent])
    command([CLANG,'--target=arm-none-eabi','-mcpu=cortex-m4','-mthumb','-O2','-ffreestanding',
             '-c','program.c','-o','application.o'],directory,[CLANG.parent.parent])
    sym=object_symbols(directory/'application.o')
    if sym['undefined']:raise ValueError('METHOD_CORE_EXTERNAL_DENIED')
    # Each replay process remains sandboxed. Input redirection is in a trusted
    # small runner; participant code cannot read evaluation directories.
    from ..engineering_projects import sandbox
    import subprocess
    result=[]
    for name,seq in sequences.items():
        data='\n'.join(' '.join(map(str,row)) for row in seq)+'\n'
        p=subprocess.run(['/usr/bin/sandbox-exec','-p',sandbox([directory],directory),str(directory/'application')],
                         cwd=directory,input=data,capture_output=True,text=True,timeout=5,
                         env={'PATH':'/usr/bin:/bin','HOME':str(directory),'TMPDIR':str(directory)})
        rows=[[int(v) for v in line.split()] for line in p.stdout.splitlines()]
        wanted=expected(seq)
        failures=[{'index':i,'event':seq[i],'expected':wanted[i],
                   'actual':rows[i] if i<len(rows) else None} for i in range(len(wanted))
                  if i>=len(rows) or rows[i]!=wanted[i]]
        result.append({'name':name,'passed':p.returncode==0 and rows==wanted,'rows':rows,
                       'failures':failures,'exit_code':p.returncode})
    v={'schema_version':'bf-method-core-check-v1','source_sha256':identity(source),
       'binary_sha256':sha(directory/'application'),'arm_object_sha256':sha(directory/'application.o'),
       'executor_sha256':sha(__file__),'checks':result,'passed':all(r['passed'] for r in result),
       'scope':'Compiled shared asynchronous logic with synthetic callbacks; not target peripherals/physical RF'}
    sealed(directory/'check.json',v)
    return v


def candidate(value,parent,episode_ids):
    fields={'instruction','hypothesis','falsifier','applicability','negative_scope','evidence_episodes'}
    if not isinstance(value,dict) or set(value)!=fields:raise ValueError('METHOD_CANDIDATE_FIELDS')
    if any(not isinstance(value[k],str) or not value[k].strip() for k in fields-{'evidence_episodes'}):
        raise ValueError('METHOD_CANDIDATE_TEXT')
    if len(value['instruction'].encode())>6000 or len(value['instruction'])<80:raise ValueError('METHOD_CANDIDATE_BOUND')
    if not value['evidence_episodes'] or set(value['evidence_episodes'])-set(episode_ids):raise ValueError('METHOD_EPISODE_BINDING')
    v={'schema_version':'bf-method-candidate-v1','parent_method':parent,'actor':'Pi',**value,
       'production_adoption':False,'patch_type':'versioned conditionally applied SKILL.md',
       'protected_E_V_modified':False}
    return {**v,'method_id':'H-method-'+identity(v)}


def decision(pairs, acquisition_usd):
    # Registered before dispatch. A ceiling result is a valid rejection. A cost
    # gain includes acquisition in this finite comparison, not projected reuse.
    base=sum(p['parent']['cost_usd'] for p in pairs)
    child=sum(p['child']['cost_usd'] for p in pairs)+acquisition_usd
    regression=any(p['parent']['passed'] and not p['child']['passed'] for p in pairs)
    gains=sum(not p['parent']['passed'] and p['child']['passed'] for p in pairs)
    all_child=all(p['child']['passed'] for p in pairs)
    cost_gain=base>0 and child<=base*.85
    adopted=all_child and not regression and ((gains>0 and child<=base*1.5) or cost_gain)
    return {'schema_version':'bf-method-adoption-v1','adopted':adopted,
            'decision':'LIMITED_VARIANT_ADOPTION' if adopted else 'REJECT',
            'pairs':len(pairs),'correctness_gains':gains,'regression':regression,
            'parent_total_usd':base,'child_plus_acquisition_usd':child,'acquisition_usd':acquisition_usd,
            'cost_gain_at_least_15pct_including_acquisition':cost_gain,
            'reason':'Registered finite pass/nonregression/cost rule; both pass without a gain is rejected.',
            'scope':'New callback variants only; no independent-paper generalization or stable RSI efficacy'}
