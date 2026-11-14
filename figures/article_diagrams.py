"""Replicated evidence, merge decisions, and recovery boundaries."""
import json
from pathlib import Path
from zipfile import ZipFile
from diagram_ink import Diagram,S,T,A,K,G,F,L,P,O
from matplotlib.patches import FancyBboxPatch


def epoch_split():
    d=Diagram(252,97)
    d.tag(13,85,'Evidence at seal')
    d.tag(181,85,'View')
    for y,ep,late in ((62,r'$e_0$',False),(30,r'$e_1$',True)):
        d.txt(21,y,ep,9.8)
        for x,n in zip((53,88,126),'abc'):
            d.dotmark(x,y,6,c=T)
            d.node_label(x,y,n,9.1)
        d.wire((61,y),(80,y),c=T,arrow=False)
        d.wire((96,y),(118,y),c=A if late else T,dash=late,arrow=False)
        if late:
            d.mark('reject',107,y,10,A)
        d.wire((141,y),(169,y),c=G)
        d.txt(208,y,r'$\{a,b\}\mid\{c\}$' if late else r'$\{a,b,c\}$',9.6,color=T)
    d.mark('reject',69,9,9,A)
    d.txt(81,9,'Negative cell',8.7,ha='left',color=A)
    return d


def evidence_pipeline():
    d=Diagram(242,153)
    d.tag(9,141,'Retained cells')
    d.tag(129,141,'View at each read')
    for y,k in ((69,1),(35,2)):
        d.mark('replica',18,y,15,S)
        d.txt(31,y,rf'$C_{k},F_{k}$',9.4,ha='left',color=S)
        d.wire((57,y),(72,52),c=S,arrow=False)
    d.dotmark(79,52,6,c=T,fill=P)
    d.node_label(79,52,r'$\vee$',10,color=T)
    d.wire((87,52),(102,52),c=T)
    d.diamond(112,52,6,c=T)
    d.wire((120,52),(128,52),c=T)
    d.txt(55,15,r'$F^*=\max(F_1,F_2)$',8.6,color=G)
    d.txt(111,76,'Seal gate',8.7,color=T)
    d.wire((112,45),(112,24),(124,24),c=G,dash=True)
    d.txt(125,16,r'Keep $e_0$ if incomplete',8.5,ha='left',color=G)
    d.txt(47,119,'Earlier read',8.5,color=G)
    d.mark('array',71,110,12,G)
    d.wire((80,110),(128,110),c=G,dash=True)
    for y,e,late in ((110,0,False),(52,1,True)):
        d.ax.add_patch(FancyBboxPatch((130,y-10),101,20,
                      boxstyle='round,pad=0,rounding_size=3',edgecolor=F,
                      facecolor='none',lw=.72,zorder=3))
        d.txt(178,y+16,rf'Latest seal $e_{e}$',8.6)
        for x,n in zip((145,179,214),'abc'):
            d.dotmark(x,y,6.6,c=T)
            d.node_label(x,y,n,9.5)
        d.wire((153,y),(171,y),c=T,arrow=False)
        if late:
            d.wire((187,y),(205,y),c=A,dash=True,arrow=False)
            d.mark('reject',196,y,10,A)
        else:
            d.wire((187,y),(205,y),c=T,arrow=False)
        d.txt(180,y-17,r'$\{a,b\}\mid\{c\}$' if late else r'$\{a,b,c\}$',9.8,color=T)
    d.mark('reject',17,96,8,A)
    d.txt(25,96,'Negative cell',8.4,ha='left',color=A)
    return d


def negative_safe_view():
    d=Diagram(237,126)
    d.tag(11,115,'Existing component and proposed union')
    d.zone(11,44,96,29,c=T,fill='none',dash=False)
    for x,n,c in ((29,'a',T),(88,'b',T),(207,'c',S)):
        d.dotmark(x,59,7,c=c)
        d.node_label(x,59,n,10)
    d.wire((37,59),(80,59),c=T,arrow=False)
    d.wire((96,59),(199,59),c=S,dash=True,arrow=False)
    d.wire((30,67),(45,95),(186,95),(205,67),c=A,arrow=False)
    d.txt(117,104,r'$(a,c)$ hard negative',9.1,color=A)
    d.txt(146,48,r'$(b,c)$ proposed',9.0,color=S)
    d.mark('reject',43,20,12,A)
    d.txt(56,20,r'Keep $\{a,b\}$ and $\{c\}$ separate',9.2,ha='left',color=A)
    return d


