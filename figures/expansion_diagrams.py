"""An illustrative nonlocal path veto, not a measured trace."""
from math import hypot
from diagram_ink import Diagram, S, T, A

def compatible_paths():
    d=Diagram(248,84)
    xy={'A':(19,39),'B':(76,54),'C':(159,54),'D':(228,39),'E':(124,21)}
    def rim(u,v):
        x,y=xy[u]
        vx,vy=xy[v]
        step=8.5/hypot(vx-x,vy-y)
        return x+(vx-x)*step,y+(vy-y)*step
    for u,v,c in (('A','B',S),('B','C',S),('C','D',S),('A','E',T),('E','D',T)):
        d.wire(rim(u,v),rim(v,u),c=c,arrow=False,lw=1 if c==T else .72)
    d.wire((21,49),(44,76),(130,76),(155,63),c=A,dash=True,arrow=False)
    d.txt(84,66,r'$A,C$ veto',8.8,color=A)
    for n,(x,y) in xy.items():
        d.dotmark(x,y,7.6,c=T if n=='E' else S)
        d.node_label(x,y,n,9.8)
    d.mark('check',86,7,10,T)
    d.txt(97,7,r'$A,E,D$ is compatible',8.8,ha='left',color=T)
    return d

FIGURES={'compatible-paths':compatible_paths}
