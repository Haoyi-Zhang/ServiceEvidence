"""Replicated evidence, merge decisions, and recovery boundaries."""
import json
from pathlib import Path
from zipfile import ZipFile
from diagram_ink import Diagram,S,T,A,K,G,F,L,P,O


def epoch_split():
    d=Diagram(252,97)
    d.tag(8,87,'(a) Earlier seal')
    d.tag(132,87,'(b) Later seal')
    for group,xs in enumerate(((27,60,93),(153,186,219))):
        d.wire((xs[0]+7,51),(xs[1]-7,51),c=T,arrow=False)
        d.wire((xs[1]+7,51),(xs[2]-7,51),c=A if group else T,dash=bool(group),arrow=False)
        if group:
            d.mark('reject',202.5,51,13,A)
            d.txt(202,68,'Negative cell',8.55,color=A)
        for j,x in enumerate(xs):
            d.dotmark(x,51,6,c=A if group and j==2 else T)
            d.node_label(x,51,'abc'[j],9.1)
        ends=((xs[0]-7,xs[-1]+7),) if group==0 else ((xs[0]-7,xs[1]+7),(xs[2]-7,xs[2]+7))
        for a,b in ends:d.wire((a,37),(a,32),(b,32),(b,37),c=T,arrow=False)
    d.txt(60,20,r'$\{a,b,c\}$',9.7,color=T)
    d.txt(186,20,r'$\{a,b\},\,\{c\}$',9.7,color=T)
    return d


def evidence_pipeline():
    d=Diagram(242,139)
    for x,label,k in [(31,'Local',1),(211,'Remote',2)]:
        d.mark('replica',x,109,22,S)
        d.txt(x,129,label,9.3,bold=True)
        d.txt(x,90,rf'$(F_{k},C_{k})$',10.1,color=S)
    d.wire((48,109),(86,109),(109,89),c=S)
    d.wire((194,109),(156,109),(133,89),c=S)
    d.dotmark(121,83,8,c=T)
    d.node_label(121,83,r'$\sqcup$',10.8,color=T)
    d.wire((121,73),(121,46),c=T)
    d.node_label(60,66,r'$F^*(r)$',9.4,color=T)
    d.node_label(60,51,r'$=\max(F_1(r),F_2(r))$',9.4,color=T)
    d.node_label(183,66,r'$C^*$: filter $C_1\cup C_2$',9.2,color=T)
    d.node_label(183,51,r'$e(c)\geq F^*(r(c))$',9.4,color=T)
    d.mark('epoch',121,37,16,T)
    d.txt(121,7,'Latest sealed epoch',8.8,color=T)
    d.wire((110,37),(84,22),(62,22),c=T)
    d.wire((132,37),(159,22),(181,22),c=T)
    for x,kind,label in [(51,'graph','Partition'),(192,'cert','Certificate')]:
        d.mark(kind,x,22,16,T)
        d.txt(x,7,label,8.8,color=T)
    return d


def negative_safe_view():
    d=Diagram(237,126)
    d.tag(5,114,'(a) Candidate relations')
    d.tag(124,114,'(b) First union retained')
    for a,b,c in ((16,51,86),(135,170,205)):
        d.wire((a,69),(a+9,90),(c-9,90),(c,69),c=A,dash=True,arrow=False)
        d.txt(b,99,r'$(a,c)$ negative',8.8,color=A)
        for x,label in zip((a,b,c),'abc'):
            d.dotmark(x,61,6,c=S);d.node_label(x,61,label,9.4)
        d.wire((a+7,61),(b-7,61),c=T,arrow=False,lw=1)
    d.wire((58,61),(79,61),c=T,arrow=False,lw=1)
    d.txt(51,44,'Candidate positives',8.6,color=T)
    d.wire((93,61),(123,61),c=G)
    d.wire((177,61),(182,61),c=G,arrow=False)
    d.wire((193,61),(198,61),c=G,arrow=False)
    d.mark('reject',187.5,61,10,A)
    d.txt(190,45,r'$(b,c)$ blocked',8.6,color=A)
    for lo,hi,label in ((125,180,r'$\{a,b\}$'),(196,214,r'$\{c\}$')):
        d.wire((lo,35),(lo,30),(hi,30),(hi,35),c=T,arrow=False)
        d.txt((lo+hi)/2,17,label,10.1,color=T)
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
    d.mark('epoch',15,65,13,S);d.txt(29,65,'Recovered old / absent',9.1,ha='left',color=S)
    d.mark('epoch',142,65,13,T);d.txt(156,65,'Recovered new',9.1,ha='left',color=T)
    for j in range(9):
        x=18+j*25.2
        if j:d.wire((x-19,37),(x-7,37),c=G if j==5 else (S if j<5 else T),arrow=False)
        d.dotmark(x,37,6,c=S if j<5 else T)
        d.node_label(x,37,str(j+1),8.3)
    for midpoint,label in [(4.5,'Replace'),(6.5,'Dir. fsync')]:
        boundary=18+midpoint*25.2
        d.wire((boundary,23),(boundary,55),c=A,dash=True,arrow=False)
        d.txt(boundary,11,label,9,color=A)
    return d


def merge_only_boundary():
    d=Diagram(226,101)
    d.txt(95,89,'Same view',9.1)
    d.txt(176,89,'After negative cell',9.1)
    for y,lab,kind,name,c in [(63,'X','array','Merge only',S),
                             (27,'Y','keyed','Retained cells',T)]:
        d.mark(kind,27,y,14,c)
        d.txt(9,y,lab,9.2,color=c)
        d.txt(39,y-13,name,8.5,color=c)
        d.wire((88,y),(104,y),c=c,arrow=False)
        for x,ch in [(81,'a'),(111,'b')]:
            d.dotmark(x,y,5.5,c=c);d.node_label(x,y,ch,8.4)
        d.wire((123,y),(153,y),c=c,dash=(lab=='X'))
        if lab=='X':
            d.mark('reject',164,y,14,A)
            d.txt(177,y,'Cannot split',8.7,ha='left',color=A)
        else:
            for x,ch in [(164,'a'),(193,'b')]:
                d.dotmark(x,y,5.5,c=T);d.node_label(x,y,ch,8.4)
    return d


def compaction_gate():
    d=Diagram(252,55)
    for y in (12,25,38):
        d.mark('replica',12,y,10,S)
        d.wire((20,y),(36,y),(36,25),c=S,arrow=False)
    d.dotmark(36,25,2,c=S,fill=S)
    d.wire((40,25),(94,25),c=S)
    d.txt(47,47,'Matching ACKs',8.9,color=S)
    d.mark('guard',105,25,16,T)
    d.node_label(106,43,r'$n_{>f}\leq p$',9.4,color=T)
    d.wire((116,25),(145,25),c=T)
    d.wire((105,15),(105,7),(63,7),c=A,dash=True)
    d.txt(59,7,'Refuse',8.7,ha='right',color=A)
    for x,s,c in [(160,r'$e<f$',G),(194,r'$e=f$',T),(229,r'$e>f$',T)]:
        d.mark('epoch',x,25,14,c)
        d.txt(x,42,s,9.2,color=c)
    d.txt(160,8,'Drop',8.7,color=A)
    d.wire((183,17),(183,13),(242,13),(242,17),c=T,arrow=False)
    d.txt(212,5,'Retain',8.5,color=T)
    return d


FIGURES={f.__name__.replace('_','-'):f for f in (
    epoch_split,evidence_pipeline,negative_safe_view,recovery_boundary,merge_only_boundary,compaction_gate)}
