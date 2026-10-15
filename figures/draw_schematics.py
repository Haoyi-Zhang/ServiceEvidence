"""Draw the four evidence-state schematics directly as vector PDFs.

Requires Python 3.9+ and Matplotlib; no TeX engine or network is used.
"""
import argparse
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon, Circle, FancyArrowPatch

plt.rcParams.update({'font.family':'STIXGeneral', 'mathtext.fontset':'stix',
                     'font.size':9, 'pdf.fonttype':42, 'ps.fonttype':42,
                     'text.usetex':False, 'axes.unicode_minus':False})
CM = 1 / 2.54

class Drawing:
    def __init__(self, bounds):
        x0,y0,x1,y1 = bounds
        self.fig = plt.figure(figsize=((x1-x0)*CM,(y1-y0)*CM))
        self.ax = self.fig.add_axes([0,0,1,1], xlim=(x0,x1), ylim=(y0,y1))
        self.ax.set_aspect('equal'); self.ax.axis('off')
        self.nodes = {}
        self.labels = []

    def text(self,x,y,label,size=9,ha='center',va='center'):
        artist=self.ax.text(x,y,label,fontsize=size,ha=ha,va=va,
                            linespacing=1.15,clip_on=False,zorder=4)
        self.labels.append([artist,None])
        return artist

    def box(self,name,x,y,w,h,label,dashed=False,shape='rect',size=9):
        style = {'edgecolor':'black','facecolor':'white','linewidth':.55,
                 'linestyle':(0,(4,3)) if dashed else 'solid', 'zorder':2}
        if shape == 'diamond':
            obj = Polygon([(x-w/2,y),(x,y+h/2),(x+w/2,y),(x,y-h/2)],**style)
        elif shape == 'circle': obj = Circle((x,y),w/2,**style)
        else: obj = Rectangle((x-w/2,y-h/2),w,h,**style)
        self.ax.add_patch(obj); self.text(x,y,label,size)
        self.labels[-1][1]=(x-w/2,y-h/2,x+w/2,y+h/2)
        self.nodes[name] = (x,y,w,h,shape)

    def point(self,name,side):
        x,y,w,h,_ = self.nodes[name]
        return {'n':(x,y+h/2),'s':(x,y-h/2),'e':(x+w/2,y),
                'w':(x-w/2,y),'nw':(x-w/2,y+h/2),
                'ne':(x+w/2,y+h/2),'c':(x,y)}[side]

    def line(self,points,dashed=False):
        xs,ys=zip(*points)
        self.ax.plot(xs,ys,color='black',linewidth=.55,
                     linestyle=(0,(4,3)) if dashed else 'solid',zorder=1)

    def arrow(self,p,q,dashed=False,via=()):
        points=[p,*via,q]
        if via:self.line(points[:-1],dashed)
        self.ax.add_patch(FancyArrowPatch(points[-2],points[-1],
                         arrowstyle='-|>',mutation_scale=7.5,linewidth=.55,
                         color='black',shrinkA=0,shrinkB=0,
                         linestyle=(0,(4,3)) if dashed else 'solid',zorder=1))

    def edge(self,a,b,sa='s',sb='n',**kwargs):
        self.arrow(self.point(a,sa),self.point(b,sb),**kwargs)

    def frame(self,x,y,w,h):
        self.ax.add_patch(Rectangle((x,y),w,h,fill=False,edgecolor='black',
                                   linewidth=.55,linestyle=(0,(4,3)),zorder=0))

    def save(self,out,name):
        # Fixed physical canvas: do not enlarge or rasterize the scientific figure.
        self.fig.canvas.draw()
        renderer=self.fig.canvas.get_renderer()
        x0,x1=self.ax.get_xlim();y0,y1=self.ax.get_ylim()
        for artist,node in self.labels:
            b=artist.get_window_extent(renderer).transformed(self.ax.transData.inverted())
            if b.x0<x0-.02 or b.x1>x1+.02 or b.y0<y0-.02 or b.y1>y1+.02:
                raise ValueError(name+': clipped label '+repr(artist.get_text()))
            if node and (b.x0<node[0]-.02 or b.x1>node[2]+.02 or b.y0<node[1]-.02 or b.y1>node[3]+.02):
                raise ValueError(name+': label exceeds node '+repr(artist.get_text()))
        self.fig.savefig(out/(name+'.pdf'),format='pdf',
                         metadata={'Creator':'Python Matplotlib','Producer':None,
                                   'CreationDate':None,'ModDate':None})
        plt.close(self.fig)





