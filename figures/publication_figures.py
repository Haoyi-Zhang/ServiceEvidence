"""Evidence-plane illustrations and retained system measurements."""
from pathlib import Path
import csv
import json
import statistics
import gzip
from zipfile import ZipFile
from fractions import Fraction

from figure_style import (AMBER, BLUE, INK, LIGHT, MINT, MUTED, RULE, SAND, SERIES, TEAL,
                          Plate, arguments, grid, paper_style, plot, plt, save)

HERE=Path(__file__).resolve().parent
RESULTS=HERE/'../results'

def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))

def epochs(out,preview):
    from diagram_ink import emit
    emit('epoch-split',out,preview)

def pipeline(out,preview):
    from diagram_ink import emit
    emit('evidence-pipeline',out,preview)

def veto(out,preview):
    from diagram_ink import emit
    emit('negative-safe-view',out,preview)

def lower(out,preview):
    from diagram_ink import emit
    emit('merge-only-boundary',out,preview)

def recovery(out,preview):
    from diagram_ink import emit
    emit('recovery-boundary',out,preview)

def speed(out,preview):
    from matplotlib.lines import Line2D
    rr=rows(RESULTS/'tpds/materializer_summary.csv')
    xs=[64,128,256,512]
    f=plt.figure(figsize=(252/72,133.2/72))
    a=f.add_axes([.17,.235,.342,.46])
    b=f.add_axes([.650,.235,.32,.46])
    family=[('sparse_cut','Sparse cut'),('dense_cut','Dense cut'),('low_conflict','Low conflict')]
    looks=[(c,m,ls,ms,filled) for (c,m,ls),ms,filled in
           zip(SERIES,(3.7,4.65,2.75),(False,False,True))]
    for i,((k,label),(c,m,ls,ms,filled)) in enumerate(zip(family,looks)):
        ys=[]
        for x in xs:
            value=[float(r['paired_speedup_median']) for r in rr if r['family']==k and int(r['handles'])==x]
            assert len(value)==1,(x,k)
            ys.extend(value)
        (a if i==0 else b).plot(xs,ys,color=c,marker=m,ls=ls,ms=ms,mew=.66,
                              lw=.74,mfc=c if filled else 'white',label=label,zorder=3+i)
    for ax,title,lo,hi,ticks in [(a,'(a) Sparse cut',.88,2.85,(1,2)),
                                 (b,'(b) Near parity',.88,1.155,(.9,1,1.1))]:
        ax.set(xscale='log',xlim=(57,579),xticks=xs,xticklabels=xs,ylim=(lo,hi),yticks=ticks)
        ax.set_yticklabels([f'{t:g}' for t in ticks])
        ax.axhline(1,color=MUTED,ls=':',lw=.5,zorder=2)
        ax.set_title(title,loc='left',pad=4,fontsize=9.3)
        ax.minorticks_off()
        ax.tick_params(axis='both',labelsize=9,length=2.1)
        grid(ax)
    a.set_ylabel('Scanning / indexed time',fontsize=8.8)
    f.text(.58,.05,'Handles',ha='center',fontsize=9)
    f.legend(handles=[Line2D([],[],color=c,marker=m,ls=ls,ms=ms,
                           mfc=c if filled else 'white',mew=.66,lw=.74,label=label)
                      for (_,label),(c,m,ls,ms,filled) in zip(family,looks)],
             ncol=3,loc='upper center',bbox_to_anchor=(.53,.985),fontsize=8.8,handlelength=1.42,columnspacing=.72)
    save(f,out,'index-speedup-native',preview)

def sparsity(out,preview):
    groups={}
    for r in rows(RESULTS/'correctness.csv'):
        if r['method']!='sealed-evidence q=2':continue
        x=100*float(r['trial'].split(';',1)[0].split('=',1)[1])
        groups.setdefault(x,[]).append(r)
    xs=sorted(groups);assert xs==[0,8,20]
    f,a=plot(252,136.06,left=45,bottom=32,top=23)
    for i,(k,label,(c,m,ls)) in enumerate(zip(['false_merge_rate','false_split_rate'],['False merge','False split'],SERIES)):
        a.plot(xs,[100*statistics.mean(float(r[k]) for r in groups[x]) for x in xs],
               color=c,ls=ls,marker=m if i==0 else 'D',ms=6.1 if i==0 else 2.4,mew=.68,lw=.75,
               mfc='white' if i==0 else c,label=label,zorder=3+i)
    a.set(xticks=xs,ylim=(-2.1,32),xlabel='True edges with sparse evidence (%)',ylabel='Pairwise error (%)')
    a.legend(ncol=2,loc='lower left',bbox_to_anchor=(0,1.02),fontsize=8.7)
    grid(a);save(f,out,'sparsity-native',preview)