def recovery_boundary():
    with ZipFile(Path(__file__).resolve().parents[1]/'results/process-cutpoints-evidence.zip') as q:
        summary=json.loads(q.read('summary.json'))
        cut=json.loads(q.read('protocol.json'))['matrix']['cutpoints']
    assert cut==['before_write','mid_write_prefix_flushed','before_file_fsync',
                 'after_file_fsync','before_replace','after_replace',
                 'before_directory_fsync','after_directory_fsync','after_dispatch_ack']
    assert summary['actual_SIGKILL_cases']==54 and summary['passed']==59
    assert all(sum(r['cut']==c for r in summary['rows'])==6 for c in cut)
    d=Diagram(240,83)
    d.txt(62,68,'Old / absent',9.0,color=S)
    d.txt(176,68,'New snapshot',9.0,color=T)
    d.wire((12,53),(12,58),(117,58),(117,53),c=S,arrow=False)
    d.wire((135,53),(135,58),(225,58),(225,53),c=T,arrow=False)
    for j in range(9):
        x=17+j*25.5
        y=39
        if j:
            d.wire((x-19,y),(x-7,y),c=G,arrow=False,lw=.56)
        if j<5:
            d.dotmark(x,y,5.6,c=S)
        else:
            d.zone(x-5.5,y-5.5,11,11,c=T,dash=False)
        d.node_label(x,y,str(j+1),8.1)
    for mid,label in [(2.5,'File fsync'),(4.5,'Replace'),(6.5,'Dir. fsync')]:
        x=17+mid*25.5
        d.wire((x,32),(x,22),c=A,dash=True,arrow=False)
        d.txt(x,12,label,8.8,color=A)
    return d


def merge_only_boundary():
    d=Diagram(226,101)
    d.txt(40,89,'Sealed epoch 0',9.2)
    d.txt(166,89,'After a negative seal',9.2)
    for x,n in ((25,'a'),(56,'b')):
        d.dotmark(x,51,6,c=S)
        d.node_label(x,51,n,9.1)
    d.wire((33,51),(48,51),c=S,arrow=False)
    d.wire((64,51),(84,51),c=G,arrow=False)
    d.dotmark(84,51,1.9,c=G,fill=G)
    d.wire((87,52),(112,66),(140,66),c=S)
    d.txt(105,76,'Partition only',8.4,color=S)
    d.wire((87,50),(112,29),(140,29),c=T)
    d.txt(108,14,'Keep cells',8.6,color=T)
    for x,n in ((153,'a'),(191,'b')):
        for y,c in ((66,S),(29,T)):
            d.dotmark(x,y,5.5,c=c)
            d.node_label(x,y,n,8.8)
    d.wire((160,66),(184,66),c=S,arrow=False)
    d.mark('reject',172,29,10,A)
    d.txt(171,52,'Still joined',8.5,color=S)
    d.txt(171,13,'Split',8.5,color=T)
    return d


def compaction_gate():
    d=Diagram(252,55)
    d.mark('replica',11,29,13,S)
    d.wire((20,29),(43,29),c=S)
    d.txt(48,43,'ACKs match?',8.5,color=S)
    d.diamond(50,29,5,T)
    d.wire((57,29),(101,29),c=T)
    d.txt(108,43,r'$n_{>f}\leq p$?',9.5,color=S)
    d.diamond(108,29,5,T)
    d.wire((115,29),(155,29),c=T)
    d.txt(151,43,'All pass',8.0,color=T)
    d.mark('store',165,29,13,T)
    d.txt(206,35,r'Drop $e<f$',8.7,color=A)
    d.txt(206,23,r'Keep $e\geq f$',8.7,color=T)
    d.wire((50,23),(50,9),(105,9),c=A,dash=True,arrow=False)
    d.wire((108,23),(108,9),c=A,dash=True,arrow=False)
    d.dotmark(108,9,1.5,c=A,fill=A)
    d.wire((111,9),(142,9),c=A,dash=True)
    d.txt(149,9,'Refuse without mutation',8.0,ha='left',color=A)
    return d


FIGURES={f.__name__.replace('_','-'):f for f in (
    epoch_split,evidence_pipeline,negative_safe_view,recovery_boundary,merge_only_boundary,compaction_gate)}
