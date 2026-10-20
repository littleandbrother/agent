#!/usr/bin/env python3
"""Render paper PDF figures from saved views; no scientific execution."""
from pathlib import Path
import csv
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

ROOT = Path(__file__).resolve().parent
DATA, OUT = ROOT/"data", ROOT/"figures"
OUT.mkdir(exist_ok=True)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7.5,
    "pdf.fonttype": 42, "svg.fonttype": "none", "axes.spines.top": False,
    "axes.spines.right": False, "axes.linewidth": .6, "xtick.major.width": .6,
    "ytick.major.width": .6, "axes.labelsize": 7.5, "legend.frameon": False})
BLUE, ORANGE, GREY, INK = "#356BA1", "#C5773A", "#B6BDC6", "#263746"


def save(fig, name):
    fig.savefig(OUT/(name+".pdf"), metadata={"Title": name, "Creator": "Saved-data Matplotlib figure; no simulation"})
    plt.close(fig)


def chain():
    fig, ax = plt.subplots(figsize=(6.5, 1.6))
    fig.subplots_adjust(left=.01, right=.99, top=.98, bottom=.04)
    ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis("off")
    positions = [(x, y) for y in (.57, .08) for x in (.01, .35, .69)]
    labels = ["Acquire source\nidentity, values, registered units", "Propose qualified relation\nsource + field + domain", "Deterministic preflight\nLEGAL or exact-field rejection",
              "Independent service judgment\nprediction, decision, service", "Execute immutable full input\ninput hash + execution identity", "Consume typed observation\nexplicit branch + bound input edge"]
    for (x,y), label in zip(positions, labels):
        ax.add_patch(FancyBboxPatch((x,y), .29,.30, boxstyle="round,pad=.009,rounding_size=.025", linewidth=.8, edgecolor=BLUE, facecolor="white"))
        ax.text(x+.145,y+.15,label,ha="center",va="center",fontsize=7.1,color=INK,linespacing=1.5)
    for a,b in [((.31,.72),(.34,.72)),((.65,.72),(.68,.72)),((.835,.56),(.835,.40)),((.68,.23),(.65,.23)),((.34,.23),(.31,.23))]:
        ax.add_patch(FancyArrowPatch(a,b,arrowstyle="-|>",mutation_scale=9,linewidth=.8,color=BLUE))
    ax.text(.01,.46,"Participant facts and actions",fontsize=6.8,color=INK)
    ax.text(.48,.46,"Final judgment remains host-only",fontsize=6.8,color=INK)
    save(fig,"consumer-chain")


def mechanisms():
    source = json.loads((DATA/"mechanisms.json").read_text())
    traces = {}
    with (DATA/"saved-traces.csv").open() as f:
        for row in csv.DictReader(f):
            traces.setdefault(row["execution_key"], []).append((float(row["time_s"])*1000,float(row["voltage_v"])))
    fig, axes = plt.subplots(1, 3, figsize=(6.5, 2.95), sharey=True)
    fig.subplots_adjust(left=.075,right=.99,bottom=.18,top=.75,wspace=.18)
    names = ["storage-connection", "reset-placement", "package-response"]
    titles = ["a  Storage connection", "b  Reset placement", "c  Package response"]
    subtitles = ["22 → 5.5 µF; 0.3 → 1.2 Ω", "40 µJ shunt: 80 → 12 ms", "150 µJ: [0,20] → [70,110] ms"]
    for i,(ax,name) in enumerate(zip(axes,names)):
        m = source[name]
        for decision,color,style in [("retain",BLUE,"-"),("adopt",ORANGE,"--")]:
            role=m["roles"][decision]; v=np.asarray(traces[role["execution_key"]])
            ax.plot(v[:,0],v[:,1],color=color,lw=1.1,ls=style,label=decision.capitalize(),zorder=3)
            for a in role["activity"]:
                if a["action"] == "brownout" and a["time_s"] <= .11:
                    t=a["time_s"]*1000; j=int(np.argmin(abs(v[:,0]-t)))
                    ax.scatter([t],[v[j,1]],marker="x",s=18,color=color,lw=.8,zorder=5)
            rx=role["reference"]["first_receive_s"]
            if rx is not None:
                j=int(np.argmin(abs(v[:,0]-rx*1000)))
                ax.scatter([rx*1000],[v[j,1]],marker="v",s=24,color=color,zorder=6)
        ax.axhline(2.8,color="#7C8791",ls=":",lw=.65,zorder=1)
        ax.axhline(1.8,color="#7C8791",ls=":",lw=.65,zorder=1)
        ax.axvline(100,color="#7C8791",ls="-.",lw=.65,zorder=1)
        ax.set(xlim=(0,112),ylim=(0,3.6),xticks=[0,50,100],xlabel="Time (ms)")
        ax.tick_params(labelsize=7,length=2.5)
        ax.set_title(titles[i],loc="left",fontweight="bold",fontsize=8.4,pad=31)
        ax.text(0,1.08,subtitles[i],transform=ax.transAxes,fontsize=6.8,color=INK)
        if i==0:
            ax.set_ylabel("Saved capacitor voltage (V)")
            ax.text(40,3.13,"Retain: RX 15.8 ms",color=BLUE,fontsize=6.6)
            ax.text(24,.53,"Adopt: 4 TX resets",color=ORANGE,fontsize=6.6)
        elif i==1:
            ax.axvspan(0,8,color="#DCE1E6",alpha=.55,zorder=0)
            ax.text(41,3.13,"Retain: RX 46.9 ms",color=BLUE,fontsize=6.6)
            ax.text(15,.53,"Adopt: event cleared",color=ORANGE,fontsize=6.6)
        else:
            ax.axvspan(0,20,ymin=0,ymax=.04,color=BLUE,alpha=.55)
            ax.axvspan(70,110,ymin=0,ymax=.04,color=ORANGE,alpha=.55)
            ax.text(23,3.13,"Retain: RX 15.8 ms",color=BLUE,fontsize=6.6)
            ax.text(26,.53,"Adopt: RX 98.7 ms",color=ORANGE,fontsize=6.6)
    save(fig,"mechanism-traces")