def sealing(out,preview):
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    s={r['schedule']:r for r in rows(RESULTS/'unsealed_safety.csv')}
    rr=[s['uniform random delivery order'],s['adversarial same-votes first']]
    f,a=plot(252,136.06,left=57,bottom=31,top=27,right=62)
    for j,(key,label,c,hatch) in enumerate([('unsealed_transient_false_merges','Unsealed',AMBER,'//'),
                                           ('sealed_transient_false_merges','Sealed',TEAL,'')]):
        vals=[100*int(r[key])/int(r['trials']) for r in rr]
        pos=[1+(.15 if not j else -.15),(.15 if not j else -.15)]
        a.barh(pos,vals,height=.24,color=c,edgecolor=INK,linewidth=.4,hatch=hatch,label=label)
        for y,x,r in zip(pos,vals,rr):
            if not x:a.plot(0,y,marker='o',ms=4.3,mfc='white',mec=TEAL,mew=.85,zorder=5)
            a.text(1.035,y,f"{int(r[key]):,}/{int(r['trials']):,}",
                   transform=a.get_yaxis_transform(),va='center',ha='left',
                   color=INK,fontsize=8)
    a.set(xlim=(-4,101),ylim=(-.43,1.43),xticks=(0,25,50,75,100),
          yticks=(1,0),yticklabels=['Random order','Positive first'],xlabel='Trials with a transient false merge (%)')
    a.tick_params(axis='y',length=0)
    a.legend(handles=[Patch(facecolor=AMBER,edgecolor=INK,hatch='//',label='Unsealed'),
                      Line2D([],[],marker='o',mfc='white',mec=TEAL,ms=4.3,mew=.85,
                             linestyle='none',label='Sealed')],
             ncol=2,loc='lower left',bbox_to_anchor=(0,1.01),fontsize=8.5)
    grid(a,'x');save(f,out,'sealing-native',preview)

def compaction(out,preview):
    rr=sorted(rows(RESULTS/'compaction.csv'),key=lambda r:int(r['epochs']))
    xs=[int(r['epochs']) for r in rr];assert xs==[2,4,6]
    f,a=plot(252,136.06,left=47,bottom=31,top=23)
    for (key,label),(c,m,ls) in zip([('cells_before','Before'),('cells_after','After compaction')],SERIES):
        a.plot(xs,[int(r[key])/1000 for r in rr],color=c,ls=ls,marker=m,ms=3.6,mew=.58,
               lw=.76,mfc='white',label=label)
    a.set(xticks=xs,ylim=(0,50),xlabel='Complete epochs before compaction',ylabel='Retained cells (thousands)')
    a.legend(ncol=2,loc='lower left',bbox_to_anchor=(0,1.02),fontsize=8.7)
    grid(a);save(f,out,'compaction-native',preview)

