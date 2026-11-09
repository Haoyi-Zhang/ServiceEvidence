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
        d.wire((xs[0]+6,51),(xs[1]-6,51),c=T,arrow=False)
        if group==0:d.wire((xs[1]+6,51),(xs[2]-6,51),c=T,arrow=False)
        else:
            d.wire((xs[1]+6,51),(xs[2]-6,51),c=A,dash=True,arrow=False)
            d.mark('reject',202.5,51,14,A)
            d.txt(202,68,'Negative cell',8.15,color=A)
        for j,x in enumerate(xs):
            d.dotmark(x,51,6,c=A if group and j==2 else T)
            d.txt(x,51,'abc'[j],8.8)
    d.txt(60,25,r'$\{a,b,c\}$',9.4,color=T)
    d.txt(185,25,r'$\{a,b\},\,\{c\}$',9.4,color=T)
    return d


def evidence_pipeline():
    d=Diagram(242,139)
    d.mark('replica',23,116,19,S)
    d.mark('replica',219,116,19,S)
    d.txt(37,125,'Local replica',9.0,ha='left')
    d.txt(205,125,'Remote replica',9.0,ha='right')
    d.txt(57,106,r'$(F_1,C_1)$',10.0,color=S)
    d.txt(185,106,r'$(F_2,C_2)$',10.0,color=S)
    d.wire((57,96),(57,85),(104,85),c=S)
    d.wire((185,96),(185,85),(138,85),c=S)
    d.dotmark(121,85,9,c=S)
    d.txt(121,85,r'$\sqcup$',11,color=S)
    d.wire((121,76),(121,71),c=T)
    d.txt(121,63,r'$F^*=\max(F_1,F_2)$',10.1,color=T)
    d.txt(121,50,'Keep union cells at or above the floor',9.1,color=T)
    d.wire((121,43),(121,38),c=T)
    d.txt(121,31,'Read latest sealed epoch',9.2)
    d.wire((121,24),(121,20),(56,20),(56,15),c=T)
    d.wire((121,20),(186,20),(186,15),c=T)
    d.txt(56,8,'Partition',8.8,color=T)
    d.txt(186,8,'Certificate',8.8,color=T)
    return d


def negative_safe_view():
    d=Diagram(237,126)
    a,b,c=(37,52),(118,52),(199,52)
    d.wire((43,57),(43,95),(193,95),(193,57),c=A,dash=True,arrow=False)
    d.txt(118,108,'Negative pair (a, c)',9.2,color=A)
    d.wire((44,52),(111,52),c=T,arrow=False)
    d.wire((125,52),(192,52),c=F,dash=True,arrow=False)
    d.mark('reject',157,52,16,A)
    for x,y,ch in ((a[0],a[1],'a'),(b[0],b[1],'b'),(c[0],c[1],'c')):
        d.dotmark(x,y,6,c=A if ch=='c' else T);d.txt(x,y,ch,8.8)
    d.txt(78,68,'Accept',8.8,color=T)
    d.txt(158,68,'Veto',8.8,color=A)
    d.txt(118,19,'Read: {a, b}, {c}',9.2)
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
    d.txt(67,70,'Old or absent',9.1,color=S)
    d.txt(181,70,'New snapshot',9.1,color=T)
    for j in range(9):
        x=18+j*25.2
        if j:d.wire((x-19,38),(x-6,38),c=S if j<5 else T,arrow=False)
        d.dotmark(x,38,6,c=S if j<5 else T)
        d.txt(x,38,str(j+1),8.1)
    d.wire((131,23),(131,57),c=A,dash=True,arrow=False)
    d.txt(131,12,'Atomic replace',8.7,color=A)
    return d


def merge_only_boundary():
    d=Diagram(226,101)
    d.txt(69,89,'Same visible pair',9.0,bold=True)
    d.txt(170,89,'Later split?',9.0,bold=True)
    for y,lab,c,result in [(61,'X',S,'Blocked'),(28,'Y',T,'Split')]:
        d.txt(17,y,lab,9.6,bold=True)
        d.wire((55,y),(76,y),c=c,arrow=False)
        for x,ch in [(49,'a'),(82,'b')]:
            d.dotmark(x,y,5.5,c=c);d.txt(x,y,ch,8.4)
        d.wire((94,y),(136,y),c=c,dash=(lab=='X'))
        if lab=='X':
            d.mark('reject',153,y,17,A);d.txt(165,y,result,8.6,ha='left',color=A)
        else:
            for x,ch in [(153,'a'),(187,'b')]:
                d.dotmark(x,y,5.5,c=T);d.txt(x,y,ch,8.4)
    return d


def compaction_gate():
    d=Diagram(252,55)
    for y in (12,26,40):d.mark('replica',19,y,11,S)
    for y in (12,26,40):d.wire((27,y),(52,y),(52,26),c=S,arrow=False)
    d.wire((52,26),(92,26),c=S)
    d.txt(65,47,'All acknowledge',8.5,color=S)
    d.mark('guard',104,26,21,T);d.txt(104,10,'Floor',8.4)
    d.wire((117,26),(150,26),c=T)
    for x,label,c in [(161,r'$f$',T),(183,r'$f{+}1$',T),(205,r'$\cdots$',G)]:
        d.mark('epoch',x,26,16,c);d.txt(x,44,label,8.1,color=c)
    d.txt(183,10,'Retain floor + newer',8.4,color=T)
    return d


FIGURES={f.__name__.replace('_','-'):f for f in (
    epoch_split,evidence_pipeline,negative_safe_view,recovery_boundary,merge_only_boundary,compaction_gate)}