def draw(out):
    d=Drawing((-.5,-2.42,16.75,2.25))
    for name,x,label in [('a',0,'a'),('b',1.6,'b'),('c',3.2,'c'),('a1',9.1,'a'),('b1',10.6,'b'),('c1',12.1,'c')]:
        d.box(name,x,0,.7,.7,r'$'+label+'$',shape='circle')
    d.edge('a','b',sa='e',sb='w');d.text(.8,.78,'redirect')
    d.edge('b','c',sa='e',sb='w');d.text(2.4,.78,'asset')
    d.box('v0',1.6,-1.8,2.8,1.0,r'Vantages $v_0,v_1$'+'\nPositive support')
    d.edge('v0','a',sa='nw',sb='s');d.edge('v0','c',sa='ne',sb='s')
    d.box('p0',6.1,0,2.8,1.3,'Epoch 0 sealed\n'+r'view: $\{a,b,c\}$')
    d.edge('c','p0',sa='e',sb='w')
    d.edge('a1','b1',sa='e',sb='w')
    d.edge('b1','c1',sa='e',sb='w',dashed=True);d.text(11.35,.78,'stale')
    d.box('v2',10.6,-1.8,2.8,1.0,r'Vantage $v_2$'+'\n'+r'Negative $(b,c)$')
    d.edge('v2','c1',sa='ne',sb='s')
    d.box('p1',15.2,0,2.8,1.3,'Epoch 1 sealed\n'+r'view: $\{a,b\},\{c\}$')
    d.edge('c1','p1',sa='e',sb='w')
    d.arrow(d.point('p0','n'),d.point('p1','n'),via=((6.1,1.7),(15.2,1.7)))
    d.text(10.65,2.02,'Replicate cells; recompute view')
    d.save(out,'epoch-split')

    d=Drawing((-1.65,-2.2,6.9,1.65))
    for name,x,y,label in [('obs',0,0,'Normalized\nobservations'),('cell',2.8,0,'Source-indexed\ncells'),
        ('join',5.6,0,'Union cells;\nmax floors'),('seal',5.6,-1.55,'Greatest sealed\nepoch per relation'),
        ('mat',2.8,-1.55,'Negative-safe\npartition'),('cert',0,-1.55,'Query\ncertificate')]:
        d.box(name,x,y,2.4,1.1,label)
    d.edge('obs','cell',sa='e',sb='w');d.edge('cell','join',sa='e',sb='w');d.text(4.2,.95,'deltas')
    d.edge('join','seal');d.edge('seal','mat',sa='w',sb='e');d.edge('mat','cert',sa='w',sb='e')
    d.arrow(d.point('cell','n'),d.point('cert','w'),dashed=True,via=((2.8,1.05),(-1.5,1.05),(-1.5,-1.55)))
    d.text(.5,1.36,'Retained reasons')
    d.save(out,'evidence-pipeline')

    d=Drawing((-3.75,-7.05,3.75,.57))
    rows=[('select',0,1.05,'Select greatest sealed epoch and decision\nfor every candidate relation'),
          ('index',-1.5,1.05,'Insert all different relations\ninto a negative-neighbor index'),
          ('initial',-2.9,.85,'Initialize singleton components'),
          ('union',-4.45,1.4,'For each same relation in lexical order,\nunion components iff their candidate union\ncontains no indexed negative pair'),
          ('result',-6.25,1.4,'Return components, accepted / rejected\npositive edges, negative edges,\nand unknown edges')]
    for name,y,height,label in rows:d.box(name,0,y,7.2,height,label)
    for left,right in zip(rows,rows[1:]):d.edge(left[0],right[0])
    d.save(out,'negative-safe-view')

    d=Drawing((-1.3,-1.7,5.5,1.7))
    d.box('x',0,.8,1.7,1.1,r'$X$: sealed $+$'+'\n'+r'$\{a,b\}$')
    d.box('y',0,-.8,1.7,1.1,r'$Y$: sealed $+$'+'\n'+r'$\{a,b\}$')
    d.frame(-1.15,-1.65,2.3,3.3)
    d.box('later',4.1,-.8,2.4,1.1,r'Sealed $-$ arrives'+'\n'+r'$\{a\},\{b\}$')
    d.edge('y','later',sa='e',sb='w')
    d.save(out,'merge-only-boundary')

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=Path(__file__).resolve().parent)
    out=parser.parse_args().output
    out.mkdir(parents=True,exist_ok=True)
    draw(out)
