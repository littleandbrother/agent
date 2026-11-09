"""Source-bound scientific figures; no science, provider calls or inferred wins."""
from pathlib import Path
import sys
import textwrap
from collections import Counter
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'s0'))
from common import load,save,ref,OUT

plt.rcParams.update({'font.family':['Arial','Helvetica','DejaVu Sans'],
    'font.size':11,'axes.spines.right':False,'axes.spines.top':False,
    'axes.linewidth':1.2,'legend.frameon':False,'svg.fonttype':'none','pdf.fonttype':42})
COLORS={'G':'#4D4D4D','D':'#B64342','R':'#0F4D92','on':'#0F4D92','off':'#B64342'}
PASS='#DDF3DE'; FAIL='#F6CFCB'; UNKNOWN='#CFCECE'


def export(fig,name):
    for ext in ('pdf','svg','png'):
        fig.savefig(HERE/f'{name}.{ext}',dpi=300,bbox_inches='tight',facecolor='white')
    plt.close(fig)


def counterfactuals():
    data=load(OUT/'a/FIXED-NEIGHBORHOOD-MATRIX.json')
    names=list(dict.fromkeys(r['design_name'] for r in data['rows']))
    conditions=['capture-recover','reuse-train','radio-gap']
    targets=[3,7,3]
    labels=['Parent: volatile / 3.2 V / holder off',
            'Persistence only / 3.2 V / holder off',
            'Holder-only fixed deletion',
            'Original complete reference',
            'Same reference, clear never',
            'Persistence + 1.9 V / holder off',
            '1.9 V only / volatile / holder off',
            'Saved G proposal, executed unchanged']
    fig=plt.figure(figsize=(13.8,7.1))
    gs=fig.add_gridspec(1,2,width_ratios=[4.5,1.7],wspace=.18)
    ax=fig.add_subplot(gs[0]); note=fig.add_subplot(gs[1]); note.axis('off')
    for i,name in enumerate(names):
        rows=[next(r for r in data['rows'] if r['design_name']==name and r['condition_id']==c) for c in conditions]
        for j,(row,target) in enumerate(zip(rows,targets)):
            verdict=row['verdict'] if row['model_valid'] else 'UNKNOWN'
            ax.add_patch(Rectangle((j-.47,i-.44),.94,.88,facecolor={'PASS':PASS,'FAIL':FAIL}.get(verdict,UNKNOWN),edgecolor='white'))
            ax.text(j,i-.12,verdict,ha='center',va='center',fontweight='bold',fontsize=11)
            ax.text(j,i+.18,f"RX {row['received']}/{target}",ha='center',va='center',fontsize=10,color='#272727')
    ax.set(xticks=range(3),xticklabels=['Capture / recovery','Repeated contact','Radio gap'],
           yticks=range(len(names)),yticklabels=labels,xlim=(-.5,2.5),ylim=(len(names)-.45,-.8))
    ax.tick_params(length=0,pad=10)
    ax.set_title('A  Fixed designs under the original three full-service gates',loc='left',pad=22,fontweight='bold')
    ax.spines[:].set_visible(False)
    note.text(0,.98,'Two legal success routes',va='top',fontweight='bold',fontsize=13)
    note.text(0,.88,'• Persistence + earlier startup\n  passes with holder off.\n\n• The saved G proposal passes\n  with its original full design.',va='top',linespacing=1.45)
    note.text(0,.58,'6 new complete inputs\n0 new model requests',va='top',fontweight='bold',color='#0F4D92')
    note.text(0,.46,textwrap.fill('Rows 1–6 reuse retained results. Rows 7–8 are the six new counterfactual executions. G proposed the numerical equivalent of the reference; this is a recovered proposal evaluation, not a new model episode.',40),va='top',fontsize=10,linespacing=1.5)
    note.text(0,.10,'Fixed design neighborhood only.\nNo global necessity claim.',va='top',fontsize=10,color='#4D4D4D')
    fig.subplots_adjust(left=.31,right=.98,bottom=.09,top=.91)
    export(fig,'fig1_fixed_design_counterfactuals')
    return data


