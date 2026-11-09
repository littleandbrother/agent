"""Small source-bound figure; raw repeats, no inferential error bars."""
from common import *


def run():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    table=load(OUT/'trajectory-table.json')
    validity=load(HERE/'comparison-validity.json')
    rows=[{k:r[k] for k in ('family','condition','repeat','calls','first_pass','final_design','status')} for r in table]
    rejected=validity['rejected_callbacks'];denied={}
    for event in rejected:
        family=event['episode'].split('-',1)[0]
        condition=event['episode'].rsplit('-',1)[0].split('-',1)[1]
        denied[family,condition]=denied.get((family,condition),0)+event['tool_names'].count('calculate')
    save(OUT/'figures/summary-data.json',dict(source=ref(OUT/'trajectory-table.json'),validity=ref(HERE/'comparison-validity.json'),rows=rows,
        denied_calculate=[dict(family=k[0],condition=k[1],count=v) for k,v in denied.items()],
        scope='Execution facts only. Common calculator access was blocked; no matched-tool or independent seed inference.'))
    plt.rcParams.update({'font.family':['Arial','Helvetica','DejaVu Sans','sans-serif'],'font.size':11,
        'axes.spines.right':False,'axes.spines.top':False,'axes.linewidth':1.4,'legend.frameon':False,
        'svg.fonttype':'none','pdf.fonttype':42})
    fig,axes=plt.subplots(1,2,figsize=(11,4.5))
    groups=[(family,condition) for family in ('DOOR','LC') for condition in ('G','G+J','G+J+C')]
    palette={'G':'#767676','G+J':'#42949E','G+J+C':'#0F4D92'}
    for r in rows:
        x=groups.index((r['family'],r['condition']))+(-.1 if r['repeat']==314159 else .1)
        marker='o' if r['repeat']==314159 else 's';color=palette[r['condition']]
        axes[0].scatter(x,r['calls'],s=65,marker=marker,color=color,edgecolors='black',linewidths=.6,zorder=3)
    labels=[f'{f}\n{c}' for f,c in groups]
    for ax in axes:
        ax.set_xticks(range(6),labels);ax.set_xlim(-.5,5.5)
        ax.axvline(2.5,color='#CFCECE',linewidth=1)
    axes[0].set(title='Actual model requests',ylabel='Requests per trajectory',ylim=(0,max([r['calls'] for r in rows] or [1])+1))
    for x,(family,condition) in enumerate(groups):
        count=denied.get((family,condition),0)
        axes[1].bar(x,count,width=.52,color=palette[condition],edgecolor='black',linewidth=.7)
        axes[1].text(x,count+.12,str(count),ha='center',fontsize=10)
    axes[1].set(title='Local parser denied calculator access',ylabel='Unexecuted calculate calls',ylim=(0,5))
    legend=[Line2D([0],[0],marker=m,color='none',markerfacecolor='#767676',markeredgecolor='black',label=str(rep),markersize=7)
        for rep,m in ((314159,'o'),(271828,'s'))]
    fig.legend(handles=legend,loc='upper center',bbox_to_anchor=(.5,.9),ncol=2)
    fig.suptitle('Execution record: common-calculator interface blocked',fontsize=16,y=.98)
    fig.text(.5,.01,'4 settled replies rejected locally · 6 calculate calls never dispatched\nService PASS remains an execution fact; matched-tool comparison is invalid',ha='center',fontsize=9,color='#B64342')
    fig.tight_layout(rect=(0,.06,1,.83),pad=1.3)
    for suffix in ('pdf','svg','png'):fig.savefig(OUT/'figures'/f'comparison-summary.{suffix}',dpi=300,facecolor='white')
    plt.close(fig)
    print(json.dumps(dict(event='FIGURE',rows=len(rows),artifacts=[str(OUT/'figures'/f'comparison-summary.{s}') for s in ('pdf','svg','png')])),flush=True)


if __name__=='__main__':run()
