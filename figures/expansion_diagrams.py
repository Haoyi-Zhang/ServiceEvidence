"""An illustrative nonlocal path veto, not a measured trace."""
from diagram_ink import Diagram, S, T, A

def compatible_paths():
    d=Diagram(248,84)
    xy={'A':(16,43),'B':(76,66),'C':(165,66),'D':(231,43),'E':(124,17)}
    for u,v,c in [('A','B',S),('B','C',S),('C','D',S),('A','E',T),('E','D',T)]:
        d.wire(xy[u],xy[v],c=c,arrow=False)
    d.wire((20,51),(40,76),(143,76),(160,70),c=A,dash=True,arrow=False)
    for name,(x,y) in xy.items():
        d.dotmark(x,y,8,c=T if name=='E' else S)
        d.text(x,y,name,9.8)
    d.txt(123,51,r'$A$--$C$ veto',9.0,color=A)
    d.txt(124,5,'Compatible alternative',8.8,color=T)
    return d

FIGURES={'compatible-paths':compatible_paths}
