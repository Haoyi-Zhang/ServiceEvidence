"""An illustrative nonlocal path veto, not a measured trace."""
from math import hypot
from diagram_ink import Diagram, S, T, A

def compatible_paths():
    d=Diagram(248,84)
    xy={'A':(16,43),'B':(76,66),'C':(165,66),'D':(231,43),'E':(124,22)}
    def rim(u,v):
        x,y=xy[u]
        vx,vy=xy[v]
        step=8.3/hypot(vx-x,vy-y)
        return x+(vx-x)*step,y+(vy-y)*step
    for u,v,c in [('A','B',S),('B','C',S),('C','D',S),('A','E',T),('E','D',T)]:
        d.wire(rim(u,v),rim(v,u),c=c,arrow=False,lw=1 if c==T else .72)
    d.wire((20,51),(40,76),(143,76),(157.3,69.3),c=A,dash=True,arrow=False)
    for name,(x,y) in xy.items():
        d.dotmark(x,y,8,c=T if name=='E' else S)
        d.node_label(x,y,name,9.8)
    d.txt(119,54,r'$A$--$C$ veto',9.0,color=A)
    d.txt(124,5,r'Compatible path $A,E,D$',8.7,color=T)
    return d

FIGURES={'compatible-paths':compatible_paths}