def observed_counts(result):
    totals=Counter()
    for row in result['results']:
        acts=Counter(x.get('action') for x in row.get('facts',{}).get('activity',[]))
        totals.update(capture=acts['capture']+acts['sample'],save=acts['save_commit'],
                      tx=acts['wire_complete'],ack=acts['ack_commit'],
                      rx=row.get('public_check',{}).get('received_count',0))
    return dict(totals)


def paired_prefixes():
    data=load(OUT/'s0/stage2-result.json')
    fig=plt.figure(figsize=(14.6,9.6))
    gs=fig.add_gridspec(3,3,height_ratios=[1,1,.55],width_ratios=[1.5,2.0,1.3],hspace=.42,wspace=.35)
    axes=np.array([[fig.add_subplot(gs[i,j]) for j in range(3)] for i in range(2)])
    machine=[]
    for i,label in enumerate(('identity-progress','saved-undelivered')):
        prefix=load(OUT/'shared/prefixes'/f'{label}.json.gz')
        rows=[r for r in data['cells'] if r['prefix_id']==label]
        off,on=[next(r for r in rows if r['switch']==v) for v in ('off','on')]
        before=observed_counts(prefix['family_result'])
        after={r['switch']:observed_counts(load(r['result']['path'])) for r in rows}
        for ax in axes[i,:2]:ax.axis('off')
        title='Identity progress, service unfinished' if i==0 else 'Saved records, no completed wire frames'
        facts=('3 explicit identity conflicts cease to appear.\nRaw stage counts do not increase.\n\nCapture / SAVE / TX / RX / ACK\n7 / 7 / 7 / 7 / 7' if i==0 else
               'Capture / SAVE / TX / RX / ACK\n18 / 18 / 0 / 0 / 0\n\nSAVE→wire obligation remains pending.\nEnergy, eligibility and timing causes UNKNOWN.')
        axes[i,0].text(0,1,title,va='top',fontweight='bold',fontsize=12)
        axes[i,0].text(0,.79,facts,va='top',fontsize=10.5,linespacing=1.6)
        axes[i,1].text(0,1,'Same facts + common joint pool + seed',va='top',fontweight='bold',fontsize=12)
        onpatch=('ON: startup 3.2 → 1.9 V\nEarlier powered sampling; brownout risk remains.' if i==0 else
                 'ON: C 100 → 257 µF; ESR 49.81 → 0.1 Ω\nC ≥ Q / (Vgate − Vbrownout − reserve − ESR·I).\nStartup delay remains an explicit side effect.')
        axes[i,1].text(0,.80,onpatch,va='top',color=COLORS['on'],fontsize=10.5,linespacing=1.55)
        changes=', '.join(off['design_patch'])
        axes[i,1].text(0,.47,'OFF: general joint mutation selected\n'+textwrap.fill(changes,49),va='top',color=COLORS['off'],fontsize=10.3,linespacing=1.5)
        axes[i,1].text(0,.20,'Prediction before execution: full service UNKNOWN.\nThese are seen development prefixes.',va='top',fontsize=9.8,color='#4D4D4D',linespacing=1.5)
        ax=axes[i,2]
        vals=[after['off']['rx'],after['on']['rx']]
        bars=ax.bar([0,1],vals,color=[COLORS['off'],COLORS['on']],width=.55,edgecolor='black',linewidth=.7)
        ax.bar_label(bars,padding=4,fontsize=12)
        ax.set(xticks=[0,1],xticklabels=['OFF\n0/3 pass','ON\n3/3 pass'],ylim=(0,max(vals)*1.38+1),ylabel='Accepted RX, summed over 3 conditions')
        ax.set_title('Original complete consumer',fontweight='bold',fontsize=11,pad=13)
        ax.tick_params(axis='x',length=0)
        machine.append(dict(prefix_id=label,before=before,after=after,on_patch=on['design_patch'],off_patch=off['design_patch'],cells=rows))
    fig.text(.03,.985,'B  Public state → prospective action → full consequence',fontsize=14,fontweight='bold',va='top')
    closure=load(OUT/'s0/core-closure-gate.json')
    rail=fig.add_subplot(gs[2,:]);rail.axis('off')
    rail.text(0,1,'v2: actual source-bound component-duty expansion (static check)',va='top',fontweight='bold',fontsize=11.5)
    rail.text(0,.72,'Holder enabled\nCONSUMPTION = false',va='top',fontsize=10.5,color=COLORS['off'])
    rail.annotate('',xy=(.27,.51),xytext=(.20,.51),arrowprops=dict(arrowstyle='->',color='#555555',lw=1.5))
    rail.text(.28,.72,'Add holding_then_contact reader\nCONSUMPTION = true',va='top',fontsize=10.5,color=COLORS['on'])
    rail.annotate('',xy=(.61,.51),xytext=(.54,.51),arrowprops=dict(arrowstyle='->',color='#555555',lw=1.5))
    rail.text(.62,.72,'Optional siblings from capacity UNKNOWN\nearly: handoff false · SAVE / ACK: supported',va='top',fontsize=10.5)
    rail.text(0,.10,'Dynamic timing, energy and capacity remain UNKNOWN. The four selected prefix actions are unchanged numeric probes; no executed holder-closure benefit is established.',va='top',fontsize=9.4,color='#4D4D4D')
    fig.text(.03,.018,'Counts are raw operations / accepted records, not independent true events. 12 logical condition evaluations = 9 new + 3 exact reuses. Seen development prefixes.',fontsize=9.5,color='#4D4D4D')
    fig.subplots_adjust(left=.04,right=.98,top=.92,bottom=.07)
    export(fig,'fig2_paired_prefix_mechanism')
    return dict(prefixes=machine,static_closure=closure)