def partition_response(out,preview):
    rr=rows(RESULTS/'tpds/topology_cases.csv')
    s=json.loads((RESULTS/'tpds/topology_summary.json').read_text(encoding='utf8'))
    assert len(rr)==s['placement_cases']==2550
    assert len({r['partition'] for r in rr})==s['nonconnected_partitions']==51
    groups=[rr,[r for r in rr if r['components']=='2']]
    vals=[]
    for group in groups:
        n=sum(int(r['query_sites']) for r in group)
        v=[Fraction(sum(int(r[k+'_responding_sites']) for r in group),n) for k in ('central','quorum','peer')]
        vals.append(v)
    assert vals==[[Fraction(107,255),Fraction(92,255),Fraction(1)],
                  [Fraction(43,75),Fraction(47,75),Fraction(1)]]
    fig,a=plot(250,104,left=77,right=15,bottom=32,top=20)
    for j,(label,color,shape,dy) in enumerate([('Central',BLUE,'o',.17),('Quorum',AMBER,'s',-.17)]):
        xx=[100*float(v[j]) for v in vals]
        a.scatter(xx,[1+dy,dy],c=color,marker=shape,s=15,label=label,zorder=4)
        for x,y in zip(xx,[1+dy,dy]):
            a.annotate(f'{x:.1f}',(x,y),xytext=(5,0),textcoords='offset points',
                       fontsize=8.3,va='center',color=color)
    for y,v in zip([1,0],vals):
        a.hlines(y,*sorted([100*float(x) for x in v[:2]]),color=RULE,linewidth=.8,zorder=1)
    a.set(xlim=(0,83),ylim=(-.42,1.43),xticks=(0,20,40,60,80),yticks=(1,0),
          yticklabels=('All 51 partitions','15 two-block cuts'),xlabel='Mean responding-site share (%)')
    a.tick_params(axis='y',length=0)
    a.legend(ncol=2,loc='lower left',bbox_to_anchor=(0,1.03),fontsize=8.5)
    grid(a,'x');save(fig,out,'partition-response',preview)

def workflow_pairs(out,preview):
    from matplotlib.lines import Line2D
    data=RESULTS/'durable-mws-linux'
    verified=json.loads((data/'verified-summary.json').read_text(encoding='utf8'))
    assert verified['cases']==36 and verified['query_checks']==540
    arms=('scanning','indexed','mws_small_table')
    families=('sparse_cut','dense_cut','low_conflict')
    observed={}
    for family in families:
        for seed in (1,2):
            for arm in arms:
                with gzip.open(data/f'{family}-128-{seed}-{arm}.json.gz','rt',encoding='utf8') as f:
                    row=json.load(f)['row']
                assert (row['family'],row['handles'],row['seed'],row['implementation'])==(family,128,seed,arm)
                assert row['workflow_ns']>0
                observed[family,seed,arm]=row['workflow_ns']
    for row in verified['costs_128_handles']:
        pair=[observed[row['family'],seed,row['implementation']]/1e6 for seed in (1,2)]
        assert round(statistics.median(pair),3)==row['median_workflow_ms']
    f,a=plot(250,106,left=66,bottom=30,top=22,right=13)
    a.axvline(0,color=MUTED,ls=':',lw=.9,zorder=1)
    styles=[('indexed','Indexed',BLUE,'o',.17,'-'),
            ('mws_small_table','Corrected MWS',AMBER,'s',-.17,'--')]
    for arm,title,col,marker,dy,ls in styles:
        for j,family in enumerate(families):
            yy=2-j+dy
            x=[100*(observed[family,s,arm]/observed[family,s,'scanning']-1) for s in (1,2)]
            assert all(-20<v<10 for v in x)
            a.hlines(yy,*sorted(x),color=col,linewidth=.8,linestyle=ls)
            a.plot(x,[yy,yy],linestyle='none',marker=marker,ms=3.3,mew=.67,
                   mfc='white',color=col,label=title if j==0 else None)
    a.set(xlim=(-20,10),ylim=(-.43,2.43),xticks=(-20,-10,0,10),yticks=(2,1,0),
          yticklabels=('Sparse cut','Dense cut','Low conflict'),xlabel='Workflow time change vs. scanning (%)')
    a.tick_params(axis='y',length=0)
    a.legend(handles=[Line2D([],[],color=col,lw=.8,ls=ls,marker=marker,
                      ms=3.3,mew=.67,mfc='white',label=title)
                      for _,title,col,marker,_,ls in styles],
             ncol=2,loc='lower left',bbox_to_anchor=(0,1.02),fontsize=9)
    grid(a,'x');save(f,out,'workflow-pairs',preview)

if __name__=='__main__':
    args=arguments();paper_style('tpds')
    for draw in (epochs,pipeline,veto,lower,recovery,speed,sparsity,sealing,compaction,partition_response,workflow_pairs):draw(args.outdir,args.previews)
    from diagram_ink import emit_supplemental
    emit_supplemental(args.outdir,args.previews)