def costs():
    stats=json.loads((DATA/"aggregate.json").read_text())["B"]
    arms=["complete_information","fixed_rule","observation_refinement"]
    names=["Complete","Fixed","Refine"]
    fig,axes=plt.subplots(1,3,figsize=(6.5,2.7))
    fig.subplots_adjust(left=.09,right=.99,bottom=.25,top=.78,wspace=.60)
    a,b,c=axes
    typed=np.array([stats[k]["real_typed_consumer"] for k in arms]); direct=6-typed
    y=np.arange(3)
    a.barh(y,typed,height=.48,color=BLUE,label="Typed")
    a.barh(y,direct,left=typed,height=.48,color="#D6DBE1",label="Direct")
    a.barh([1],[2],left=[4],height=.48,facecolor="none",edgecolor="#6D7680",hatch="///",lw=.5)
    for n,(t,d) in enumerate(zip(typed,direct)):
        a.text(t/2,n,str(t),color="white",ha="center",va="center",fontsize=7)
        a.text(t+d/2,n,str(d),color=INK,ha="center",va="center",fontsize=7)
    a.set(yticks=y,yticklabels=names,xlim=(0,6.15),xticks=[0,2,4,6],xlabel="Actual submissions (n=6)")
    a.invert_yaxis();a.set_title("a  Decision paths",loc="left",fontsize=8.3,fontweight="bold",pad=26)
    a.legend(loc="lower left",bbox_to_anchor=(-.02,1.02),ncol=2,fontsize=6.5,handlelength=1,columnspacing=.7)
    x=np.arange(3)
    for delta,key,color,label in [(-.24,"requests",BLUE,"Requests"),(0,"preflight_calls",GREY,"Preflight"),(.24,"rejected_actions",ORANGE,"Rejects")]:
        v=[stats[k][key] for k in arms];b.bar(x+delta,v,width=.23,color=color,label=label)
        for j,n in enumerate(v):b.text(j+delta,n+1,str(n),ha="center",va="bottom",fontsize=6.2)
    b.set(xticks=x,xticklabels=names,ylim=(0,67),ylabel="Count")
    b.set_title("b  Operational demand",loc="left",fontsize=8.3,fontweight="bold",pad=26)
    b.legend(loc="lower left",bbox_to_anchor=(-.08,1.0),fontsize=6.1,ncol=2,handlelength=1,columnspacing=.7)
    values=[stats[k]["charge_upper_usd"] for k in arms]
    c.bar(x,values,color=[GREY,"#CAD1D8",BLUE],width=.60)
    for j,v in enumerate(values):c.text(j,v+.022,f"{v:.3f}",ha="center",fontsize=7)
    c.set(xticks=x,xticklabels=names,ylim=(0,.98),ylabel="Estimated USD")
    c.set_title("c  Fixed-rate estimate",loc="left",fontsize=8.3,fontweight="bold",pad=26)
    c.text(0,1.045,"Not invoice amounts",transform=c.transAxes,fontsize=6.5,color=INK)
    for ax in axes:ax.tick_params(labelsize=6.8,length=2.5)
    save(fig,"cost-paths")


if __name__ == "__main__":
    chain();mechanisms();costs()