def consequence_summary(result):
    """Retained consumer facts only; no regenerated simulation or cost model."""
    rows=[]
    for member in result['results']:
        facts=member.get('facts',{})
        operations=Counter(x.get('action') for x in facts.get('activity',[]))
        rows.append(dict(condition_id=member.get('condition_id',member['task_id']),
            model_valid=member['model_valid'],public_check=member['public_check'],
            energy_j=facts.get('energy',{}),operation_counts=dict(operations),
            minimum_tx_terminal_v=facts.get('minimum_tx_terminal_v'),
            peak_handle_force_n=facts.get('peak_handle_force_n'),
            source=ref(member['canonical_public_path']) if member.get('canonical_public_path') else None))
    return rows


def comparison():
    path=OUT/'s0/stage3-result.json'
    fig=plt.figure(figsize=(14.2,5.5))
    if not path.exists():
        ax=fig.add_subplot();ax.axis('off')
        ax.text(.05,.87,'C  Fair comparison not dispatched',fontweight='bold',fontsize=19)
        ax.text(.05,.65,'No first-PASS curve can be estimated without admitted trajectories.',fontsize=14)
        ax.text(.05,.45,'The candidate-duty closure gate and finite stop reason are reported in the final receipt.\nNo unrun trajectory is plotted as a scientific failure.',fontsize=12,linespacing=1.7)
        export(fig,'fig3_budget_and_complexity')
        return dict(status='NOT_RUN',curves=[])
    data=load(path)
    gs=fig.add_gridspec(1,3,width_ratios=[1,1,1.2],wspace=.35)
    curves=[]
    method_labels={'G':'G: strong model','D':'D: joint / archive','R':'R: relations'}
    for i,family in enumerate(('DOOR','LC')):
        ax=fig.add_subplot(gs[i])
        for method in ('G','D','R'):
            rows=[r for r in data['trajectories'] if r['family']==family and r['condition']==method]
            xs=list(range(7))
            ys=[sum(r['first_all_service_PASS_design_slot'] is not None and r['first_all_service_PASS_design_slot']<=x for r in rows)/2 for x in xs]
            incomplete=sum(r['status']!='COMPLETE' for r in rows)
            ax.step(xs,ys,where='post',lw=2.2,color=COLORS[method],label=method_labels[method],linestyle={'G':'-','D':'--','R':':'}[method])
            ax.scatter([6],[ys[-1]],color=COLORS[method],s=25,marker={'G':'o','D':'s','R':'D'}[method])
            curves.append(dict(family=family,method=method,design_slots=xs,observed_success_fraction=ys,denominator=2,operational_incomplete=incomplete))
        ax.set(xlim=(-.1,6.2),ylim=(-.04,1.06),xticks=range(7),yticks=[0,.5,1],xlabel='New design evaluations (initial excluded)',ylabel='Observed all-service PASS / 2 seeds',title=family)
        secondary=ax.secondary_xaxis('top',functions=(lambda x:x*3,lambda x:x/3))
        secondary.set_xticks([0,3,6,9,12,15,18]);secondary.set_xlabel('Logical complete-condition evaluations')
        ax.grid(axis='y',alpha=.16)
    handles,labels=ax.get_legend_handles_labels()
    fig.legend(handles,labels,loc='upper left',bbox_to_anchor=(.04,.0),ncol=3,fontsize=10)
    table=fig.add_subplot(gs[2]);table.axis('off')
    table.text(0,1,'Unweighted design changes',va='top',fontweight='bold',fontsize=12)
    cells=[]
    outcomes=[]
    for r in data['trajectories']:
        c=r.get('final_complexity')
        n='—' if c is None else str(c['changed_field_count'])
        extra='—' if c is None else str(len(c['added_components']))
        final_design=r['final']['design'] if r.get('final') else None
        initial=load(OUT/'s0/initial'/f'{r["family"]}.json.gz')
        c_ratio='—' if final_design is None else f'{final_design["capacitance_f"]/initial["design"]["capacitance_f"]:.2g}'
        cells.append([r['family']+' '+r['condition'],str(r['seed']),n,extra,c_ratio])
        final_entry=next((h for h in r['history'] if h['design']==final_design),None)
        selected=load(final_entry['result']['path']) if final_entry else initial if final_design==initial['design'] else None
        outcomes.append(dict(ident=r['ident'],final_design=final_design,
            final_complexity=c,capacitance_ratio=None if final_design is None else final_design['capacitance_f']/initial['design']['capacitance_f'],
            pv_area_ratio=None if final_design is None or 'area_cm2' not in final_design else final_design['area_cm2']/initial['design']['area_cm2'],
            initial=consequence_summary(initial),final=consequence_summary(selected) if selected else None))
    t=table.table(cellText=cells,colLabels=['Group','Seed','Fields','+parts','C / init'],loc='upper center',bbox=[0,.16,1,.73],cellLoc='center')
    t.auto_set_font_size(False);t.set_fontsize(8.5)
    for key,cell in t.get_celld().items():
        cell.set_edgecolor('#DDDDDD');cell.set_linewidth(.5)
        if key[0]==0:cell.set_facecolor('#EFEFEF');cell.set_text_props(fontweight='bold')
    table.text(0,.10,'Full parameter/program deltas, PV area,\ncapacitance, energy and control outcomes\nare in plot-data.json and trajectory receipts.',va='top',fontsize=9,color='#4D4D4D',linespacing=1.5)
    fig.suptitle('C  First complete service under the same logical scientific budget',x=.03,ha='left',fontsize=14,fontweight='bold',y=1.02)
    fig.text(.03,-.09,f"Exact cache hits consume the same logical slots. {data['completed']}/12 trajectories complete; {data['operational_incomplete']}/12 operationally incomplete. Two seeds per family/method; no significance claim. Model fees are reported separately.",fontsize=9.2,color='#4D4D4D')
    fig.subplots_adjust(left=.06,right=.99,bottom=.12,top=.81)
    export(fig,'fig3_budget_and_complexity')
    return dict(curves=curves,trajectories=data['trajectories'],consequences=outcomes)


def run():
    a=counterfactuals();b=paired_prefixes();c=comparison()
    save(HERE/'plot-data.json',dict(figure1=a,figure2=b,figure3=c,
        sources=[ref(OUT/'a/FIXED-NEIGHBORHOOD-MATRIX.json'),ref(OUT/'s0/stage2-result.json'),ref(OUT/'s0/core-closure-gate.json')]+([ref(OUT/'s0/stage3-result.json')] if (OUT/'s0/stage3-result.json').exists() else []),
        script=ref(Path(__file__)),new_science=0,new_provider=0,
        metadata_interpretation=ref(OUT/'s0/metadata-errata.json')))


if __name__=='__main__':run()
